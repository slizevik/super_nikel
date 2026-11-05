from dataclasses import dataclass, field
from io import BytesIO
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import structlog


logger = structlog.get_logger(__name__)


class DoclingParsingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedImage:
    image_id: str
    content: bytes
    media_type: str
    caption: str | None
    page_numbers: list[int]
    width: int
    height: int


@dataclass(frozen=True)
class ParsedTextBlock:
    text: str
    page_number: int
    bbox: tuple[float, float, float, float] | None
    heading: str | None
    block_index: int


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    images: list[ParsedImage]
    manifest: dict[str, Any]
    blocks: list[ParsedTextBlock] = field(default_factory=list)


def _text_blocks(page: Any) -> list[tuple[float, float, float, float, str]]:
    blocks: list[tuple[float, float, float, float, str]] = []
    for block in page.get_text("blocks"):
        if len(block) < 7 or block[6] != 0:
            continue
        text = str(block[4]).strip()
        if text:
            blocks.append(
                (
                    float(block[0]),
                    float(block[1]),
                    float(block[2]),
                    float(block[3]),
                    text,
                )
            )
    return blocks


def _column_gutter(
    blocks: list[tuple[float, float, float, float, str]],
    page_width: float,
) -> float | None:
    candidates = sorted(
        {
            block[2]
            for block in blocks
            if block[2] - block[0] < page_width * 0.72
        }
    )
    best_gutter: float | None = None
    best_gap = page_width * 0.035
    for gutter in candidates:
        if not page_width * 0.25 <= gutter <= page_width * 0.75:
            continue
        left = [
            block
            for block in blocks
            if block[2] <= gutter
            and block[2] - block[0] < page_width * 0.72
        ]
        right = [
            block
            for block in blocks
            if block[0] >= gutter
            and block[2] - block[0] < page_width * 0.72
        ]
        if not left or not right:
            continue
        nearest_right = min(block[0] for block in right)
        gap = nearest_right - gutter
        if gap > best_gap:
            best_gutter = gutter
            best_gap = gap
    return best_gutter


def _ordered_page_blocks(page: Any) -> list[tuple[float, float, float, float, str]]:
    blocks = _text_blocks(page)
    if not blocks:
        return []

    page_width = float(page.rect.width)
    gutter = _column_gutter(blocks, page_width)
    if gutter is None:
        ordered = sorted(blocks, key=lambda block: (block[1], block[0]))
        return ordered

    spanning = sorted(
        (
            block
            for block in blocks
            if block[2] - block[0] >= page_width * 0.72
        ),
        key=lambda block: (block[1], block[0]),
    )
    column_blocks = [
        block
        for block in blocks
        if block[2] - block[0] < page_width * 0.72
    ]
    ordered: list[tuple[float, float, float, float, str]] = []
    previous_y = float("-inf")
    for spanning_block in spanning:
        band = [
            block
            for block in column_blocks
            if previous_y <= (block[1] + block[3]) / 2 < spanning_block[1]
        ]
        ordered.extend(
            sorted(
                (block for block in band if block[0] < gutter),
                key=lambda block: (block[1], block[0]),
            )
        )
        ordered.extend(
            sorted(
                (block for block in band if block[0] >= gutter),
                key=lambda block: (block[1], block[0]),
            )
        )
        ordered.append(spanning_block)
        previous_y = spanning_block[3]

    remaining = [
        block
        for block in column_blocks
        if (block[1] + block[3]) / 2 >= previous_y
    ]
    ordered.extend(
        sorted(
            (block for block in remaining if block[0] < gutter),
            key=lambda block: (block[1], block[0]),
        )
    )
    ordered.extend(
        sorted(
            (block for block in remaining if block[0] >= gutter),
            key=lambda block: (block[1], block[0]),
        )
    )
    return ordered


def _ordered_page_text(page: Any) -> str:
    return "\n\n".join(block[4] for block in _ordered_page_blocks(page))


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 140 or "\n" in stripped:
        return False
    if stripped.startswith("#"):
        return True
    return bool(re.match(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+)[.)]?\s+\S+", stripped))


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    import pymupdf
    from docling.document_converter import DocumentConverter

    try:
        with TemporaryDirectory(prefix="nikelpower-pdf-") as temporary_directory:
            pdf_path = Path(temporary_directory) / "document.pdf"
            pdf_path.write_bytes(pdf_bytes)
            result = DocumentConverter().convert(pdf_path)
            document = result.document
            blocks: list[ParsedTextBlock] = []
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf_document:
                markdown_pages: list[str] = []
                current_heading: str | None = None
                block_index = 0
                for page_number, page in enumerate(pdf_document, start=1):
                    page_blocks = _ordered_page_blocks(page)
                    page_text = "\n\n".join(block[4] for block in page_blocks)
                    if page_text:
                        markdown_pages.append(page_text)
                    for x0, y0, x1, y1, text in page_blocks:
                        if _is_heading(text):
                            current_heading = text.lstrip("# ").strip()
                        blocks.append(
                            ParsedTextBlock(
                                text=text,
                                page_number=page_number,
                                bbox=(x0, y0, x1, y1),
                                heading=current_heading,
                                block_index=block_index,
                            )
                        )
                        block_index += 1
                markdown = "\n\n".join(markdown_pages).strip()
            text_extractor = "pymupdf_ordered_blocks"
            if not markdown:
                markdown = document.export_to_markdown().strip()
                text_extractor = "docling_markdown"
                blocks = [
                    ParsedTextBlock(
                        text=part.strip(),
                        page_number=1,
                        bbox=None,
                        heading=(part.strip().lstrip("# ").strip() if _is_heading(part) else None),
                        block_index=index,
                    )
                    for index, part in enumerate(markdown.split("\n\n"))
                    if part.strip()
                ]
            images: list[ParsedImage] = []
            image_manifest: list[dict[str, Any]] = []

            for index, picture in enumerate(document.pictures, start=1):
                image_id = f"image-{index:04d}"
                caption = picture.caption_text(doc=document)
                page_numbers = sorted(
                    {
                        int(provenance.page_no)
                        for provenance in (picture.prov or [])
                        if getattr(provenance, "page_no", None) is not None
                    }
                )
                image = picture.get_image(doc=document)
                if image is None:
                    image_manifest.append(
                        {
                            "image_id": image_id,
                            "caption": (
                                caption.strip()
                                if caption and caption.strip()
                                else None
                            ),
                            "page_numbers": page_numbers,
                            "width": None,
                            "height": None,
                            "media_type": None,
                            "image_data_available": False,
                            "skip_reason": "image_data_unavailable",
                        }
                    )
                    logger.warning(
                        "docling_picture_data_unavailable",
                        image_id=image_id,
                        page_numbers=page_numbers,
                    )
                    continue

                image_buffer = BytesIO()
                image.save(image_buffer, format="PNG")
                content = image_buffer.getvalue()
                images.append(
                    ParsedImage(
                        image_id=image_id,
                        content=content,
                        media_type="image/png",
                        caption=(
                            caption.strip()
                            if caption and caption.strip()
                            else None
                        ),
                        page_numbers=page_numbers,
                        width=image.width,
                        height=image.height,
                    )
                )
                image_manifest.append(
                    {
                        "image_id": image_id,
                        "caption": images[-1].caption,
                        "page_numbers": page_numbers,
                        "width": image.width,
                        "height": image.height,
                        "media_type": "image/png",
                        "image_data_available": True,
                    }
                )

            if not markdown:
                raise DoclingParsingError("Docling extracted no text from the PDF.")

            manifest = {
                "format": "pdf",
                "page_count": len(document.pages),
                "text_extractor": text_extractor,
                "image_count": len(images),
                "detected_picture_count": len(document.pictures),
                "skipped_picture_count": len(document.pictures) - len(images),
                "images": image_manifest,
            }
            return ParsedDocument(
                markdown=markdown,
                images=images,
                manifest=manifest,
                blocks=blocks,
            )
    except DoclingParsingError:
        raise
    except Exception as error:
        raise DoclingParsingError(
            f"Docling could not parse the PDF ({error.__class__.__name__})."
        ) from error
