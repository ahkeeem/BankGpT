import os
import time
from typing import Any, Dict, List
import httpx
from app.config import settings


class DatabricksClient:
    """Helper to communicate with Databricks SQL and Vector Search APIs."""

    def __init__(self):
        self.host = settings.DATABRICKS_HOST.rstrip("/") if settings.DATABRICKS_HOST else ""
        self.token = settings.DATABRICKS_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.warehouse_id = (
            settings.DATABRICKS_SQL_HTTP_PATH.split("/")[-1]
            if settings.DATABRICKS_SQL_HTTP_PATH
            else ""
        )
        self.is_mock = not (self.host and self.token and self.warehouse_id)
        if self.is_mock:
            print("⚠️ [DatabricksClient] Missing credentials. Operating in MOCK mode.")

    def execute_sql(self, sql_statement: str) -> Dict[str, Any]:
        """Execute a SQL statement on Databricks SQL Warehouse using Statement Execution API."""
        if self.is_mock:
            print(f"[Mock Databricks SQL] Executing statement: {sql_statement}")
            return {
                "status": {"state": "SUCCEEDED"},
                "result": {"row_count": 0, "data_array": []},
            }

        url = f"{self.host}/api/2.0/sql/statements"
        payload = {
            "warehouse_id": self.warehouse_id,
            "statement": sql_statement,
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            res_json = response.json()

            statement_id = res_json.get("statement_id")
            status = res_json.get("status", {}).get("state")

            while status in ["PENDING", "RUNNING"]:
                time.sleep(0.5)
                poll_url = f"{self.host}/api/2.0/sql/statements/{statement_id}"
                poll_resp = client.get(poll_url, headers=self.headers)
                poll_resp.raise_for_status()
                res_json = poll_resp.json()
                status = res_json.get("status", {}).get("state")

            if status == "FAILED":
                error_msg = (
                    res_json.get("status", {})
                    .get("error", {})
                    .get("message", "Unknown error")
                )
                raise Exception(f"Databricks SQL Execution Failed: {error_msg}")

            return res_json

    def query_vector_search(
        self, query_embedding: List[float], top_k: int, organization_id: str
    ) -> Dict[str, Any]:
        """Query Databricks Vector Search REST API."""
        if self.is_mock:
            print(
                f"[Mock Databricks Vector Search] Searching endpoint={settings.DATABRICKS_VECTOR_SEARCH_ENDPOINT} for org={organization_id}"
            )
            return {
                "manifest": {
                    "columns": [
                        {"name": "chunk_id", "type": "STRING"},
                        {"name": "document_id", "type": "STRING"},
                        {"name": "document_name", "type": "STRING"},
                        {"name": "text", "type": "STRING"},
                        {"name": "chunk_index", "type": "LONG"},
                        {"name": "source_url", "type": "STRING"},
                    ]
                },
                "result": {"row_count": 0, "data_array": []},
            }

        index_name = settings.DATABRICKS_VECTOR_INDEX_NAME
        url = f"{self.host}/api/2.0/vector-search/indexes/{index_name}/query"

        payload = {
            "query_vector": query_embedding,
            "columns": [
                "chunk_id",
                "document_id",
                "document_name",
                "text",
                "chunk_index",
                "source_url",
            ],
            "num_results": top_k,
            "filters": {"organization_id": organization_id},
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
