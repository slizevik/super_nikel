from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.pipeline import IngestionStatus, PipelineStep
from app.db.models import Document, IngestionJob
from app.schemas.extraction import (
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
    ImageDescription,
    ImageKind,
    RelationshipType,
)
from app.services.llm.base import LLMConfigurationError
from app.services.pdf_parser import ParsedDocument
from app.tasks import PipelineFailure, parse_pdf_document


class FakeSession:
    def __init__(self, document, job) -> None:
        self.document = document
        self.job = job
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        pass

    def get(self, model, _identifier):
        if model is Document:
            return self.document
        if model is IngestionJob:
            return self.job
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass


class MockLLMProvider:
    def __init__(self) -> None:
        self.images: list[str] = []
        self.raw_responses: list[str] = []

    def describe_image(self, image, _document_context):
        self.images.append(image.image_id)
        return ImageDescription(
            image_id=image.image_id,
            kind=ImageKind.CHART,
            useful=True,
            description="Nickel recovery increases with temperature.",
            key_information="Recovery rises with temperature.",
            caption=image.caption,
        )

    def extract_entities(
        self,
        _document_text,
        image_descriptions,
        on_raw_response=None,
    ):
        assert len(image_descriptions) == len(self.images)
        result = ExtractionResult(
            entities=[
                ExtractedEntity(
                    id="process-1",
                    type=EntityType.PROCESS,
                    label="Nickel leaching",
                    canonical_label="Nickel leaching",
                    evidence="Nickel leaching was studied.",
                ),
                ExtractedEntity(
                    id="material-1",
                    type=EntityType.MATERIAL,
                    label="nickel ore",
                    canonical_label="nickel ore",
                    evidence="Nickel leaching used nickel ore.",
                ),
            ],
            relationships=[
                ExtractedRelationship(
                    source_id="process-1",
                    target_id="material-1",
                    type=RelationshipType.USES_MATERIAL,
                    evidence="Nickel leaching used nickel ore.",
                )
            ],
            unclassified_entities=[
                {
                    "text": "heap",
                    "context": "Nickel leaching used nickel ore.",
                }
            ],
        )
        if on_raw_response is not None:
            raw_response = result.model_dump_json()
            self.raw_responses.append(raw_response)
            on_raw_response(raw_response)
        return result


def setup_task_session(monkeypatch, parsed_output_dir: Path, parsed_document=None):
    document = SimpleNamespace(original_file=b"%PDF-1.7")
    job = SimpleNamespace(
        status=IngestionStatus.QUEUED.value,
        current_step="queued",
        progress_percent=0,
        attempt=0,
        extracted_text=None,
        document_manifest=None,
        image_descriptions=None,
        extraction_result=None,
        token_budget_limit=100_000,
        tokens_consumed=0,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )
    session = FakeSession(document, job)
    monkeypatch.setattr("app.tasks.SessionLocal", lambda: session)
    monkeypatch.setattr(
        "app.tasks.get_settings",
        lambda: SimpleNamespace(
            analyze_document_images=True,
            parsed_documents_dir=str(parsed_output_dir),
        ),
    )
    monkeypatch.setattr(
        "app.tasks._parse_document",
        lambda _pdf_bytes: parsed_document
        or ParsedDocument(
            markdown=(
                "# Nickel leaching\n"
                "Nickel leaching was studied. Nickel leaching used nickel ore. "
                "Nickel ore was tested."
            ),
            images=[],
            manifest={"format": "pdf", "page_count": 1, "images": []},
        ),
    )
    return session, job


def test_pipeline_saves_docling_markdown_and_stops_before_persistence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session, job = setup_task_session(monkeypatch, tmp_path)
    provider = MockLLMProvider()
    monkeypatch.setattr("app.tasks.get_llm_provider", lambda _budget: provider)
    document_id = uuid4()

    parse_pdf_document.run(str(document_id), str(uuid4()))

    assert job.status == IngestionStatus.AWAITING_PERSISTENCE.value
    assert job.current_step == "awaiting_persistence"
    assert job.progress_percent == 90
    assert job.extracted_text.startswith("# Nickel leaching")
    assert (tmp_path / f"{document_id}.md").read_text(encoding="utf-8") == (
        job.extracted_text
    )
    assert (
        tmp_path / f"{document_id}.llm-response.txt"
    ).read_text(encoding="utf-8") == provider.raw_responses[0]
    assert job.document_manifest["page_count"] == 1
    assert len(job.extraction_result["entities"]) == 2
    assert job.extraction_result["unclassified_entities"][0]["text"] == "heap"
    assert job.finished_at is None
    assert session.commits == 5


def test_pipeline_describes_docling_images_before_entity_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.services.pdf_parser import ParsedImage

    parsed = ParsedDocument(
        markdown=(
            "# Nickel leaching\n"
            "Nickel leaching was studied. Nickel leaching used nickel ore. "
            "Nickel ore was tested."
        ),
        images=[
            ParsedImage(
                image_id="image-0001",
                content=b"image",
                media_type="image/png",
                caption="Recovery chart",
                page_numbers=[1],
                width=10,
                height=10,
            )
        ],
        manifest={
            "format": "pdf",
            "page_count": 1,
            "image_count": 1,
            "images": [{"image_id": "image-0001", "caption": "Recovery chart"}],
        },
    )
    session, job = setup_task_session(monkeypatch, tmp_path, parsed)
    provider = MockLLMProvider()
    monkeypatch.setattr("app.tasks.get_llm_provider", lambda _budget: provider)

    parse_pdf_document.run(str(uuid4()), str(uuid4()))

    assert provider.images == ["image-0001"]
    assert job.image_descriptions[0]["image_id"] == "image-0001"
    assert job.status == IngestionStatus.AWAITING_PERSISTENCE.value
    assert session.commits == 5


def test_missing_yandex_credentials_fails_job_explicitly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session, job = setup_task_session(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.tasks.get_llm_provider",
        lambda _budget: (_ for _ in ()).throw(
            LLMConfigurationError(
                "YANDEX_CLOUD_API_KEY is missing. Configure local credentials."
            )
        ),
    )

    with pytest.raises(PipelineFailure, match="YANDEX_CLOUD_API_KEY is missing"):
        parse_pdf_document.run(str(uuid4()), str(uuid4()))

    assert job.status == IngestionStatus.FAILED.value
    assert job.current_step == "llm_configuration"
    assert job.error_code == "LLM_CREDENTIALS_MISSING"
    assert "YANDEX_CLOUD_API_KEY" in job.error_message
    assert job.extracted_text
    assert session.commits == 3


def test_docling_failure_is_reported_at_parsing_step(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session, job = setup_task_session(monkeypatch, tmp_path)

    monkeypatch.setattr(
        "app.tasks._parse_document",
        lambda _pdf_bytes: (_ for _ in ()).throw(
            PipelineFailure(
                "PDF_PARSING_FAILED",
                PipelineStep.PARSING_ERROR,
                "Corrupt PDF structure.",
            )
        ),
    )
    monkeypatch.setattr(
        "app.tasks.get_llm_provider",
        lambda _budget: pytest.fail(
            "LLM provider must not be initialized after parse failure"
        ),
    )

    with pytest.raises(PipelineFailure, match="Corrupt PDF structure"):
        parse_pdf_document.run(str(uuid4()), str(uuid4()))

    assert job.status == IngestionStatus.FAILED.value
    assert job.current_step == "pdf_parsing_failed"
    assert job.error_code == "PDF_PARSING_FAILED"
    assert session.commits == 2


def test_markdown_save_failure_fails_job_explicitly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session, job = setup_task_session(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.tasks.save_parsed_markdown",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("storage is unavailable")
        ),
    )
    monkeypatch.setattr(
        "app.tasks.get_llm_provider",
        lambda _budget: pytest.fail("LLM must not run if Markdown save fails"),
    )

    with pytest.raises(PipelineFailure, match="Could not save the Docling Markdown"):
        parse_pdf_document.run(str(uuid4()), str(uuid4()))

    assert job.status == IngestionStatus.FAILED.value
    assert job.current_step == "parsed_document_save_failed"
    assert job.error_code == "PARSED_DOCUMENT_SAVE_FAILED"


def test_raw_model_response_save_failure_fails_job_explicitly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session, job = setup_task_session(monkeypatch, tmp_path)
    provider = MockLLMProvider()
    monkeypatch.setattr("app.tasks.get_llm_provider", lambda _budget: provider)
    monkeypatch.setattr(
        "app.tasks.save_model_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("storage is unavailable")
        ),
    )

    with pytest.raises(PipelineFailure, match="Could not save the raw LLM"):
        parse_pdf_document.run(str(uuid4()), str(uuid4()))

    assert job.status == IngestionStatus.FAILED.value
    assert job.current_step == "model_response_save_failed"
    assert job.error_code == "MODEL_RESPONSE_SAVE_FAILED"
