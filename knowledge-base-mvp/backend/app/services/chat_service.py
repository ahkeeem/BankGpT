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
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_CHAT_MODEL

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
        self, organization_id: str, question: str, top_k: int = 5
    ) -> AsyncGenerator[str, None]:
        """
        Full RAG pipeline with SSE streaming:
        1. Retrieve relevant context
        2. Stream LLM response token by token as SSE events
        3. Append source citations as final SSE event
        """
        # Retrieve context chunks
        chunks = self.retrieve_context(organization_id, question, top_k)
        context_text = self._build_context_prompt(chunks)
        sources = self._extract_sources(chunks)

        # Build messages for the LLM
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context Documents:\n\n{context_text}\n\n---\n\nQuestion: {question}",
            },
        ]

        # Stream from OpenAI
        if not settings.OPENAI_API_KEY:
            print("⚠️ [ChatService] OPENAI_API_KEY not set. Using mock chat generation.")
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
            for word in full_text.split(" "):
                yield f"data: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(0.04)

            yield f"data: {json.dumps({'sources': sources})}\n\n"
            yield "data: [DONE]\n\n"
            return

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
                    yield f"data: {json.dumps({'token': token})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error generating response: {str(e)}'})}\n\n"

        # Send source citations as the final event
        yield f"data: {json.dumps({'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
