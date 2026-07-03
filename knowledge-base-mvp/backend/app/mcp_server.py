import json
import os
import sys
import traceback
from typing import Any, Dict, List

# Keep a reference to the real stdout and redirect sys.stdout to sys.stderr
# to prevent any third-party library warning/log outputs from polluting the JSON-RPC channel.
real_stdout = sys.stdout
sys.stdout = sys.stderr

# Add parent directory to sys.path so app imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.databricks_client import DatabricksClient
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import LocalChromaStore, DatabricksVectorStore

# Initialize services
embedding_service = EmbeddingService()
vector_store = (
    DatabricksVectorStore()
    if settings.VECTOR_PROVIDER == "databricks"
    else LocalChromaStore()
)
db_client = DatabricksClient()


def send_response(response: dict):
    real_stdout.write(json.dumps(response) + "\n")
    real_stdout.flush()


def handle_initialize(request_id: Any, params: dict):
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "bank-gpt-knowledge-mcp",
                "version": "1.0.0",
            },
        },
    }
    send_response(response)


def handle_list_tools(request_id: Any):
    tools = [
        {
            "name": "databricks_vector_search",
            "description": (
                "Search the banking and regulatory knowledge base for specific policy rules, "
                "circulars, fees, guidelines, and bank FAQs. Returns relevant document text chunks."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search query (e.g. 'transfer fees', 'FIRS taxes', 'CBN FX spread').",
                    },
                    "organization_id": {
                        "type": "string",
                        "description": "Tenant organization ID.",
                        "default": "demo_org",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of chunks to retrieve.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "databricks_sql_query",
            "description": (
                "Query structured metadata, audit logs, or indexed policy details directly "
                "from Databricks SQL tables."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Read-only SELECT SQL statement.",
                    }
                },
                "required": ["sql"],
            },
        },
    ]
    response = {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
    send_response(response)


def execute_vector_search(query: str, organization_id: str, top_k: int) -> str:
    query_emb = embedding_service.embed_query(query)
    if not query_emb:
        return "Error generating query embedding."

    results = vector_store.search(organization_id, query_emb, top_k)
    if not results:
        return f"No matching chunks found for query '{query}'."

    formatted = []
    for i, res in enumerate(results, 1):
        doc_name = res.get("metadata", {}).get("document_name", "Unknown Document")
        score = res.get("score", 1.0)
        text = res.get("text", "")
        formatted.append(
            f"[{i}] Document: {doc_name} (Score: {score:.4f})\nContent: {text}\n"
        )
    return "\n---\n\n".join(formatted)


def execute_sql_query(sql: str) -> str:
    # Basic safety check: read-only queries only
    sql_upper = sql.strip().upper()
    if (
        not sql_upper.startswith("SELECT")
        and not sql_upper.startswith("SHOW")
        and not sql_upper.startswith("DESC")
    ):
        return "Error: Only read-only queries (SELECT, SHOW, DESC) are allowed via this tool."

    try:
        res = db_client.execute_sql(sql)
        status = res.get("status", {}).get("state")
        if status == "FAILED":
            return f"Database query failed: {res.get('status', {}).get('error', {}).get('message', 'Unknown error')}"

        result = res.get("result", {})
        data_array = result.get("data_array", [])
        manifest = res.get("manifest", {})
        columns = [c["name"] for c in manifest.get("columns", [])]

        if not data_array:
            return "Query completed. 0 rows returned."

        # Format as a simple markdown table
        header = " | ".join(columns)
        separator = " | ".join(["---"] * len(columns))
        rows = []
        for row in data_array:
            rows.append(" | ".join(map(str, row)))

        return (
            f"| {header} |\n| {separator} |\n"
            + "\n".join([f"| {r} |" for r in rows])
        )
    except Exception as e:
        return f"Database query failed: {str(e)}"


def handle_call_tool(request_id: Any, name: str, arguments: dict):
    try:
        if name == "databricks_vector_search":
            query = arguments.get("query", "")
            org_id = arguments.get("organization_id", "demo_org")
            top_k = arguments.get("top_k", 5)
            text_result = execute_vector_search(query, org_id, top_k)
        elif name == "databricks_sql_query":
            sql = arguments.get("sql", "")
            text_result = execute_sql_query(sql)
        else:
            text_result = f"Error: Tool '{name}' not found."

        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": text_result}]},
        }
        send_response(response)
    except Exception as e:
        error_msg = f"Error executing tool '{name}': {str(e)}\n{traceback.format_exc()}"
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": error_msg},
        }
        send_response(response)


def main():
    # MCP server listens to sys.stdin for client commands
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")

            if method == "initialize":
                handle_initialize(request_id, request.get("params", {}))
            elif method == "notifications/initialized":
                # Initialized notification, no response required
                pass
            elif method == "tools/list":
                handle_list_tools(request_id)
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {})
                handle_call_tool(request_id, name, arguments)
            elif request_id is not None:
                # Unknown method
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{method}' not found",
                        },
                    }
                )
        except Exception as e:
            # Send general RPC parse error
            send_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
            )


if __name__ == "__main__":
    main()
