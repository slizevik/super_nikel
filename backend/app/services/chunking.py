"""Deterministic, page-aware text chunking for indexed documents."""

from dataclasses import dataclass
import re
from collections.abc import Sequence

from app.services.pdf_parser import ParsedTextBlock


@dataclass(frozen=True)
class DocumentChunkDraft:
    chunk_index: int
    content: str
    token_count: int
    page_start: int
    page_end: int
    heading: str | None
    char_start: int
    char_end: int


def _tokens(text: str) -> list[str]:
    return re.findall(r"\S+", text.strip())


def _token_count(text: str) -> int:
    return len(_tokens(text))


def build_chunks(
    blocks: Sequence[ParsedTextBlock],
    *,
    target_tokens: int = 600,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[DocumentChunkDraft]:
    """Build stable chunks while retaining source pages and section headings.

    The implementation uses whitespace tokens intentionally.  A tokenizer
    adapter can replace this later without changing the chunk contract.
    """
    if (
        target_tokens <= 0
        or max_tokens < target_tokens
        or overlap_tokens < 0
        or overlap_tokens >= max_tokens
    ):
        raise ValueError("Invalid chunking parameters.")

    prepared = [block for block in blocks if block.text.strip()]
    chunks: list[DocumentChunkDraft] = []
    current: list[tuple[ParsedTextBlock, str]] = []
    current_tokens = 0
    source_cursor = 0

    def emit(items: list[tuple[ParsedTextBlock, str]]) -> None:
        nonlocal source_cursor
        if not items:
            return
        content = "\n\n".join(text for _, text in items).strip()
        if not content:
            return
        first, last = items[0][0], items[-1][0]
        char_start = source_cursor
        char_end = char_start + len(content)
        chunks.append(
            DocumentChunkDraft(
                chunk_index=len(chunks),
                content=content,
                token_count=_token_count(content),
                page_start=first.page_number,
                page_end=last.page_number,
                heading=first.heading,
                char_start=char_start,
                char_end=char_end,
            )
        )
        source_cursor = char_end + 2

    for block in prepared:
        words = _tokens(block.text)
        while words:
            room = max_tokens - current_tokens
            take = min(len(words), room)
            if take <= 0:
                emit(current)
                overlap = _tokens(current[-1][1])[-overlap_tokens:] if overlap_tokens else []
                current = [(current[-1][0], " ".join(overlap))] if overlap else []
                current_tokens = len(overlap)
                continue

            part = " ".join(words[:take])
            current.append((block, part))
            current_tokens += take
            words = words[take:]

            if current_tokens >= target_tokens:
                emit(current)
                overlap = _tokens(current[-1][1])[-overlap_tokens:] if overlap_tokens else []
                current = [(current[-1][0], " ".join(overlap))] if overlap else []
                current_tokens = len(overlap)

    emit(current)
    return chunks
