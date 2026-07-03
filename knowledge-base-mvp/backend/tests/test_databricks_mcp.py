import io
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.databricks_client import DatabricksClient
from app.database.delta_store import DatabricksMetadataStore
from app.services.vector_service import DatabricksVectorStore


class TestDatabricksClient(unittest.TestCase):
    """Test DatabricksClient operations in mock mode."""

    def setUp(self):
        # Force mock mode by clearing env vars
        settings.DATABRICKS_HOST = ""
        settings.DATABRICKS_TOKEN = ""
        self.client = DatabricksClient()

    def test_initialization_mock_mode(self):
        self.assertTrue(self.client.is_mock)

    def test_mock_execute_sql(self):
        res = self.client.execute_sql("SELECT * FROM test")
        self.assertEqual(res["status"]["state"], "SUCCEEDED")
        self.assertEqual(res["result"]["row_count"], 0)

    def test_mock_query_vector_search(self):
        res = self.client.query_vector_search([0.1]*1536, 5, "demo_org")
        self.assertIn("manifest", res)
        self.assertEqual(res["result"]["row_count"], 0)


class TestDatabricksStores(unittest.TestCase):
    """Test Databricks Vector and Metadata Stores."""

    @patch("app.core.databricks_client.DatabricksClient.execute_sql")
    def test_metadata_save_document(self, mock_execute_sql):
        mock_execute_sql.return_value = {
            "status": {"state": "SUCCEEDED"},
            "result": {"row_count": 0, "data_array": []}
        }
        store = DatabricksMetadataStore()
        doc = {
            "document_id": "test-doc-id",
            "organization_id": "demo_org",
            "name": "CBN_Circular.pdf",
            "type": "pdf",
            "status": "processing",
        }
        success = store.save_document(doc)
        self.assertTrue(success)
        self.assertTrue(mock_execute_sql.called)

    @patch("app.core.databricks_client.DatabricksClient.execute_sql")
    def test_vector_upsert_chunks(self, mock_execute_sql):
        mock_execute_sql.return_value = {
            "status": {"state": "SUCCEEDED"},
            "result": {"row_count": 0, "data_array": []}
        }
        store = DatabricksVectorStore()
        chunks = [{
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "document_name": "FAQ.pdf",
            "text": "This is synthetic banking text for Nigerian banks.",
            "embedding": [0.01] * 1536,
            "chunk_index": 0
        }]
        success = store.upsert_chunks("demo_org", chunks)
        self.assertTrue(success)
        self.assertTrue(mock_execute_sql.called)


from app import mcp_server


class TestMCPServer(unittest.TestCase):
    """Test MCP JSON-RPC protocol parsing and tool invocation."""

    @patch("app.mcp_server.real_stdout", new_callable=io.StringIO)
    def test_mcp_initialize(self, mock_stdout):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")):
            mcp_server.main()
            
        output = mock_stdout.getvalue().strip()
        resp = json.loads(output)
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", resp["result"]["capabilities"])

    @patch("app.mcp_server.real_stdout", new_callable=io.StringIO)
    def test_mcp_list_tools(self, mock_stdout):
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")):
            mcp_server.main()
            
        output = mock_stdout.getvalue().strip()
        resp = json.loads(output)
        self.assertEqual(resp["id"], 2)
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("databricks_vector_search", tool_names)
        self.assertIn("databricks_sql_query", tool_names)



if __name__ == "__main__":
    unittest.main()
