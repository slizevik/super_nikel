from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.answers import AnswerCitation


class StrictChatSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatTitleSuggestion(StrictChatSchema):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def validate_non_blank_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Chat title must not be blank.")
        return normalized


class ChatMessageCreate(StrictChatSchema):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def validate_non_blank_question(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Question must contain at least three non-space characters.")
        return normalized


class ChatMessageResponse(StrictChatSchema):
    id: UUID
    chat_id: UUID
    question: str
    answer: str
    citations: list[AnswerCitation]
    translated_question: str | None
    created_at: datetime


class ChatSessionSummary(StrictChatSchema):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatSessionDetail(StrictChatSchema):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]
