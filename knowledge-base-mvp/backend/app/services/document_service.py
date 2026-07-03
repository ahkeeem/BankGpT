"""
Document ingestion service: PDF extraction, web scraping, text chunking,
and orchestration of the embed → store pipeline.
"""

import hashlib
import uuid
from io import BytesIO
from typing import Any, Dict, List, Tuple

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.database.delta_store import DocumentMetadataStoreInterface
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorStoreInterface


class DocumentService:
    """Handles document extraction, chunking, and ingestion orchestration."""

    def __init__(
        self,
        metadata_store: DocumentMetadataStoreInterface,
        vector_store: VectorStoreInterface,
        embedding_service: EmbeddingService,
    ):
        self.metadata_store = metadata_store
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    # ------------------------------------------------------------------ #
    #  Text Extraction
    # ------------------------------------------------------------------ #

    def extract_pdf_text(self, file_bytes: bytes) -> str:
        """Extract text from a PDF file, page by page."""
        reader = PdfReader(BytesIO(file_bytes))
        pages: List[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)

    async def extract_url_text(self, url: str) -> str:
        """
        Scrape a web page and extract clean text content.
        Removes script/style tags; selects <main> or <article>, falls back to <body>.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Prefer semantic containers
        content_node = soup.find("main") or soup.find("article") or soup.find("body")
        if content_node is None:
            return ""

        # Get text with whitespace normalization
        text = content_node.get_text(separator="\n", strip=True)
        # Collapse excessive blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Text Chunking (Recursive Character Splitting)
    # ------------------------------------------------------------------ #

    def chunk_text(
        self, text: str, chunk_size: int = 1000, overlap: int = 200
    ) -> List[str]:
        """
        Split text into overlapping chunks using recursive character splitting.
        Tries to split on paragraph boundaries, then sentences, then words.
        """
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        separators = ["\n\n", "\n", ". ", " ", ""]
        return self._recursive_split(text, separators, chunk_size, overlap)

    def _recursive_split(
        self, text: str, separators: List[str], chunk_size: int, overlap: int
    ) -> List[str]:
        """Recursively split text using hierarchical separators."""
        chunks: List[str] = []
        separator = separators[0]
        remaining_separators = separators[1:]

        if separator == "":
            # Character-level split as fallback
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i : i + chunk_size]
                if chunk.strip():
                    chunks.append(chunk.strip())
            return chunks

        parts = text.split(separator)
        current_chunk = ""

        for part in parts:
            candidate = (
                current_chunk + separator + part if current_chunk else part
            )

            if len(candidate) <= chunk_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # If this single part exceeds chunk_size, split it further
                if len(part) > chunk_size and remaining_separators:
                    sub_chunks = self._recursive_split(
                        part, remaining_separators, chunk_size, overlap
                    )
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk and current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Apply overlap: extend each chunk with the beginning of the next
        if overlap > 0 and len(chunks) > 1:
            overlapped: List[str] = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    prev_tail = chunks[i - 1][-overlap:]
                    chunk = prev_tail + " " + chunk
                overlapped.append(chunk.strip())
            chunks = overlapped

        return chunks

    # ------------------------------------------------------------------ #
    #  Ingestion Orchestration
    # ------------------------------------------------------------------ #

    def _generate_chunk_id(self, document_id: str, index: int) -> str:
        """Generate a deterministic chunk ID."""
        raw = f"{document_id}_{index}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def ingest_pdf(
        self, file_bytes: bytes, filename: str, organization_id: str
    ) -> Dict[str, Any]:
        """
        Full PDF ingestion pipeline:
        1. Extract text from PDF
        2. Chunk the text
        3. Generate embeddings
        4. Save metadata to Delta table
        5. Upsert vectors to ChromaDB
        """
        document_id = str(uuid.uuid4())

        # Save initial metadata (status = processing)
        self.metadata_store.save_document({
            "document_id": document_id,
            "organization_id": organization_id,
            "name": filename,
            "type": "pdf",
            "status": "processing",
        })

        try:
            # Extract & chunk
            text = self.extract_pdf_text(file_bytes)
            if not text.strip():
                self.metadata_store.update_status(document_id, organization_id, "error")
                raise ValueError("No text could be extracted from PDF")

            text_chunks = self.chunk_text(text)

            # Embed
            embeddings = self.embedding_service.embed_texts(text_chunks)

            # Build chunk records
            chunks = [
                {
                    "chunk_id": self._generate_chunk_id(document_id, i),
                    "document_id": document_id,
                    "document_name": filename,
                    "text": chunk_text,
                    "embedding": embedding,
                    "chunk_index": i,
                }
                for i, (chunk_text, embedding) in enumerate(zip(text_chunks, embeddings))
            ]

            # Upsert to vector store
            self.vector_store.upsert_chunks(organization_id, chunks)

            # Update metadata
            self.metadata_store.update_status(document_id, organization_id, "indexed")

            return {
                "document_id": document_id,
                "name": filename,
                "type": "pdf",
                "status": "indexed",
                "chunk_count": len(chunks),
            }

        except Exception as e:
            self.metadata_store.update_status(document_id, organization_id, "error")
            raise e

    async def ingest_url(
        self, url: str, organization_id: str
    ) -> Dict[str, Any]:
        """
        Full URL ingestion pipeline:
        1. Scrape web page
        2. Chunk the text
        3. Generate embeddings
        4. Save metadata to Delta table
        5. Upsert vectors to ChromaDB
        """
        document_id = str(uuid.uuid4())
        # Derive a name from the URL
        name = url.split("//")[-1].split("/")[0][:80]

        self.metadata_store.save_document({
            "document_id": document_id,
            "organization_id": organization_id,
            "name": name,
            "type": "url",
            "status": "processing",
            "source_url": url,
        })

        try:
            text = await self.extract_url_text(url)
            if not text.strip():
                self.metadata_store.update_status(document_id, organization_id, "error")
                raise ValueError("No text could be extracted from URL")

            text_chunks = self.chunk_text(text)
            embeddings = self.embedding_service.embed_texts(text_chunks)

            chunks = [
                {
                    "chunk_id": self._generate_chunk_id(document_id, i),
                    "document_id": document_id,
                    "document_name": name,
                    "text": chunk_text,
                    "embedding": embedding,
                    "chunk_index": i,
                    "source_url": url,
                }
                for i, (chunk_text, embedding) in enumerate(zip(text_chunks, embeddings))
            ]

            self.vector_store.upsert_chunks(organization_id, chunks)
            self.metadata_store.update_status(document_id, organization_id, "indexed")

            return {
                "document_id": document_id,
                "name": name,
                "type": "url",
                "status": "indexed",
                "chunk_count": len(chunks),
                "source_url": url,
            }

        except Exception as e:
            self.metadata_store.update_status(document_id, organization_id, "error")
            raise e
