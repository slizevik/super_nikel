from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import chats
from app.db.models import ChatMessage, ChatSession
from app.schemas.answers import AskQuestionResponse
from app.schemas.chats import ChatMessageCreate


class FakeSession:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.chat = ChatSession(
            id=uuid4(),
            title="29.10.2026 · Новый чат",
            created_at=now,
            updated_at=now,
        )
        self.added = []
        self.commits = 0

    def get(self, model, _chat_id):
        return self.chat if model is ChatSession else None

    def add(self, instance) -> None:
        self.added.append(instance)

    def delete(self, instance) -> None:
        self.deleted = instance

    def commit(self) -> None:
        self.commits += 1

    def execute(self, _statement):
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.chat,
            all=lambda: [(self.chat, len(self.chat.messages))],
        )


def test_create_chat_persists_session_with_date_title() -> None:
    session = FakeSession()

    result = chats.create_chat(session)
    created_chat = session.added[0]

    assert result.id == created_chat.id
    assert result.title.startswith(datetime.now().strftime("%d.%m.%Y"))
    assert result.message_count == 0
    assert session.added == [created_chat]
    assert session.commits == 1


def test_delete_chat_removes_session_and_commits() -> None:
    session = FakeSession()

    result = chats.delete_chat(session.chat.id, session)

    assert result is None
    assert session.deleted is session.chat
    assert session.commits == 1


def test_list_chats_and_restore_saved_messages() -> None:
    session = FakeSession()
    message = ChatMessage(
        id=uuid4(),
        chat_id=session.chat.id,
        question="What datasets are used?",
        answer="The article uses RNALocate.",
        translated_question=None,
        citations=[],
        created_at=datetime.now(timezone.utc),
    )
    session.chat.messages.append(message)

    listed = chats.list_chats(session)
    restored = chats.get_chat(session.chat.id, session)

    assert listed[0].id == session.chat.id
    assert listed[0].message_count == 1
    assert restored.messages[0].question == message.question
    assert restored.messages[0].answer == message.answer


def test_first_chat_message_is_saved_and_model_titles_chat(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(
        chats,
        "answer_library_question",
        lambda request, db: AskQuestionResponse(
            answer="В статье используется RNALocate.",
            citations=[],
            translated_question="Which dataset is used?",
        ),
    )
    monkeypatch.setattr(
        chats,
        "get_settings",
        lambda: SimpleNamespace(token_limit=100_000),
    )

    class FakeProvider:
        def suggest_chat_title(self, question: str):
            assert question == "Какие статьи используют RNALocate?"
            return SimpleNamespace(title="Статьи о RNALocate")

    monkeypatch.setattr(
        chats,
        "create_llm_provider",
        lambda settings, budget: FakeProvider(),
    )

    response = chats.add_chat_message(
        session.chat.id,
        ChatMessageCreate(question="Какие статьи используют RNALocate?"),
        session,
    )

    saved_message = next(
        item for item in session.added if isinstance(item, ChatMessage)
    )
    assert session.chat.title.endswith(" · Статьи о RNALocate")
    assert response.answer == "В статье используется RNALocate."
    assert response.translated_question == "Which dataset is used?"
    assert saved_message.question == "Какие статьи используют RNALocate?"
    assert saved_message.citations == []
    assert session.commits == 1


def test_title_generation_failure_uses_question_fallback(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(
        chats,
        "answer_library_question",
        lambda request, db: AskQuestionResponse(
            answer="Ответ по источникам.",
            citations=[],
        ),
    )
    monkeypatch.setattr(
        chats,
        "get_settings",
        lambda: SimpleNamespace(token_limit=100_000),
    )

    def fail_provider(settings, budget):
        raise chats.LLMProviderError("Provider unavailable.")

    monkeypatch.setattr(chats, "create_llm_provider", fail_provider)

    chats.add_chat_message(
        session.chat.id,
        ChatMessageCreate(question="Какие статьи используют RNALocate?"),
        session,
    )

    assert session.chat.title.endswith(" · статьи используют RNALocate")
    assert len(session.added) == 1
