"""
Document metadata storage interface and local Delta Lake implementation.
The interface allows swapping to Databricks Unity Catalog in production.
"""

import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from deltalake import DeltaTable, write_deltalake

from app.config import settings


class DocumentMetadataStoreInterface(ABC):
    """Abstract interface for document metadata persistence."""

    @abstractmethod
    def save_document(self, doc_metadata: Dict[str, Any]) -> bool:
        """Saves or updates document metadata (doc_id, name, type, status)."""
        pass

    @abstractmethod
    def list_documents(self, organization_id: str) -> List[Dict[str, Any]]:
        """Lists all documents belonging to a specific organization."""
        pass

    @abstractmethod
    def update_status(self, document_id: str, organization_id: str, status: str) -> bool:
        """Updates the status of a specific document."""
        pass

    @abstractmethod
    def delete_document(self, document_id: str, organization_id: str) -> bool:
        """Deletes a document record."""
        pass


class LocalDeltaStore(DocumentMetadataStoreInterface):
    """
    Local developer implementation using python-deltalake.
    Writes Delta Lake tables to disk without requiring Spark or JVM.
    """

    def __init__(self, table_path: Optional[str] = None):
        self.table_path = table_path or settings.DELTA_TABLE_PATH
        os.makedirs(os.path.dirname(self.table_path), exist_ok=True)

    def _table_exists(self) -> bool:
        """Check if the Delta table already exists on disk."""
        try:
            DeltaTable(self.table_path)
            return True
        except Exception:
            return False

    def _read_all(self) -> pd.DataFrame:
        """Read the entire Delta table into a DataFrame."""
        if not self._table_exists():
            return pd.DataFrame(columns=[
                "document_id", "organization_id", "name", "type",
                "status", "source_url", "chunk_count", "created_at", "updated_at"
            ])
        dt = DeltaTable(self.table_path)
        return dt.to_pandas()

    def save_document(self, doc_metadata: Dict[str, Any]) -> bool:
        """Append a new document record to the Delta table."""
        try:
            record = {
                "document_id": doc_metadata.get("document_id", str(uuid.uuid4())),
                "organization_id": doc_metadata["organization_id"],
                "name": doc_metadata["name"],
                "type": doc_metadata.get("type", "pdf"),
                "status": doc_metadata.get("status", "processing"),
                "source_url": doc_metadata.get("source_url", ""),
                "chunk_count": doc_metadata.get("chunk_count", 0),
                "created_at": doc_metadata.get("created_at", datetime.now(timezone.utc).isoformat()),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            df = pd.DataFrame([record])
            write_deltalake(self.table_path, df, mode="append")
            return True
        except Exception as e:
            print(f"[LocalDeltaStore] Error saving document: {e}")
            return False

    def list_documents(self, organization_id: str) -> List[Dict[str, Any]]:
        """List all documents for a given organization."""
        try:
            df = self._read_all()
            if df.empty:
                return []
            filtered = df[df["organization_id"] == organization_id]
            return filtered.to_dict(orient="records")
        except Exception as e:
            print(f"[LocalDeltaStore] Error listing documents: {e}")
            return []

    def update_status(self, document_id: str, organization_id: str, status: str) -> bool:
        """
        Update status by rewriting the table.
        Reads all rows, modifies the matching row, overwrites.
        """
        try:
            df = self._read_all()
            if df.empty:
                return False
            mask = (df["document_id"] == document_id) & (df["organization_id"] == organization_id)
            if not mask.any():
                return False
            df.loc[mask, "status"] = status
            df.loc[mask, "updated_at"] = datetime.now(timezone.utc).isoformat()
            write_deltalake(self.table_path, df, mode="overwrite")
            return True
        except Exception as e:
            print(f"[LocalDeltaStore] Error updating status: {e}")
            return False

    def delete_document(self, document_id: str, organization_id: str) -> bool:
        """Delete a document by rewriting the table without the matching row."""
        try:
            df = self._read_all()
            if df.empty:
                return False
            mask = (df["document_id"] == document_id) & (df["organization_id"] == organization_id)
            if not mask.any():
                return False
            df = df[~mask]
            write_deltalake(self.table_path, df, mode="overwrite")
            return True
        except Exception as e:
            print(f"[LocalDeltaStore] Error deleting document: {e}")
            return False


class DatabricksMetadataStore(DocumentMetadataStoreInterface):
    """
    Databricks Unity Catalog implementation of the document metadata store.
    Uses Serverless Databricks SQL REST Statement API for persistence.
    """

    def __init__(self):
        from app.core.databricks_client import DatabricksClient
        self.client = DatabricksClient()
        self.catalog = settings.DATABRICKS_CATALOG
        self.schema = settings.DATABRICKS_SCHEMA
        self.table_name = f"{self.catalog}.{self.schema}.bank_document_metadata"

    def _escape_sql_string(self, s: str) -> str:
        if not s:
            return "NULL"
        return "'" + s.replace("'", "''") + "'"

    def save_document(self, doc_metadata: Dict[str, Any]) -> bool:
        """Saves or updates document metadata using SQL MERGE statement."""
        try:
            doc_id = doc_metadata.get("document_id", str(uuid.uuid4()))
            org_id = doc_metadata["organization_id"]
            name = doc_metadata["name"]
            dtype = doc_metadata.get("type", "pdf")
            status = doc_metadata.get("status", "processing")
            source_url = doc_metadata.get("source_url", "")
            chunk_count = doc_metadata.get("chunk_count", 0)
            created_at = doc_metadata.get("created_at", datetime.now(timezone.utc).isoformat())
            updated_at = datetime.now(timezone.utc).isoformat()

            sql = f"""
            MERGE INTO {self.table_name} AS target
            USING (SELECT {self._escape_sql_string(doc_id)} AS document_id) AS source
            ON target.document_id = source.document_id
            WHEN MATCHED THEN
              UPDATE SET 
                status = {self._escape_sql_string(status)},
                chunk_count = {chunk_count},
                updated_at = {self._escape_sql_string(updated_at)}
            WHEN NOT MATCHED THEN
              INSERT (document_id, organization_id, name, type, status, source_url, chunk_count, created_at, updated_at)
              VALUES (
                {self._escape_sql_string(doc_id)}, 
                {self._escape_sql_string(org_id)}, 
                {self._escape_sql_string(name)}, 
                {self._escape_sql_string(dtype)}, 
                {self._escape_sql_string(status)}, 
                {self._escape_sql_string(source_url)}, 
                {chunk_count}, 
                {self._escape_sql_string(created_at)}, 
                {self._escape_sql_string(updated_at)}
              )
            """
            self.client.execute_sql(sql)
            return True
        except Exception as e:
            print(f"[DatabricksMetadataStore] Error saving document: {e}")
            return False

    def list_documents(self, organization_id: str) -> List[Dict[str, Any]]:
        """Lists all documents belonging to a specific organization."""
        try:
            org_id = self._escape_sql_string(organization_id)
            sql = f"SELECT * FROM {self.table_name} WHERE organization_id = {org_id}"
            resp = self.client.execute_sql(sql)
            
            manifest = resp.get("manifest", {})
            columns = [c["name"] for c in manifest.get("columns", [])]
            result = resp.get("result", {})
            data_array = result.get("data_array", [])
            
            output = []
            for row in data_array:
                row_dict = {}
                for col, val in zip(columns, row):
                    row_dict[col] = val
                output.append(row_dict)
            return output
        except Exception as e:
            print(f"[DatabricksMetadataStore] Error listing documents: {e}")
            return []

    def update_status(self, document_id: str, organization_id: str, status: str) -> bool:
        """Updates the status of a specific document."""
        try:
            doc_id = self._escape_sql_string(document_id)
            org_id = self._escape_sql_string(organization_id)
            stat = self._escape_sql_string(status)
            updated_at = self._escape_sql_string(datetime.now(timezone.utc).isoformat())
            
            sql = f"""
            UPDATE {self.table_name}
            SET status = {stat}, updated_at = {updated_at}
            WHERE document_id = {doc_id} AND organization_id = {org_id}
            """
            self.client.execute_sql(sql)
            return True
        except Exception as e:
            print(f"[DatabricksMetadataStore] Error updating status: {e}")
            return False

    def delete_document(self, document_id: str, organization_id: str) -> bool:
        """Deletes a document record."""
        try:
            doc_id = self._escape_sql_string(document_id)
            org_id = self._escape_sql_string(organization_id)
            
            sql = f"DELETE FROM {self.table_name} WHERE document_id = {doc_id} AND organization_id = {org_id}"
            self.client.execute_sql(sql)
            return True
        except Exception as e:
            print(f"[DatabricksMetadataStore] Error deleting document: {e}")
            return False
