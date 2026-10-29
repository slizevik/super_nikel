import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import answers
from app.schemas.answers import AnswerDraft, AskQuestionRequest


class FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows

    def execute(self, _statement):
        return SimpleNamespace(all=lambda: self.rows)


def test_answer_library_question_uses_retrieved_library_sources(monkeypatch) -> None:
    document_id = uuid4()
    rows = [
        (
            document_id,
            "mRNA-localization.pdf",
            "cell/mRNA-localization.pdf",
            "Full extracted article text.",
            "Relevant excerpt about mRNA localization.",
            0.42,
        )
    ]
    captured_context = {}

    class FakeProvider:
        def answer_question(self, question: str, context: str) -> AnswerDraft:
            captured_context["question"] = question
            captured_context["sources"] = json.loads(context)
            return AnswerDraft(
                answer="The article describes RNA localization.",
                cited_document_ids=[document_id],
            )

    monkeypatch.setattr(
        answers,
        "get_settings",
        lambda: SimpleNamespace(
            token_limit=100_000,
            library_root=Path("/library"),
            library_display_root=r"C:\develop\articles",
        ),
    )
    monkeypatch.setattr(
        answers,
        "create_llm_provider",
        lambda settings, budget: FakeProvider(),
    )

    result = answers.answer_library_question(
        AskQuestionRequest(question="How is mRNA localized?"),
        FakeSession(rows),
    )

    assert result.answer == "The article describes RNA localization."
    assert result.citations[0].document_id == document_id
    assert result.citations[0].source_path == (
        r"C:\develop\articles\cell\mRNA-localization.pdf"
    )
    assert captured_context["question"] == "How is mRNA localized?"
    assert captured_context["sources"][0]["document_id"] == str(document_id)


def test_russian_question_is_translated_and_answered_in_russian(monkeypatch) -> None:
    document_id = uuid4()
    rows = [
        (
            document_id,
            "dataset-study.pdf",
            "ml/dataset-study.pdf",
            "The model was trained using the RNALocate dataset.",
            "The model was trained using the RNALocate dataset.",
            0.42,
        )
    ]

    class FakeProvider:
        def translate_question_to_english(self, question: str) -> str:
            assert question == "Какие датасеты использовались для обучения?"
            return "Which datasets were used for training?"

        def answer_question(self, question: str, context: str) -> AnswerDraft:
            assert question == "Какие датасеты использовались для обучения?"
            assert "RNALocate dataset" in context
            return AnswerDraft(
                answer="В статье для обучения использовался RNALocate.",
                cited_document_ids=[document_id],
            )

    monkeypatch.setattr(
        answers,
        "get_settings",
        lambda: SimpleNamespace(
            token_limit=100_000,
            library_root=Path("/library"),
            library_display_root=r"C:\develop\articles",
        ),
    )
    monkeypatch.setattr(
        answers,
        "create_llm_provider",
        lambda settings, budget: FakeProvider(),
    )

    result = answers.answer_library_question(
        AskQuestionRequest(question="Какие датасеты использовались для обучения?"),
        FakeSession(rows),
    )

    assert result.translated_question == "Which datasets were used for training?"
    assert "RNALocate" in result.answer
    assert result.citations[0].document_id == document_id


def test_answer_library_question_does_not_call_llm_without_search_results(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        answers,
        "get_settings",
        lambda: SimpleNamespace(token_limit=100_000),
    )
    monkeypatch.setattr(
        answers,
        "create_llm_provider",
        lambda settings, budget: pytest.fail("LLM should not be called"),
    )

    result = answers.answer_library_question(
        AskQuestionRequest(question="Where is mRNA localized?"),
        FakeSession([]),
    )

    assert result.citations == []
    assert "не найдено" in result.answer


def test_answer_library_question_rejects_unknown_citation(monkeypatch) -> None:
    document_id = uuid4()
    rows = [
        (
            document_id,
            "article.pdf",
            "article.pdf",
            "Article text.",
            "Relevant excerpt.",
            0.25,
        )
    ]

    class FakeProvider:
        def answer_question(self, question: str, context: str) -> AnswerDraft:
            return AnswerDraft(
                answer="Unsupported citation.",
                cited_document_ids=[uuid4()],
            )

    monkeypatch.setattr(
        answers,
        "get_settings",
        lambda: SimpleNamespace(
            token_limit=100_000,
            library_display_root=r"C:\develop\articles",
        ),
    )
    monkeypatch.setattr(
        answers,
        "create_llm_provider",
        lambda settings, budget: FakeProvider(),
    )

    with pytest.raises(HTTPException) as error:
        answers.answer_library_question(
            AskQuestionRequest(question="What is in this article?"),
            FakeSession(rows),
        )
    assert error.value.status_code == 502


def test_answer_library_question_rejects_duplicate_citations(monkeypatch) -> None:
    document_id = uuid4()
    rows = [
        (
            document_id,
            "article.pdf",
            "article.pdf",
            "Article text.",
            "Relevant excerpt.",
            0.25,
        )
    ]

    class FakeProvider:
        def answer_question(self, question: str, context: str):
            return {
                "answer": "Repeated citation.",
                "cited_document_ids": [str(document_id), str(document_id)],
            }

    monkeypatch.setattr(
        answers,
        "get_settings",
        lambda: SimpleNamespace(
            token_limit=100_000,
            library_display_root=r"C:\develop\articles",
        ),
    )
    monkeypatch.setattr(
        answers,
        "create_llm_provider",
        lambda settings, budget: FakeProvider(),
    )

    with pytest.raises(HTTPException) as error:
        answers.answer_library_question(
            AskQuestionRequest(question="What is in this article?"),
            FakeSession(rows),
        )
    assert error.value.status_code == 502
