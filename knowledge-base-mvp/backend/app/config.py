"""
Application configuration loaded from environment variables.
Supports pluggable provider selection for vector store and metadata store.
"""

import os
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Central configuration for the Knowledge Base backend."""

    # --- Environment ---
    ENVIRONMENT: Literal["DEV", "PROD"] = "DEV"

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"

    # --- JWT Auth ---
    JWT_SECRET_KEY: str = "dev-secret-change-in-production-kb-mvp-2024"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 480  # 8 hours

    # --- Data Storage ---
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    # --- Pluggable Provider Selection ---
    VECTOR_PROVIDER: Literal["chroma", "databricks"] = "chroma"
    METADATA_PROVIDER: Literal["delta_local", "databricks"] = "delta_local"

    # --- ChromaDB Local Settings ---
    CHROMA_PERSIST_DIR: str = ""

    # --- Delta Lake Local Settings ---
    DELTA_TABLE_PATH: str = ""

    # --- Databricks Settings ---
    DATABRICKS_HOST: str = ""
    DATABRICKS_TOKEN: str = ""
    DATABRICKS_SQL_HTTP_PATH: str = ""
    DATABRICKS_CATALOG: str = "main"
    DATABRICKS_SCHEMA: str = "banking_schema"
    DATABRICKS_VECTOR_SEARCH_ENDPOINT: str = ""
    DATABRICKS_VECTOR_INDEX_NAME: str = ""

    # --- Redis / Valkey Settings ---
    REDIS_URL: str = ""
    REDIS_SESSION_TTL: int = 86400  # 24 hours


    # --- CORS ---
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def model_post_init(self, __context):
        """Set derived paths after initialization."""
        if not self.CHROMA_PERSIST_DIR:
            self.CHROMA_PERSIST_DIR = os.path.join(self.DATA_DIR, "chroma")
        if not self.DELTA_TABLE_PATH:
            self.DELTA_TABLE_PATH = os.path.join(self.DATA_DIR, "delta_documents")


# Singleton settings instance
settings = Settings()
