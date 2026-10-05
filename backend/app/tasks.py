from datetime import datetime, timezone
from uuid import UUID

import structlog
from celery import shared_task

from app.core.config import get_settings
from app.core.pipeline import IngestionStatus, PipelineStep, transition_job
from app.db.models import Document, IngestionJob
from app.db.session import SessionLocal
from app.schemas.extraction import ExtractionResult, ImageDescription
from app.services.extraction import ExtractionValidationError, validate_extraction_result
from app.services.llm.base import (
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
    LLMResponseError,
    ImageInput,
    TokenBudgetExceeded,
)
from app.services.llm.budget import TokenBudget
from app.services.llm.factory import create_llm_provider
from app.services.pdf_parser import DoclingParsingError, ParsedDocument, parse_pdf


logger = structlog.get_logger(__name__)


class PipelineFailure(RuntimeError):
    def __init__(self, code: str, step: PipelineStep, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.step = step


def get_llm_provider(token_budget: TokenBudget) -> LLMProvider:
    return create_llm_provider(get_settings(), token_budget)


def _set_step(job: IngestionJob, step: PipelineStep, progress: int) -> None:
    job.current_step = step.value
    job.progress_percent = progress


def _mark_failed(
    session,
    job: IngestionJob,
    code: str,
    step: PipelineStep,
    message: str,
) -> None:
    if job.status != IngestionStatus.FAILED.value:
        transition_job(job, IngestionStatus.FAILED)
    job.current_step = step.value
    job.error_code = code
    job.error_message = message[:2000]
    job.finished_at = datetime.now(timezone.utc)
    session.commit()


def _parse_document(pdf_bytes: bytes) -> ParsedDocument:
    try:
        return parse_pdf(pdf_bytes)
    except DoclingParsingError as error:
        raise PipelineFailure(
            "PDF_PARSING_FAILED", PipelineStep.PARSING_ERROR, str(error)
        ) from error


def _describe_images(
    provider: LLMProvider,
    parsed_document: ParsedDocument,
) -> list[ImageDescription]:
    descriptions: list[ImageDescription] = []
    for image in parsed_document.images:
        try:
            description = provider.describe_image(
                ImageInput(
                    image_id=image.image_id,
                    content=image.content,
                    media_type=image.media_type,
                    caption=image.caption,
                    width=image.width,
                    height=image.height,
                ),
                parsed_document.markdown,
            )
        except LLMConfigurationError:
            raise
        except TokenBudgetExceeded as error:
            raise PipelineFailure(
                "TOKEN_LIMIT_EXCEEDED",
                PipelineStep.IMAGE_ERROR,
                str(error),
            ) from error
        except LLMProviderError as error:
            raise PipelineFailure(
                "IMAGE_DESCRIPTION_FAILED",
                PipelineStep.IMAGE_ERROR,
                f"Could not analyze {image.image_id}: {error}",
            ) from error
        except Exception as error:
            logger.exception(
                "unexpected_image_analysis_error",
                image_id=image.image_id,
            )
            raise PipelineFailure(
                "IMAGE_DESCRIPTION_FAILED",
                PipelineStep.IMAGE_ERROR,
                f"Image analysis failed for {image.image_id} "
                f"({error.__class__.__name__}).",
            ) from error
        if description.image_id != image.image_id:
            raise PipelineFailure(
                "IMAGE_DESCRIPTION_INVALID",
                PipelineStep.IMAGE_ERROR,
                f"Image analysis returned an unexpected id for {image.image_id}.",
            )
        descriptions.append(description)
    return descriptions


def _extract_entities(
    provider: LLMProvider,
    parsed_document: ParsedDocument,
    image_descriptions: list[ImageDescription],
) -> ExtractionResult:
    try:
        extracted = provider.extract_entities(
            parsed_document.markdown, image_descriptions
        )
    except LLMConfigurationError:
        raise
    except TokenBudgetExceeded as error:
        raise PipelineFailure(
            "TOKEN_LIMIT_EXCEEDED",
            PipelineStep.EXTRACTION_ERROR,
            str(error),
        ) from error
    except LLMResponseError as error:
        raise PipelineFailure(
            "ENTITY_EXTRACTION_FAILED",
            PipelineStep.EXTRACTION_ERROR,
            str(error),
        ) from error
    except LLMProviderError as error:
        raise PipelineFailure(
            "ENTITY_EXTRACTION_FAILED",
            PipelineStep.EXTRACTION_ERROR,
            str(error),
        ) from error
    except Exception as error:
        logger.exception("unexpected_entity_extraction_error")
        raise PipelineFailure(
            "ENTITY_EXTRACTION_FAILED",
            PipelineStep.EXTRACTION_ERROR,
            f"Entity extraction failed ({error.__class__.__name__}).",
        ) from error
    return extracted


def _validate_extraction(
    extracted: ExtractionResult,
    parsed_document: ParsedDocument,
    image_descriptions: list[ImageDescription],
) -> ExtractionResult:
    try:
        return validate_extraction_result(
            extracted,
            parsed_document.markdown,
            image_descriptions,
        )
    except (ExtractionValidationError, ValueError) as error:
        raise PipelineFailure(
            "EXTRACTION_VALIDATION_FAILED",
            PipelineStep.VALIDATION_ERROR,
            str(error),
        ) from error


@shared_task(name="documents.parse_pdf")
def parse_pdf_document(document_id: str, job_id: str) -> None:
    document_uuid = UUID(document_id)
    job_uuid = UUID(job_id)
    task_logger = logger.bind(document_id=document_id, job_id=job_id)

    with SessionLocal() as session:
        job = session.get(IngestionJob, job_uuid)
        document = session.get(Document, document_uuid)
        if job is None or document is None:
            task_logger.error("ingestion_records_not_found")
            return
        if job.status in {
            IngestionStatus.AWAITING_PERSISTENCE.value,
            IngestionStatus.COMPLETED.value,
            IngestionStatus.FAILED.value,
        }:
            task_logger.info("skipping_finished_ingestion_job", status=job.status)
            return

        if job.status == IngestionStatus.QUEUED.value:
            transition_job(job, IngestionStatus.PROCESSING)
        elif job.status != IngestionStatus.PROCESSING.value:
            raise ValueError(f"Cannot process a job with status '{job.status}'.")
        _set_step(job, PipelineStep.PARSING_PDF, 10)
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.attempt += 1
        job.error_code = None
        job.error_message = None
        session.commit()
        task_logger.info("ingestion_job_started", attempt=job.attempt)

        try:
            parsed_document = _parse_document(document.original_file)
            job.extracted_text = parsed_document.markdown
            job.document_manifest = parsed_document.manifest
            _set_step(job, PipelineStep.DESCRIBING_IMAGES, 35)
            session.commit()

            try:
                def persist_token_usage(tokens_consumed: int) -> None:
                    job.tokens_consumed = tokens_consumed
                    session.commit()

                token_budget = TokenBudget(
                    limit=job.token_budget_limit,
                    used=job.tokens_consumed,
                    on_change=persist_token_usage,
                )
                provider = get_llm_provider(token_budget)
            except LLMConfigurationError as error:
                raise PipelineFailure(
                    "LLM_CREDENTIALS_MISSING",
                    PipelineStep.CONFIGURATION_ERROR,
                    str(error),
                ) from error

            image_descriptions = (
                _describe_images(provider, parsed_document)
                if get_settings().analyze_document_images
                else []
            )
            job.image_descriptions = [
                description.model_dump(mode="json")
                for description in image_descriptions
            ]
            _set_step(job, PipelineStep.EXTRACTING_ENTITIES, 60)
            session.commit()

            extracted = _extract_entities(
                provider, parsed_document, image_descriptions
            )
            _set_step(job, PipelineStep.VALIDATING_EXTRACTION, 80)
            session.commit()
            extraction_result = _validate_extraction(
                extracted, parsed_document, image_descriptions
            )
            job.extraction_result = extraction_result.model_dump(mode="json")
            transition_job(job, IngestionStatus.AWAITING_PERSISTENCE)
            _set_step(job, PipelineStep.AWAITING_PERSISTENCE, 90)
            job.error_code = None
            job.error_message = None
            session.commit()
        except PipelineFailure as error:
            session.rollback()
            failed_job = session.get(IngestionJob, job_uuid)
            if failed_job is not None:
                _mark_failed(
                    session,
                    failed_job,
                    error.code,
                    error.step,
                    str(error),
                )
            task_logger.error(
                "document_ingestion_failed",
                step=error.step.value,
                error_code=error.code,
            )
            raise
        except Exception as error:
            session.rollback()
            failed_job = session.get(IngestionJob, job_uuid)
            if failed_job is not None:
                _mark_failed(
                    session,
                    failed_job,
                    "PIPELINE_INTERNAL_ERROR",
                    PipelineStep.PIPELINE_ERROR,
                    "An unexpected error occurred during document processing.",
                )
            task_logger.exception("document_ingestion_failed_unexpectedly")
            raise
        else:
            task_logger.info(
                "document_extraction_completed",
                status=job.status,
                entities_count=len(job.extraction_result["entities"]),
                relationships_count=len(job.extraction_result["relationships"]),
            )
