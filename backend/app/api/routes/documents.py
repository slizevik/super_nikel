import hashlib
from io import BytesIO
from pathlib import PurePath
from urllib.parse import quote
from uuid import UUID
from zipfile import BadZipFile, ZipFile

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, IngestionJob
from app.db.session import get_db
from app.services.document_conversion import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    PDF_SIGNATURE,
)
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUploadResponse,
    IngestionJobResponse,
)
from app.tasks import parse_pdf_document


router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_CHUNK_BYTES = 1024 * 1024
logger = structlog.get_logger(__name__)


async def read_document_upload(file: UploadFile) -> tuple[str, str, bytes]:
    try:
        filename = PurePath(file.filename or "").name
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        extension = PurePath(filename).suffix.lower()
        mime_type = {
            ".pdf": PDF_MIME_TYPE,
            ".docx": DOCX_MIME_TYPE,
        }.get(extension)
        if not filename or mime_type is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF and DOCX files are supported.",
            )

        maximum_size = get_settings().max_upload_size_bytes
        contents = bytearray()
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            contents.extend(chunk)
            if len(contents) > maximum_size:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=(
                        f"Document exceeds the {maximum_size}-byte upload limit."
                    ),
                )

        document_bytes = bytes(contents)
        if mime_type == PDF_MIME_TYPE and not document_bytes.startswith(
            PDF_SIGNATURE
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded file does not have a valid PDF signature.",
            )
        if mime_type == DOCX_MIME_TYPE:
            try:
                with ZipFile(BytesIO(document_bytes)) as archive:
                    if not {
                        "[Content_Types].xml",
                        "word/document.xml",
                    }.issubset(archive.namelist()):
                        raise BadZipFile("Missing required DOCX package files.")
            except BadZipFile as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="The uploaded file is not a valid DOCX document.",
                ) from error
        return filename[:512], mime_type, document_bytes
    finally:
        await file.close()


@router.post("", response_model=DocumentUploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(min_length=1, max_length=100),
    session: Session = Depends(get_db),
) -> DocumentUploadResponse:
    filename, mime_type, document_bytes = await read_document_upload(file)
    normalized_category = category.strip()
    if not normalized_category:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document category must not be blank.",
        )

    document = Document(
        original_filename=filename,
        mime_type=mime_type,
        category=normalized_category,
        file_size_bytes=len(document_bytes),
        sha256=hashlib.sha256(document_bytes).hexdigest(),
        original_file=document_bytes,
        authors=[],
    )
    job = IngestionJob(
        document=document,
        status="queued",
        current_step="queued_for_text_extraction",
        token_budget_limit=get_settings().token_limit,
        tokens_consumed=0,
    )
    session.add(document)
    session.add(job)
    session.commit()
    session.refresh(document)
    session.refresh(job)

    try:
        task = parse_pdf_document.apply_async(
            args=[str(document.id), str(job.id)],
            task_id=str(job.id),
        )
    except Exception as error:
        logger.exception(
            "could_not_enqueue_pdf_ingestion_job",
            job_id=str(job.id),
            document_id=str(document.id),
        )
        session.rollback()
        job.status = "failed"
        job.current_step = "worker_enqueue_failed"
        job.error_code = "WORKER_UNAVAILABLE"
        job.error_message = "The document was saved, but processing could not be queued."
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": job.error_message,
                "document_id": str(document.id),
                "job_id": str(job.id),
            },
        ) from error

    job.celery_task_id = task.id
    session.commit()
    return DocumentUploadResponse(document=document, job=job)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_db),
) -> list[DocumentResponse]:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100 and offset must be non-negative.",
        )
    documents = session.scalars(
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: UUID,
    session: Session = Depends(get_db),
) -> DocumentDetailResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    job = session.scalar(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Document ingestion job not found.")
    return DocumentDetailResponse(
        document=DocumentResponse.model_validate(document),
        job=IngestionJobResponse.model_validate(job),
        text_extracted=job.extracted_text is not None,
        extracted_text_preview=job.extracted_text[:10_000]
        if job.extracted_text
        else None,
        extracted_text_truncated=len(job.extracted_text or "") > 10_000,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    session: Session = Depends(get_db),
) -> Response:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    filename = quote(document.original_filename, safe="")
    return Response(
        content=document.original_file,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
        },
    )
