import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.routes.answers import answer_library_question
from app.core.config import get_settings
from app.db.models import ChatMessage, ChatSession
from app.db.session import get_db
from app.schemas.answers import AnswerCitation, AskQuestionRequest
from app.schemas.chats import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionDetail,
    ChatSessionSummary,
)
from app.services.llm.base import LLMProviderError
from app.services.llm.budget import TokenBudget
from app.services.llm.factory import create_llm_provider


router = APIRouter(prefix="/chats", tags=["chats"])
logger = structlog.get_logger(__name__)
_TITLE_STOP_WORDS = {
    "а",
    "без",
    "в",
    "где",
    "для",
    "до",
    "как",
    "какие",
    "какой",
    "каких",
    "ли",
    "мне",
    "на",
    "над",
    "о",
    "об",
    "по",
    "при",
    "про",
    "с",
    "со",
    "что",
    "это",
    "и",
    "the",
    "what",
    "which",
    "how",
    "are",
    "is",
    "was",
    "were",
    "used",
    "using",
}


def _fallback_title_label(question: str) -> str:
    words = re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", question, flags=re.UNICODE)
    keywords = [
        word for word in words if word.casefold() not in _TITLE_STOP_WORDS
    ][:6]
    return " ".join(keywords) or "Новый чат"


def _dated_title(label: str) -> str:
    date_label = datetime.now().strftime("%d.%m.%Y")
    return f"{date_label} · {label.strip()}"[:160]


def _message_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        chat_id=message.chat_id,
        question=message.question,
        answer=message.answer,
        citations=[
            AnswerCitation.model_validate(citation)
            for citation in message.citations
        ],
        translated_question=message.translated_question,
        created_at=message.created_at,
    )


def _session_summary(chat: ChatSession, message_count: int) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        message_count=message_count,
    )


@router.post("", response_model=ChatSessionSummary, status_code=status.HTTP_201_CREATED)
def create_chat(session: Session = Depends(get_db)) -> ChatSessionSummary:
    now = datetime.now(timezone.utc)
    chat = ChatSession(
        id=uuid4(),
        title=_dated_title("Новый чат"),
        created_at=now,
        updated_at=now,
    )
    session.add(chat)
    session.commit()
    return _session_summary(chat, 0)


@router.get("", response_model=list[ChatSessionSummary])
def list_chats(session: Session = Depends(get_db)) -> list[ChatSessionSummary]:
    rows = session.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.chat_id == ChatSession.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
    ).all()
    return [_session_summary(chat, count) for chat, count in rows]


@router.get("/{chat_id}", response_model=ChatSessionDetail)
def get_chat(
    chat_id: UUID,
    session: Session = Depends(get_db),
) -> ChatSessionDetail:
    chat = session.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == chat_id)
    ).scalar_one_or_none()
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat was not found.",
        )
    return ChatSessionDetail(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[_message_response(message) for message in chat.messages],
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: UUID,
    session: Session = Depends(get_db),
) -> None:
    chat = session.get(ChatSession, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat was not found.",
        )
    session.delete(chat)
    session.commit()


@router.post(
    "/{chat_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_chat_message(
    chat_id: UUID,
    request: ChatMessageCreate,
    session: Session = Depends(get_db),
) -> ChatMessageResponse:
    chat = session.get(ChatSession, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat was not found.",
        )

    is_first_message = len(chat.messages) == 0
    answer = answer_library_question(
        AskQuestionRequest(question=request.question),
        session,
    )

    if is_first_message:
        title_label = _fallback_title_label(request.question)
        try:
            settings = get_settings()
            provider = create_llm_provider(
                settings,
                TokenBudget(settings.token_limit),
            )
            title_label = provider.suggest_chat_title(request.question).title
        except LLMProviderError as error:
            logger.warning(
                "chat_title_generation_failed",
                error_type=error.__class__.__name__,
                fallback_used=True,
            )
        chat.title = _dated_title(title_label)

    now = datetime.now(timezone.utc)
    chat.updated_at = now
    message = ChatMessage(
        id=uuid4(),
        chat_id=chat.id,
        question=request.question,
        answer=answer.answer,
        translated_question=answer.translated_question,
        citations=[
            citation.model_dump(mode="json") for citation in answer.citations
        ],
        created_at=now,
    )
    session.add(message)
    session.commit()
    return _message_response(message)
