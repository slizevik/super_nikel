from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestionJobResponse(BaseModel):
    id: UUID
    document_id: UUID
    status: str
    current_step: str | None
    progress_percent: int
    error_code: str | None
    error_message: str | None
    document_manifest: dict | None = None
    image_descriptions: list[dict] | None = None
    extraction_result: dict | None = None
    token_budget_limit: int
    tokens_consumed: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    id: UUID
    original_filename: str
    mime_type: str
    category: str
    title: str | None
    authors: list[str]
    published_at: date | None
    file_size_bytes: int
    sha256: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    job: IngestionJobResponse


class DocumentDetailResponse(DocumentUploadResponse):
    text_extracted: bool
    extracted_text_preview: str | None
    extracted_text_truncated: bool


class JobStatusResponse(IngestionJobResponse):
    is_terminal: bool
    is_success: bool


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]
