from uuid import uuid4

from app.services.chunk_indexing import build_indexed_chunks, replace_document_chunks
from app.services.embeddings import FakeEmbeddingProvider
from app.services.pdf_parser import ParsedTextBlock


def make_block(text: str) -> ParsedTextBlock:
    return ParsedTextBlock(text, 2, None, "2 Methods", 0)


def test_build_indexed_chunks_embeds_in_batches() -> None:
    provider = FakeEmbeddingProvider(dimensions=8)
    blocks = [make_block("one two three four five six")]

    indexed = build_indexed_chunks(
        blocks,
        provider,
        batch_size=1,
        target_tokens=3,
        max_tokens=4,
        overlap_tokens=0,
    )

    assert len(indexed) == 2
    assert all(len(vector) == 8 for _draft, vector in indexed)


class FakeSession:
    def __init__(self) -> None:
        self.deleted = False
        self.added = []

    def execute(self, _statement) -> None:
        self.deleted = True

    def add_all(self, values) -> None:
        self.added.extend(values)


def test_replace_document_chunks_prepares_before_replacing() -> None:
    session = FakeSession()
    provider = FakeEmbeddingProvider(dimensions=8)
    document_id = uuid4()

    count = replace_document_chunks(
        session,
        document_id,
        [make_block("one two three four")],
        provider,
        target_tokens=3,
        max_tokens=4,
        overlap_tokens=0,
    )

    assert count == 2
    assert session.deleted
    assert len(session.added) == count
    assert session.added[0].document_id == document_id
    assert session.added[0].chunk_metadata["chunker_version"] == "v1"
    assert session.added[0].embedding_model == "fake"
