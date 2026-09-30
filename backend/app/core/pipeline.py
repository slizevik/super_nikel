from enum import StrEnum


class IngestionStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    AWAITING_PERSISTENCE = "awaiting_persistence"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStep(StrEnum):
    QUEUED = "queued"
    PARSING_PDF = "parsing_pdf"
    DESCRIBING_IMAGES = "describing_images"
    EXTRACTING_ENTITIES = "extracting_entities"
    VALIDATING_EXTRACTION = "validating_extraction"
    AWAITING_PERSISTENCE = "awaiting_persistence"
    CONFIGURATION_ERROR = "llm_configuration"
    PARSING_ERROR = "pdf_parsing_failed"
    IMAGE_ERROR = "image_description_failed"
    EXTRACTION_ERROR = "entity_extraction_failed"
    VALIDATION_ERROR = "extraction_validation_failed"
    PIPELINE_ERROR = "pipeline_failed"


ALLOWED_STATUS_TRANSITIONS = {
    IngestionStatus.QUEUED: {IngestionStatus.PROCESSING, IngestionStatus.FAILED},
    IngestionStatus.PROCESSING: {
        IngestionStatus.AWAITING_PERSISTENCE,
        IngestionStatus.FAILED,
    },
    IngestionStatus.AWAITING_PERSISTENCE: {
        IngestionStatus.PROCESSING,
        IngestionStatus.COMPLETED,
        IngestionStatus.FAILED,
    },
    IngestionStatus.COMPLETED: set(),
    IngestionStatus.FAILED: set(),
}


def transition_job(job, status: IngestionStatus) -> None:
    current = IngestionStatus(job.status)
    if status not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise ValueError(
            f"Invalid ingestion status transition: {current.value} -> {status.value}"
        )
    job.status = status.value
