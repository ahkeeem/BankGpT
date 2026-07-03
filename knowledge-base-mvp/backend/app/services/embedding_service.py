"""
Embedding service using OpenAI's text-embedding API.
Batches requests to stay within API limits.
"""

from typing import List

from openai import OpenAI

from app.config import settings


class EmbeddingService:
    """Generates text embeddings using OpenAI's embedding models."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self.max_batch_size = 100  # OpenAI batch limit

    def _mock_embed(self, text: str) -> List[float]:
        """Generate a deterministic mock embedding vector of size 1536."""
        import hashlib
        import random
        h = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(h, 'big') % (2**32)
        rng = random.Random(seed)
        vector = [rng.gauss(0, 1) for _ in range(1536)]
        norm = sum(x*x for x in vector) ** 0.5
        return [x / norm for x in vector] if norm > 0 else [0.0] * 1536

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        Automatically batches large inputs to respect API limits.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (list of floats).
        """
        if not texts:
            return []

        if not settings.OPENAI_API_KEY:
            print("⚠️ [EmbeddingService] OPENAI_API_KEY not set. Using mock embeddings.")
            return [self._mock_embed(t) for t in texts]

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            # Clean empty strings (OpenAI rejects them)
            batch = [t if t.strip() else " " for t in batch]

            response = self.client.embeddings.create(
                input=batch,
                model=self.model,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        Generate an embedding for a single query string.

        Args:
            query: The search query to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        result = self.embed_texts([query])
        return result[0] if result else []
