from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.pipeline import IngestionStatus
from app.db.models import IngestionJob
from app.db.session import get_db
from app.schemas.documents import IngestionJobResponse, JobStatusResponse


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=IngestionJobResponse)
def get_job_status(
    job_id: UUID,
    session: Session = Depends(get_db),
) -> IngestionJobResponse:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return IngestionJobResponse.model_validate(job)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status_compatible(
    job_id: UUID,
    session: Session = Depends(get_db),
) -> JobStatusResponse:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return JobStatusResponse(
        **IngestionJobResponse.model_validate(job).model_dump(),
        is_terminal=job.status
        in {IngestionStatus.COMPLETED.value, IngestionStatus.FAILED.value},
        is_success=job.status == IngestionStatus.COMPLETED.value,
    )
