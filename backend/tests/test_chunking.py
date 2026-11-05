from app.services.chunking import build_chunks
from app.services.pdf_parser import ParsedTextBlock


def block(text: str, page: int, heading: str | None = None, index: int = 0):
    return ParsedTextBlock(
        text=text,
        page_number=page,
        bbox=None,
        heading=heading,
        block_index=index,
    )


def test_build_chunks_preserves_pages_heading_and_order() -> None:
    chunks = build_chunks(
        [
            block("Introduction explains the problem.", 1, "1 Introduction", 0),
            block("Methods describe the experiment.", 2, "2 Methods", 1),
        ],
        target_tokens=4,
        max_tokens=6,
        overlap_tokens=0,
    )

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert chunks[0].heading == "1 Introduction"
    assert chunks[-1].heading == "2 Methods"
    assert chunks[0].char_start == 0
    assert chunks[1].char_start > chunks[0].char_end


def test_build_chunks_applies_overlap() -> None:
    chunks = build_chunks(
        [block("one two three four five six seven eight", 1, "Section")],
        target_tokens=4,
        max_tokens=4,
        overlap_tokens=2,
    )

    assert chunks[0].content == "one two three four"
    assert chunks[1].content.startswith("three four")


def test_build_chunks_skips_empty_blocks_and_rejects_invalid_parameters() -> None:
    assert build_chunks([block("  ", 1)]) == []

    try:
        build_chunks([], target_tokens=0)
    except ValueError as error:
        assert "Invalid" in str(error)
    else:
        raise AssertionError("Expected invalid chunking parameters to fail")
