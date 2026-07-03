"""
Vector store interface and local ChromaDB implementation.
The interface allows swapping to Databricks Vector Search in production.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


class VectorStoreInterface(ABC):
    """Abstract interface for vector storage and similarity search."""

    @abstractmethod
    def upsert_chunks(self, organization_id: str, chunks: List[Dict[str, Any]]) -> bool:
        """Upsert a list of document chunks containing 'chunk_id', 'text', and 'embedding'."""
        pass

    @abstractmethod
    def search(self, organization_id: str, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Query vector database filtering strictly by organization_id."""
        pass

    @abstractmethod
    def delete_chunks(self, organization_id: str, document_id: str) -> bool:
        """Delete all chunks belonging to a specific document within an org."""
        pass


class LocalChromaStore(VectorStoreInterface):
    """
    Local developer implementation using ChromaDB in persistent mode.
    Each organization gets its own collection for strict tenant isolation.
    """

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        os.makedirs(self.persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _get_collection(self, organization_id: str):
        """Get or create a ChromaDB collection for the given org."""
        collection_name = f"org_{organization_id}"
        # ChromaDB collection names must be 3-63 chars, alphanumeric + underscores
        collection_name = collection_name[:63]
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, organization_id: str, chunks: List[Dict[str, Any]]) -> bool:
        """
        Upsert chunks into the org's ChromaDB collection.
        Each chunk must contain: chunk_id, text, embedding, and optionally metadata.
        """
        try:
            collection = self._get_collection(organization_id)

            ids = [chunk["chunk_id"] for chunk in chunks]
            embeddings = [chunk["embedding"] for chunk in chunks]
            documents = [chunk["text"] for chunk in chunks]
            metadatas = [
                {
                    "document_id": chunk.get("document_id", ""),
                    "document_name": chunk.get("document_name", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "source_url": chunk.get("source_url", ""),
                }
                for chunk in chunks
            ]

            # ChromaDB has a batch limit; process in batches of 500
            batch_size = 500
            for i in range(0, len(ids), batch_size):
                end = i + batch_size
                collection.upsert(
                    ids=ids[i:end],
                    embeddings=embeddings[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end],
                )
            return True
        except Exception as e:
            print(f"[LocalChromaStore] Error upserting chunks: {e}")
            return False

    def search(self, organization_id: str, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar chunks within an org's collection.
        Returns list of dicts with 'chunk_id', 'text', 'score', and metadata.
        """
        try:
            collection = self._get_collection(organization_id)

            # Guard against empty collections
            if collection.count() == 0:
                return []

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            output = []
            for i in range(len(results["ids"][0])):
                output.append({
                    "chunk_id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "score": 1 - results["distances"][0][i],  # cosine distance → similarity
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })
            return output
        except Exception as e:
            print(f"[LocalChromaStore] Error searching: {e}")
            return []

    def delete_chunks(self, organization_id: str, document_id: str) -> bool:
        """Delete all chunks for a given document_id within the org collection."""
        try:
            collection = self._get_collection(organization_id)
            # Query by metadata to find matching chunk IDs
            results = collection.get(
                where={"document_id": document_id},
                include=[],
            )
            if results["ids"]:
                collection.delete(ids=results["ids"])
            return True
        except Exception as e:
            print(f"[LocalChromaStore] Error deleting chunks: {e}")
            return False


class DatabricksVectorStore(VectorStoreInterface):
    """
    Databricks Vector Search implementation.
    Inserts chunks into a Unity Catalog Delta Table, which syncs to the search index.
    Queries the vector search index directly via Databricks REST API.
    """

    def __init__(self):
        from app.core.databricks_client import DatabricksClient
        self.client = DatabricksClient()
        self.catalog = settings.DATABRICKS_CATALOG
        self.schema = settings.DATABRICKS_SCHEMA
        self.table_name = f"{self.catalog}.{self.schema}.bank_knowledge_chunks"

    def _escape_sql_string(self, s: str) -> str:
        if not s:
            return "NULL"
        return "'" + s.replace("'", "''") + "'"

    def _format_array(self, arr: List[float]) -> str:
        if not arr:
            return "NULL"
        return f"ARRAY({','.join(map(str, arr))})"

    def upsert_chunks(self, organization_id: str, chunks: List[Dict[str, Any]]) -> bool:
        """Insert vector chunks into the Unity Catalog table."""
        if not chunks:
            return True
        try:
            # Batch inserts to avoid statement length limits (e.g., 200 chunks per batch)
            batch_size = 200
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                values_parts = []
                for chunk in batch:
                    chunk_id = self._escape_sql_string(chunk["chunk_id"])
                    doc_id = self._escape_sql_string(chunk["document_id"])
                    doc_name = self._escape_sql_string(chunk["document_name"])
                    text = self._escape_sql_string(chunk["text"])
                    embedding = self._format_array(chunk["embedding"])
                    chunk_idx = chunk.get("chunk_index", 0)
                    src_url = self._escape_sql_string(chunk.get("source_url", ""))
                    org_id = self._escape_sql_string(organization_id)

                    values_parts.append(
                        f"({chunk_id}, {doc_id}, {doc_name}, {text}, {embedding}, {chunk_idx}, {src_url}, {org_id})"
                    )

                sql = f"""
                INSERT INTO {self.table_name} 
                (chunk_id, document_id, document_name, text, embedding, chunk_index, source_url, organization_id)
                VALUES {",".join(values_parts)}
                """
                self.client.execute_sql(sql)
            return True
        except Exception as e:
            print(f"[DatabricksVectorStore] Error upserting chunks: {e}")
            return False

    def search(self, organization_id: str, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search the Databricks Vector Search index."""
        try:
            resp = self.client.query_vector_search(query_embedding, top_k, organization_id)
            manifest = resp.get("manifest", {})
            columns = [c["name"] for c in manifest.get("columns", [])]
            result = resp.get("result", {})
            data_array = result.get("data_array", [])

            output = []
            for row in data_array:
                row_dict = {}
                for col, val in zip(columns, row):
                    row_dict[col] = val
                
                score = 1.0
                if len(row) > len(columns):
                    score = row[-1]
                elif "score" in row_dict:
                    score = row_dict["score"]

                output.append({
                    "chunk_id": row_dict.get("chunk_id", ""),
                    "text": row_dict.get("text", ""),
                    "score": score,
                    "metadata": {
                        "document_id": row_dict.get("document_id", ""),
                        "document_name": row_dict.get("document_name", ""),
                        "chunk_index": row_dict.get("chunk_index", 0),
                        "source_url": row_dict.get("source_url", ""),
                    }
                })
            return output
        except Exception as e:
            print(f"[DatabricksVectorStore] Error searching vector index: {e}")
            return []

    def delete_chunks(self, organization_id: str, document_id: str) -> bool:
        """Delete chunks for a document from the Delta Table."""
        try:
            org_id = self._escape_sql_string(organization_id)
            doc_id = self._escape_sql_string(document_id)
            sql = f"DELETE FROM {self.table_name} WHERE organization_id = {org_id} AND document_id = {doc_id}"
            self.client.execute_sql(sql)
            return True
        except Exception as e:
            print(f"[DatabricksVectorStore] Error deleting chunks: {e}")
            return False
