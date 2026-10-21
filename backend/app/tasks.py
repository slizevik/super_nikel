import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

import structlog
from celery import shared_task

from app.core.config import get_settings
from app.core.pipeline import (
    IngestionStatus,
    PipelineStep,
    complete_indexing_job,
    transition_job,
)
from app.db.models import Document, IngestionJob
from app.db.session import SessionLocal
from app.schemas.extraction import (
    ExtractionCandidates,
    ExtractionResult,
    ImageDescription,
)
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
from app.services.parsed_document_storage import (
    save_model_response,
    save_parsed_images,
    save_parsed_markdown,
)
from app.services.library_scanner import (
    LibraryConfigurationError,
    LibraryFileError,
    resolve_library_file,
)
from app.services.document_conversion import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    DocxConversionError,
    convert_docx_to_pdf,
)
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
    maximum_images: int,
) -> list[ImageDescription]:
    descriptions: list[ImageDescription] = []
    selected_images = parsed_document.images[:maximum_images]
    skipped_images = len(parsed_document.images) - len(selected_images)
    if skipped_images:
        logger.info(
            "image_analysis_limit_applied",
            selected_images=len(selected_images),
            skipped_images=skipped_images,
        )
    for image in selected_images:
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
    on_raw_response: Callable[[str], None] | None = None,
) -> ExtractionCandidates:
    try:
        extracted = provider.extract_entities(
            parsed_document.markdown,
            image_descriptions,
            on_raw_response=on_raw_response,
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
    except OSError as error:
        raise PipelineFailure(
            "MODEL_RESPONSE_SAVE_FAILED",
            PipelineStep.MODEL_RESPONSE_SAVE_ERROR,
            "Could not save the raw LLM extraction response.",
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
    extracted: ExtractionCandidates,
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
        is_docx = document.mime_type == DOCX_MIME_TYPE
        _set_step(
            job,
            PipelineStep.CONVERTING_DOCX if is_docx else PipelineStep.PARSING_PDF,
            5 if is_docx else 10,
        )
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.attempt += 1
        job.error_code = None
        job.error_message = None
        session.commit()
        task_logger.info("ingestion_job_started", attempt=job.attempt)

        try:
            is_library_document = (
                getattr(document, "source_type", "upload") == "library"
            )
            if is_library_document:
                settings = get_settings()
                try:
                    library_path = resolve_library_file(
                        settings.library_root,
                        document.library_relative_path or "",
                    )
                    pdf_bytes = library_path.read_bytes()
                except (LibraryConfigurationError, LibraryFileError, OSError) as error:
                    raise PipelineFailure(
                        "LIBRARY_FILE_UNAVAILABLE",
                        PipelineStep.PARSING_ERROR,
                        "The indexed library file is unavailable or outside "
                        "the configured library.",
                    ) from error
                if hashlib.sha256(pdf_bytes).hexdigest() != document.sha256:
                    raise PipelineFailure(
                        "LIBRARY_FILE_CHANGED",
                        PipelineStep.PARSING_ERROR,
                        "The library file changed after scanning. "
                        "Scan the library again.",
                    )
            else:
                pdf_bytes = document.original_file
                if pdf_bytes is None:
                    raise PipelineFailure(
                        "DOCUMENT_SOURCE_MISSING",
                        PipelineStep.PARSING_ERROR,
                        "The uploaded document has no stored file content.",
                    )
            if is_docx:
                settings = get_settings()
                try:
                    converted_pdf_path = convert_docx_to_pdf(
                        document.original_file,
                        str(document_uuid),
                        settings.converted_pdf_dir,
                        settings.libreoffice_binary,
                        settings.libreoffice_timeout_sec,
                    )
                    pdf_bytes = converted_pdf_path.read_bytes()
                except (DocxConversionError, OSError) as error:
                    raise PipelineFailure(
                        "DOCX_CONVERSION_FAILED",
                        PipelineStep.DOCX_CONVERSION_ERROR,
                        str(error),
                    ) from error
                task_logger.info(
                    "docx_converted_to_pdf",
                    output_path=str(converted_pdf_path),
                    pdf_size_bytes=len(pdf_bytes),
                )
                _set_step(job, PipelineStep.PARSING_PDF, 10)
                session.commit()
            elif document.mime_type != PDF_MIME_TYPE:
                raise PipelineFailure(
                    "UNSUPPORTED_DOCUMENT_FORMAT",
                    PipelineStep.DOCX_CONVERSION_ERROR,
                    f"Unsupported document media type: {document.mime_type}.",
                )

            parsed_document = _parse_document(pdf_bytes)
            try:
                parsed_markdown_path = save_parsed_markdown(
                    parsed_document.markdown,
                    document_uuid,
                    get_settings().parsed_documents_dir,
                )
            except OSError as error:
                raise PipelineFailure(
                    "PARSED_DOCUMENT_SAVE_FAILED",
                    PipelineStep.PARSED_DOCUMENT_SAVE_ERROR,
                    "Could not save the Docling Markdown output.",
                ) from error
            task_logger.info(
                "parsed_markdown_saved",
                path=str(parsed_markdown_path),
                character_count=len(parsed_document.markdown),
            )
            try:
                persisted_image_paths = save_parsed_images(
                    [
                        (image.image_id, image.content)
                        for image in parsed_document.images
                    ],
                    document_uuid,
                    get_settings().parsed_documents_dir,
                )
            except OSError as error:
                raise PipelineFailure(
                    "PARSED_IMAGES_SAVE_FAILED",
                    PipelineStep.PARSED_DOCUMENT_SAVE_ERROR,
                    "Could not save extracted PDF figures.",
                ) from error
            document_manifest = dict(parsed_document.manifest)
            for image_metadata in document_manifest.get("images", []):
                image_path = persisted_image_paths.get(
                    image_metadata.get("image_id", "")
                )
                if image_path is not None:
                    image_metadata["stored_path"] = image_path
            job.extracted_text = parsed_document.markdown
            job.document_manifest = document_manifest
            if is_library_document:
                complete_indexing_job(job)
                _set_step(job, PipelineStep.INDEXED, 100)
                job.finished_at = datetime.now(timezone.utc)
                job.error_code = None
                job.error_message = None
                session.commit()
                task_logger.info(
                    "library_document_indexed",
                    status=job.status,
                    character_count=len(parsed_document.markdown),
                )
                return
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
                _describe_images(
                    provider,
                    parsed_document,
                    get_settings().max_images_for_llm,
                )
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
                provider,
                parsed_document,
                image_descriptions,
                on_raw_response=lambda response: save_model_response(
                    response,
                    document_uuid,
                    get_settings().parsed_documents_dir,
                ),
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
