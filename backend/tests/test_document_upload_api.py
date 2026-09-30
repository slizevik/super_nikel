import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.api.routes import documents
from app.db.models import IngestionJob
from app.main import app


class FakeSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, instance) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        pass

    def refresh(self, instance) -> None:
        if getattr(instance, "id", None) is None:
            instance.id = uuid4()
        if getattr(instance, "created_at", None) is None:
            instance.created_at = datetime.now(timezone.utc)
        if isinstance(instance, IngestionJob):
            instance.document_id = instance.document.id
            instance.progress_percent = 0
            instance.attempt = 0

    def rollback(self) -> None:
        pass

    def get(self, model, identifier):
        return next(
            (
                instance
                for instance in self.added
                if isinstance(instance, model) and str(instance.id) == str(identifier)
            ),
            None,
        )


@pytest.fixture
def client(monkeypatch):
    fake_session = FakeSession()

    def override_get_db():
        yield fake_session

    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(max_upload_size_bytes=1024, token_limit=5000),
    )
    monkeypatch.setattr(
        documents.parse_pdf_document,
        "apply_async",
        lambda args, task_id: SimpleNamespace(id=task_id),
    )
    app.dependency_overrides[documents.get_db] = override_get_db
    yield fake_session
    app.dependency_overrides.clear()


def post_upload(client, filename: str, body: bytes):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            return await test_client.post(
                "/api/v1/documents",
                data={"category": "статья"},
                files={"file": (filename, body, "application/pdf")},
            )

    return asyncio.run(send_request())


def test_upload_accepts_pdf_and_queues_text_extraction(client) -> None:
    response = post_upload(client, "paper.pdf", b"%PDF-1.7 test body")

    assert response.status_code == 202
    body = response.json()
    assert body["document"]["original_filename"] == "paper.pdf"
    assert body["document"]["mime_type"] == "application/pdf"
    assert client.added[0].original_file == b"%PDF-1.7 test body"
    assert client.added[0].sha256
    assert body["job"]["status"] == "queued"
    assert body["job"]["current_step"] == "queued_for_text_extraction"
    assert client.added[1].token_budget_limit == 5000
    assert client.added[1].tokens_consumed == 0
    assert len(client.added) == 2


def test_upload_rejects_non_pdf_extension(client) -> None:
    response = post_upload(client, "paper.docx", b"%PDF-1.7 test body")

    assert response.status_code == 415
    assert client.added == []


def test_upload_rejects_invalid_pdf_signature(client) -> None:
    response = post_upload(client, "paper.pdf", b"not a PDF")

    assert response.status_code == 422
    assert client.added == []


def test_upload_rejects_file_over_configured_limit(client) -> None:
    response = post_upload(client, "paper.pdf", b"%PDF-" + b"x" * 1024)

    assert response.status_code == 413
    assert client.added == []


def test_upload_rejects_blank_category(client) -> None:
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            return await test_client.post(
                "/api/v1/documents",
                data={"category": "   "},
                files={"file": ("paper.pdf", b"%PDF-1.7 test body", "application/pdf")},
            )

    response = asyncio.run(send_request())

    assert response.status_code == 422
    assert client.added == []


def test_job_status_route_reports_nonterminal_extraction_state(client) -> None:
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            uploaded = await test_client.post(
                "/api/v1/documents",
                data={"category": "статья"},
                files={
                    "file": ("paper.pdf", b"%PDF-1.7 test body", "application/pdf")
                },
            )
            job_id = uploaded.json()["job"]["id"]
            job = next(item for item in client.added if isinstance(item, IngestionJob))
            job.status = "awaiting_persistence"
            job.current_step = "awaiting_persistence"
            job.progress_percent = 90
            status_response = await test_client.get(
                f"/api/v1/jobs/{job_id}/status"
            )
            unversioned_status_response = await test_client.get(
                f"/jobs/{job_id}/status"
            )
            legacy_response = await test_client.get(f"/api/v1/jobs/{job_id}")
            return status_response, unversioned_status_response, legacy_response

    status_response, unversioned_status_response, legacy_response = asyncio.run(
        send_request()
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "awaiting_persistence"
    assert status_response.json()["is_terminal"] is False
    assert status_response.json()["is_success"] is False
    assert unversioned_status_response.status_code == 200
    assert unversioned_status_response.json()["is_success"] is False
    assert legacy_response.status_code == 200
