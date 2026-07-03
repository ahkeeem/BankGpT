"""
Chat retrieval service: RAG pipeline with SSE streaming.
Embeds query → retrieves relevant chunks → streams LLM response with citations.
"""

import json
from typing import Any, AsyncGenerator, Dict, List

from openai import OpenAI

from app.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorStoreInterface


# RAG system prompt instructing the LLM to use only provided context
RAG_SYSTEM_PROMPT = """You are BankGPT, the ultimate financial intelligence and support agent for the Nigerian market.
Answer the user's question using ONLY the provided context documents.

Rules:
1. Answer using ONLY information from the provided context. If the context does not contain the answer, state: "I don't have enough information in the knowledge base to answer that."
2. Be culturally and contextually aware of Nigerian banking terms (e.g., BVN, NIP, POS charges, USSD codes, NGN rates).
3. If the user asks for comparisons (e.g. transfer limits, account requirements, or fees between different banks like GTBank, UBA, Zenith), construct a neat markdown comparison table detailing the differences clearly.
4. Always cite your sources by placing the document name in square brackets at the end of the statement or paragraph, e.g., [CBN_FX_Spread_Circular_2024.pdf] or [UBA_FAQ].
5. Tone must be professional, helpful, and highly clear. Use headings and bullet points for readability.
"""


class ChatService:
    """Handles RAG-based chat with streaming LLM responses."""

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding_service: EmbeddingService,
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        
        if settings.GROQ_API_KEY:
            self.openai_client = OpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )
            self.model = settings.GROQ_CHAT_MODEL
            print(f"🤖 [ChatService] Running in GROQ Mode with model: {self.model}")
        else:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.model = settings.OPENAI_CHAT_MODEL
            print(f"🤖 [ChatService] Running in OpenAI Mode with model: {self.model}")

    def _get_redis_client(self):
        """Lazy initialization of the Redis/Valkey client."""
        if not hasattr(self, "_redis_client"):
            self._redis_client = None
            if settings.REDIS_URL:
                try:
                    import redis
                    self._redis_client = redis.Redis.from_url(
                        settings.REDIS_URL,
                        decode_responses=True,
                        socket_timeout=2.0,
                    )
                    self._redis_client.ping()
                    print(f"🔌 Connected to Valkey/Redis session store: {settings.REDIS_URL}")
                except Exception as e:
                    print(f"⚠️ [ChatService] Could not connect to Redis: {e}. Falling back to in-memory history.")
                    self._redis_client = None
        return self._redis_client

    def get_chat_history(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieve the conversational history for a session."""
        if not session_id:
            return []

        client = self._get_redis_client()
        if client:
            try:
                key = f"session:{session_id}"
                history_data = client.get(key)
                if history_data:
                    return json.loads(history_data)
            except Exception as e:
                print(f"[ChatService] Error reading from Redis: {e}")

        # In-memory fallback
        if not hasattr(self, "_in_memory_sessions"):
            self._in_memory_sessions = {}
        return self._in_memory_sessions.get(session_id, [])

    def save_chat_history(self, session_id: str, history: List[Dict[str, str]]):
        """Save the updated conversational history, capped to the last 10 messages."""
        if not session_id:
            return

        capped_history = history[-10:]

        client = self._get_redis_client()
        if client:
            try:
                key = f"session:{session_id}"
                client.set(key, json.dumps(capped_history), ex=settings.REDIS_SESSION_TTL)
                return
            except Exception as e:
                print(f"[ChatService] Error writing to Redis: {e}")

        # In-memory fallback
        if not hasattr(self, "_in_memory_sessions"):
            self._in_memory_sessions = {}
        self._in_memory_sessions[session_id] = capped_history

    def retrieve_context(
        self, organization_id: str, question: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Embed the question and retrieve the top-k relevant chunks
        from the vector store, filtered by organization_id.
        """
        query_embedding = self.embedding_service.embed_query(question)
        if not query_embedding:
            return []

        results = self.vector_store.search(
            organization_id=organization_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )
        return results

    def _build_context_prompt(self, chunks: List[Dict[str, Any]]) -> str:
        """Build the context section of the prompt from retrieved chunks."""
        if not chunks:
            return "No relevant documents found in the knowledge base."

        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            doc_name = chunk.get("metadata", {}).get("document_name", "Unknown")
            text = chunk.get("text", "")
            context_parts.append(f"[Document {i}: {doc_name}]\n{text}")

        return "\n\n---\n\n".join(context_parts)

    def _extract_sources(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract unique source citations from the retrieved chunks."""
        seen = set()
        sources = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc_name = metadata.get("document_name", "Unknown")
            if doc_name not in seen:
                seen.add(doc_name)
                sources.append({
                    "name": doc_name,
                    "document_id": metadata.get("document_id", ""),
                    "text_snippet": chunk.get("text", "")[:200] + "...",
                    "source_url": metadata.get("source_url", ""),
                    "relevance_score": round(chunk.get("score", 0), 4),
                })
        return sources

    async def stream_response(
        self, organization_id: str, question: str, top_k: int = 5, session_id: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        Full RAG pipeline with SSE streaming and conversation memory:
        1. Retrieve relevant context
        2. Fetch prior chat history
        3. Stream LLM response token by token as SSE events
        4. Save final response to Redis/in-memory session history
        5. Append source citations as final SSE event
        """
        # Retrieve context chunks
        chunks = self.retrieve_context(organization_id, question, top_k)
        context_text = self._build_context_prompt(chunks)
        sources = self._extract_sources(chunks)

        # Build messages for the LLM
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
        ]

        # Load session history
        history = self.get_chat_history(session_id) if session_id else []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({
            "role": "user",
            "content": f"Context Documents:\n\n{context_text}\n\n---\n\nQuestion: {question}",
        })

        # Stream from OpenAI or Groq
        if not settings.OPENAI_API_KEY and not settings.GROQ_API_KEY:
            print("⚠️ [ChatService] Neither OpenAI nor Groq keys set. Using mock chat generation.")
            import asyncio
            mock_intro = "**[Mock Mode - No OpenAI API Key Set]**\n\n"
            if chunks:
                mock_answer = f"Based on the retrieved documents, here is the relevant information for *\"{question}\"*:\n\n"
                for i, chunk in enumerate(chunks, 1):
                    doc_name = chunk.get("metadata", {}).get("document_name", "Unknown")
                    snippet = chunk.get("text", "")[:150].replace('\n', ' ') + "..."
                    mock_answer += f"- According to **[{doc_name}]**: \"{snippet}\"\n"
            else:
                mock_answer = "I don't have enough information in the knowledge base to answer that."

            full_text = mock_intro + mock_answer
            
            # Save history
            if session_id:
                new_history = history + [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": full_text}
                ]
                self.save_chat_history(session_id, new_history)

            for word in full_text.split(" "):
                yield f"data: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(0.04)

            yield f"data: {json.dumps({'sources': sources})}\n\n"
            yield "data: [DONE]\n\n"
            return

        full_answer = ""
        try:
            stream = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.3,
                max_tokens=1500,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_answer += token
                    yield f"data: {json.dumps({'token': token})}\n\n"

            # Save session history
            if session_id and full_answer:
                new_history = history + [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": full_answer}
                ]
                self.save_chat_history(session_id, new_history)

        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error generating response: {str(e)}'})}\n\n"

        # Send source citations as the final event
        yield f"data: {json.dumps({'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
