import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.answers import (
    AnswerCitation,
    AnswerDraft,
    AskQuestionRequest,
    AskQuestionResponse,
)
from app.services.library_scanner import format_library_source_path
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    create_embedding_provider,
)
from app.services.llm.base import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    TokenBudgetExceeded,
)
from app.services.llm.budget import TokenBudget
from app.services.llm.factory import create_llm_provider
from app.services.query_expansion import contains_cyrillic
from app.services.retrieval import RetrievedChunk, search_library


router = APIRouter(prefix="/answers", tags=["answers"])
MAX_ANSWER_SOURCES = 5
logger = structlog.get_logger(__name__)


def _validate_cited_sources(
    cited_document_ids: list[str],
    allowed_document_ids: set[str],
) -> None:
    if not cited_document_ids:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model returned no cited document IDs.",
        )

    duplicates = [
        document_id
        for document_id in cited_document_ids
        if cited_document_ids.count(document_id) > 1
    ]
    if duplicates:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model repeated a cited document ID.",
        )

    bad_ids = [
        document_id
        for document_id in cited_document_ids
        if document_id not in allowed_document_ids
    ]
    if bad_ids:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The language model referenced a document outside the search results: "
                f"{', '.join(sorted(bad_ids))}"
            ),
        )


@router.post("", response_model=AskQuestionResponse)
def answer_library_question(
    request: AskQuestionRequest,
    session: Session = Depends(get_db),
) -> AskQuestionResponse:
    settings = get_settings()
    translated_question = None
    provider = None
    token_budget = TokenBudget(settings.token_limit)
    if contains_cyrillic(request.question):
        try:
            provider = create_llm_provider(settings, token_budget)
            translated_question = provider.translate_question_to_english(
                request.question
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
                "library_question_translation_failed",
                error_type=error.__class__.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The configured language model could not translate the search question.",
            ) from error

    try:
        embedding_provider = create_embedding_provider(settings)
        retrieved_chunks = search_library(
            session,
            request.question,
            embedding_provider,
            translated_query=translated_question,
            limit=MAX_ANSWER_SOURCES,
        )
    except EmbeddingConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except (EmbeddingProviderError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The library search could not be completed.",
        ) from error

    sources = [
        {
            "document_id": str(chunk.document_id),
            "chunk_id": str(chunk.chunk_id),
            "title": chunk.original_filename,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "heading": chunk.heading,
            "excerpt": chunk.excerpt,
        }
        for chunk in retrieved_chunks
        if chunk.excerpt and chunk.excerpt.strip()
    ]
    if not sources:
        return AskQuestionResponse(
            answer=(
                "В индексированном тексте не найдено фрагментов по этому вопросу. "
                "Попробуйте другие ключевые слова или сначала просканируйте папку."
            ),
            citations=[],
            translated_question=translated_question,
        )

    try:
        if provider is None:
            provider = create_llm_provider(settings, token_budget)
        raw_answer = provider.answer_question(
            request.question,
            json.dumps(sources, ensure_ascii=False),
        )
        answer = raw_answer
        if not isinstance(answer, dict):
            answer = answer.model_dump(mode="json")
        answer = AnswerDraft.model_validate(answer)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model returned an invalid answer payload.",
        ) from error
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

    source_rows: dict[str, RetrievedChunk] = {}
    for chunk in retrieved_chunks:
        source_rows.setdefault(str(chunk.document_id), chunk)
    cited_ids = [str(document_id) for document_id in answer.cited_document_ids]
    _validate_cited_sources(cited_ids, set(source_rows.keys()))

    citations: list[AnswerCitation] = []
    for document_id in answer.cited_document_ids:
        source = source_rows.get(str(document_id))
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The language model referenced a document outside the search results.",
            )
        source_path = format_library_source_path(
            settings.library_display_root
            or (
                str(settings.library_root)
                if settings.library_root is not None
                else None
            ),
            source.library_relative_path,
        )
        if source_path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The library folder path is not configured.",
            )
        citations.append(
            AnswerCitation(
                document_id=document_id,
                chunk_id=source.chunk_id,
                original_filename=source.original_filename,
                library_relative_path=source.library_relative_path or "",
                source_path=source_path,
                excerpt=source.excerpt,
                page_start=source.page_start,
                page_end=source.page_end,
                heading=source.heading,
                retrieval_score=source.hybrid_score,
            )
        )

    logger.info(
        "library_question_answered",
        source_count=len(citations),
    )
    return AskQuestionResponse(
        answer=answer.answer,
        citations=citations,
        translated_question=translated_question,
    )
