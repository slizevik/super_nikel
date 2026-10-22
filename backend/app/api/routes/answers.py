import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, IngestionJob
from app.db.session import get_db
from app.schemas.answers import (
    AnswerCitation,
    AskQuestionRequest,
    AskQuestionResponse,
)
from app.services.library_scanner import format_library_source_path
from app.services.llm.base import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    TokenBudgetExceeded,
)
from app.services.llm.budget import TokenBudget
from app.services.llm.factory import create_llm_provider


router = APIRouter(prefix="/answers", tags=["answers"])
MAX_ANSWER_SOURCES = 5
logger = structlog.get_logger(__name__)


@router.post("", response_model=AskQuestionResponse)
def answer_library_question(
    request: AskQuestionRequest,
    session: Session = Depends(get_db),
) -> AskQuestionResponse:
    settings = get_settings()
    text_config = literal_column("'simple'")
    query = func.websearch_to_tsquery(text_config, request.question)
    search_vector = func.to_tsvector(
        text_config,
        func.coalesce(IngestionJob.extracted_text, ""),
    )
    latest_job_id = (
        select(IngestionJob.id)
        .where(IngestionJob.document_id == Document.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = session.execute(
        select(
            Document.id,
            Document.original_filename,
            Document.library_relative_path,
            IngestionJob.extracted_text,
            func.ts_headline(
                text_config,
                IngestionJob.extracted_text,
                query,
                "MaxWords=120, MinWords=30, MaxFragments=3, "
                "FragmentDelimiter=' ... '",
            ),
            func.ts_rank(search_vector, query),
        )
        .join(IngestionJob, IngestionJob.id == latest_job_id)
        .where(
            Document.source_type == "library",
            IngestionJob.status == "completed",
            IngestionJob.extracted_text.is_not(None),
            search_vector.op("@@")(query),
        )
        .order_by(func.ts_rank(search_vector, query).desc())
        .limit(MAX_ANSWER_SOURCES)
    ).all()

    sources = [
        {
            "document_id": str(document_id),
            "title": filename,
            "excerpt": excerpt,
        }
        for (
            document_id,
            filename,
            _relative_path,
            _extracted_text,
            excerpt,
            _rank,
        ) in rows
        if excerpt and excerpt.strip()
    ]
    if not sources:
        return AskQuestionResponse(
            answer=(
                "В индексированном тексте не найдено фрагментов по этому вопросу. "
                "Попробуйте другие ключевые слова или сначала просканируйте папку."
            ),
            citations=[],
        )

    try:
        provider = create_llm_provider(
            settings,
            TokenBudget(settings.token_limit),
        )
        answer = provider.answer_question(
            request.question,
            json.dumps(sources, ensure_ascii=False),
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except TokenBudgetExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
        ) from error
    except LLMProviderError as error:
        logger.warning(
            "library_question_answer_failed",
            error_type=error.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The configured language model could not answer the question.",
        ) from error

    source_rows = {
        document_id: (filename, relative_path, excerpt)
        for (
            document_id,
            filename,
            relative_path,
            _extracted_text,
            excerpt,
            _rank,
        ) in rows
    }
    citations: list[AnswerCitation] = []
    for document_id in answer.cited_document_ids:
        source = source_rows.get(document_id)
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The language model referenced a document outside the search results.",
            )
        filename, relative_path, excerpt = source
        source_path = format_library_source_path(
            settings.library_display_root
            or (
                str(settings.library_root)
                if settings.library_root is not None
                else None
            ),
            relative_path,
        )
        if source_path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The library folder path is not configured.",
            )
        citations.append(
            AnswerCitation(
                document_id=document_id,
                original_filename=filename,
                library_relative_path=relative_path,
                source_path=source_path,
                excerpt=excerpt,
            )
        )

    logger.info(
        "library_question_answered",
        source_count=len(citations),
    )
    return AskQuestionResponse(answer=answer.answer, citations=citations)
