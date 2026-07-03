"""
FastAPI application entrypoint.
Initializes services, mounts API routers, and configures CORS.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.delta_store import DocumentMetadataStoreInterface, LocalDeltaStore, DatabricksMetadataStore
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorStoreInterface, LocalChromaStore, DatabricksVectorStore

# --- Global service instances (initialized at startup) ---
metadata_store: DocumentMetadataStoreInterface = None  # type: ignore
vector_store: VectorStoreInterface = None  # type: ignore
embedding_service: EmbeddingService = None  # type: ignore
document_service: DocumentService = None  # type: ignore
chat_service: ChatService = None  # type: ignore


def provision_databricks_catalog_schema():
    """Ensure catalog, schema, and tables exist in Databricks Unity Catalog."""
    from app.core.databricks_client import DatabricksClient
    client = DatabricksClient()
    if client.is_mock:
        print("[Databricks Provisioning] Skipping database setup in MOCK mode.")
        return

    catalog = settings.DATABRICKS_CATALOG
    schema = settings.DATABRICKS_SCHEMA

    print(f"⚙️ [Databricks Provisioning] Ensuring catalog '{catalog}' and schema '{schema}' exist...")
    
    # 1. Attempt to create Catalog (ignore permissions errors)
    try:
        client.execute_sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
        print(f"✅ [Databricks Provisioning] Catalog '{catalog}' verified/created.")
    except Exception as e:
        print(f"⚠️ [Databricks Provisioning] Note: Could not create catalog '{catalog}' (might be due to permission restrictions). Assuming it exists. Details: {e}")

    # 2. Attempt to create Schema (under the catalog)
    try:
        client.execute_sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
        print(f"✅ [Databricks Provisioning] Schema '{catalog}.{schema}' verified/created.")
    except Exception as e:
        print(f"⚠️ [Databricks Provisioning] Note: Could not create schema '{catalog}.{schema}'. Details: {e}")

    # 3. Create document metadata table if not exists
    try:
        client.execute_sql(f"""
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.bank_document_metadata (
          document_id STRING,
          organization_id STRING,
          name STRING,
          type STRING,
          status STRING,
          source_url STRING,
          chunk_count INT,
          created_at STRING,
          updated_at STRING
        )
        """)
        print(f"✅ [Databricks Provisioning] Table '{catalog}.{schema}.bank_document_metadata' verified/created.")
    except Exception as e:
        print(f"❌ [Databricks Provisioning] Error creating table '{catalog}.{schema}.bank_document_metadata': {e}")

    # 4. Create chunks table if not exists
    try:
        client.execute_sql(f"""
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.bank_knowledge_chunks (
          chunk_id STRING,
          document_id STRING,
          document_name STRING,
          text STRING,
          embedding ARRAY<FLOAT>,
          chunk_index INT,
          source_url STRING,
          organization_id STRING
        )
        """)
        print(f"✅ [Databricks Provisioning] Table '{catalog}.{schema}.bank_knowledge_chunks' verified/created.")
    except Exception as e:
        print(f"❌ [Databricks Provisioning] Error creating table '{catalog}.{schema}.bank_knowledge_chunks': {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    global metadata_store, vector_store, embedding_service, document_service, chat_service

    # Ensure data directories exist
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)

    # Initialize provisioning if needed
    if settings.METADATA_PROVIDER == "databricks" or settings.VECTOR_PROVIDER == "databricks":
        try:
            provision_databricks_catalog_schema()
        except Exception as e:
            print(f"⚠️ [lifespan] Provisioning Databricks failed: {e}. Proceeding.")

    # Initialize pluggable stores
    if settings.METADATA_PROVIDER == "databricks":
        metadata_store = DatabricksMetadataStore()
    else:
        metadata_store = LocalDeltaStore()

    if settings.VECTOR_PROVIDER == "databricks":
        vector_store = DatabricksVectorStore()
    else:
        vector_store = LocalChromaStore()

    embedding_service = EmbeddingService()

    # Wire up services
    document_service = DocumentService(
        metadata_store=metadata_store,
        vector_store=vector_store,
        embedding_service=embedding_service,
    )
    chat_service = ChatService(
        vector_store=vector_store,
        embedding_service=embedding_service,
    )

    print(f"🚀 Knowledge Base MVP started [env={settings.ENVIRONMENT}]")
    print(f"📂 Data directory: {settings.DATA_DIR}")
    print(f"🔍 Vector provider: {settings.VECTOR_PROVIDER}")
    print(f"📊 Metadata provider: {settings.METADATA_PROVIDER}")

    yield  # Application runs here

    print("🛑 Shutting down Knowledge Base MVP")


# --- Create FastAPI app ---
app = FastAPI(
    title="AI Knowledge Base MVP",
    description="Multi-tenant AI retrieval platform with RAG-based chat",
    version="1.0.0",
    lifespan=lifespan,
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mount API Routers ---
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.ingestion import router as ingestion_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


# --- Health Check ---
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "AI Knowledge Base MVP",
        "version": "1.0.0",
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
