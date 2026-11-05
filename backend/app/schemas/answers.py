from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictAnswerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerDraft(StrictAnswerSchema):
    answer: str = Field(min_length=1, max_length=12_000)
    cited_document_ids: list[UUID] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_unique_sources(self) -> Self:
        if len(self.cited_document_ids) != len(set(self.cited_document_ids)):
            raise ValueError("Cited document IDs must be unique.")
        return self


class EnglishSearchQuery(StrictAnswerSchema):
    translated_query: str = Field(min_length=3, max_length=2000)

    @field_validator("translated_query")
    @classmethod
    def validate_non_blank_query(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Translated query must contain at least three characters.")
        return normalized


class AskQuestionRequest(StrictAnswerSchema):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def validate_non_blank_question(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Question must contain at least three non-space characters.")
        return normalized


class AnswerCitation(StrictAnswerSchema):
    document_id: UUID
    chunk_id: UUID
    original_filename: str
    library_relative_path: str
    source_path: str
    excerpt: str
    page_start: int | None = None
    page_end: int | None = None
    heading: str | None = None
    retrieval_score: float = Field(ge=0, le=1)


class AskQuestionResponse(StrictAnswerSchema):
    answer: str
    citations: list[AnswerCitation]
    translated_question: str | None = None
