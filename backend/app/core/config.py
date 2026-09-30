from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nikelpower API"
    database_url: str = Field(
        default="postgresql+psycopg://nikelpower:localdev-postgres-password@localhost:5432/nikelpower"
    )
    redis_url: str = "redis://:localdev-redis-password@localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    llm_provider: str = "yandex"
    yandex_cloud_folder: str | None = None
    yandex_cloud_api_key: str | None = None
    yandex_cloud_model: str = "yandexgpt/latest"
    yandex_vision_model: str | None = None
    yandex_cloud_base_url: str = "https://llm.api.cloud.yandex.net/v1"
    llm_request_timeout_seconds: float = Field(default=120, gt=0)
    entity_min_occurrences: int = Field(default=2, ge=1)
    yandex_embedding_model: str = "emb/latest"
    embedding_dimensions: int = Field(default=256, gt=0)
    embedding_similarity_threshold: float = Field(default=0.82, ge=0, le=1)
    dictionary_context_top_k: int = Field(default=15, gt=0)
    token_limit: int = Field(default=1_000_000, gt=0)
    chunk_target_tokens: int = Field(default=850, gt=0)
    chunk_max_tokens: int = Field(default=1000, gt=0)
    chunk_overlap_paragraphs: int = Field(default=1, ge=0)
    ingestion_batch_size: int = Field(default=10, gt=0)
    graphiti_group_id: str = "nikelpower"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_heap: str = "2G"
    neo4j_pagecache: str = "2G"
    documents_dir: str = "./data/documents"
    ingestion_state_dir: str = "./data/ingestion"
    libreoffice_binary: str = "libreoffice"
    libreoffice_timeout_sec: int = Field(default=180, gt=0)
    converted_pdf_dir: str = "./data/ingestion/converted"
    analyze_document_images: bool = True
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
