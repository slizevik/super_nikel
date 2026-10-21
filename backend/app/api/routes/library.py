from datetime import datetime, timezone
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, IngestionJob
from app.db.session import get_db
from app.schemas.documents import LibraryScanResponse
from app.services.library_scanner import (
    LibraryConfigurationError,
    classify_scanned_file,
    scan_library,
)
from app.tasks import parse_pdf_document


router = APIRouter(prefix="/library", tags=["library"])
logger = structlog.get_logger(__name__)


@router.post(
    "/scan",
    response_model=LibraryScanResponse,
    status_code=status.HTTP_200_OK,
)
def scan_document_library(
    session: Session = Depends(get_db),
) -> LibraryScanResponse:
    try:
        scan = scan_library(get_settings().library_root)
    except LibraryConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    library_documents = session.scalars(
        select(Document).where(Document.source_type == "library")
    ).all()
    documents_by_path = {
        document.library_relative_path: document
        for document in library_documents
    }
    latest_jobs: dict[str, str] = {}
    document_ids = [document.id for document in library_documents]
    if document_ids:
        latest_jobs_subquery = (
            select(
                IngestionJob.document_id,
                IngestionJob.status,
                func.row_number()
                .over(
                    partition_by=IngestionJob.document_id,
                    order_by=(
                        IngestionJob.created_at.desc(),
                        IngestionJob.id.desc(),
                    ),
                )
                .label("job_rank"),
            )
            .where(IngestionJob.document_id.in_(document_ids))
            .subquery()
        )
        latest_job_rows = session.execute(
            select(
                latest_jobs_subquery.c.document_id,
                latest_jobs_subquery.c.status,
            ).where(latest_jobs_subquery.c.job_rank == 1)
        ).all()
        latest_jobs = {
            str(document_id): status
            for document_id, status in latest_job_rows
        }

    scheduled: list[tuple[IngestionJob, str]] = []
    changed = 0
    unchanged = 0
    skipped_busy = 0
    for scanned_file in scan.files:
        document = documents_by_path.get(scanned_file.relative_path)
        current_job = (
            latest_jobs.get(str(document.id)) if document is not None else None
        )
        disposition = classify_scanned_file(
            document.sha256 if document is not None else None,
            scanned_file.sha256,
            current_job,
        )
        if disposition == "unchanged":
            unchanged += 1
            continue
        if disposition == "busy":
            skipped_busy += 1
            continue
        if document is None:
            document = Document(
                original_filename=scanned_file.filename,
                mime_type="application/pdf",
                category="Личная библиотека",
                authors=[],
                file_size_bytes=scanned_file.size_bytes,
                sha256=scanned_file.sha256,
                source_type="library",
                library_relative_path=scanned_file.relative_path,
                original_file=None,
            )
            session.add(document)
            session.flush()
        else:
            document.file_size_bytes = scanned_file.size_bytes
            document.sha256 = scanned_file.sha256
            document.original_filename = scanned_file.filename
            if disposition == "changed":
                changed += 1

        job = IngestionJob(
            document_id=document.id,
            status="queued",
            current_step="queued_for_text_extraction",
            token_budget_limit=get_settings().token_limit,
            tokens_consumed=0,
        )
        session.add(job)
        session.flush()
        scheduled.append((job, scanned_file.relative_path))
        latest_jobs[str(document.id)] = job.status

    session.commit()

    errors = [
        f"{error.relative_path}: {error.message}"
        for error in scan.errors
    ]
    queued = 0
    for job, relative_path in scheduled:
        try:
            task = parse_pdf_document.apply_async(
                args=[str(job.document_id), str(job.id)],
                task_id=str(job.id),
            )
        except Exception as error:
            logger.exception(
                "could_not_enqueue_library_document",
                job_id=str(job.id),
                library_relative_path=relative_path,
            )
            job.status = "failed"
            job.current_step = "worker_enqueue_failed"
            job.error_code = "WORKER_UNAVAILABLE"
            job.error_message = (
                "The library document was indexed but could not be queued."
            )
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
            errors.append(f"{relative_path}: processing could not be queued.")
            continue
        job.celery_task_id = task.id
        session.commit()
        queued += 1

    logger.info(
        "library_scan_completed",
        discovered=len(scan.files),
        queued=queued,
        changed=changed,
        unchanged=unchanged,
        skipped_busy=skipped_busy,
        error_count=len(errors),
    )
    return LibraryScanResponse(
        discovered=len(scan.files),
        queued=queued,
        changed=changed,
        unchanged=unchanged,
        skipped_busy=skipped_busy,
        errors=errors,
    )
