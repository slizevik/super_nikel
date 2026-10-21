from dataclasses import dataclass
from io import BytesIO
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
class ParsedDocument:
    markdown: str
    images: list[ParsedImage]
    manifest: dict[str, Any]


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


def _ordered_page_text(page: Any) -> str:
    blocks = _text_blocks(page)
    if not blocks:
        return ""

    page_width = float(page.rect.width)
    gutter = _column_gutter(blocks, page_width)
    if gutter is None:
        ordered = sorted(blocks, key=lambda block: (block[1], block[0]))
        return "\n\n".join(block[4] for block in ordered)

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
    return "\n\n".join(block[4] for block in ordered)


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    import pymupdf
    from docling.document_converter import DocumentConverter

    try:
        with TemporaryDirectory(prefix="nikelpower-pdf-") as temporary_directory:
            pdf_path = Path(temporary_directory) / "document.pdf"
            pdf_path.write_bytes(pdf_bytes)
            result = DocumentConverter().convert(pdf_path)
            document = result.document
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf_document:
                markdown = "\n\n".join(
                    page_text
                    for page in pdf_document
                    if (page_text := _ordered_page_text(page))
                ).strip()
            text_extractor = "pymupdf_ordered_blocks"
            if not markdown:
                markdown = document.export_to_markdown().strip()
                text_extractor = "docling_markdown"
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
            return ParsedDocument(markdown, images, manifest)
    except DoclingParsingError:
        raise
    except Exception as error:
        raise DoclingParsingError(
            f"Docling could not parse the PDF ({error.__class__.__name__})."
        ) from error
