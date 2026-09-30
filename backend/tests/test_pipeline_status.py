import pytest

from app.core.pipeline import IngestionStatus, transition_job


def test_pipeline_allows_queue_to_processing_and_pending_persistence() -> None:
    job = type("Job", (), {"status": IngestionStatus.QUEUED.value})()

    transition_job(job, IngestionStatus.PROCESSING)
    transition_job(job, IngestionStatus.AWAITING_PERSISTENCE)

    assert job.status == "awaiting_persistence"


def test_pipeline_rejects_direct_success_before_persistence() -> None:
    job = type("Job", (), {"status": IngestionStatus.PROCESSING.value})()

    with pytest.raises(ValueError, match="processing -> completed"):
        transition_job(job, IngestionStatus.COMPLETED)


def test_terminal_job_cannot_transition_back_to_processing() -> None:
    job = type("Job", (), {"status": IngestionStatus.FAILED.value})()

    with pytest.raises(ValueError, match="failed -> processing"):
        transition_job(job, IngestionStatus.PROCESSING)
