from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


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


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    from docling.document_converter import DocumentConverter

    try:
        with TemporaryDirectory(prefix="nikelpower-pdf-") as temporary_directory:
            pdf_path = Path(temporary_directory) / "document.pdf"
            pdf_path.write_bytes(pdf_bytes)
            result = DocumentConverter().convert(pdf_path)
            document = result.document
            markdown = document.export_to_markdown().strip()
            images: list[ParsedImage] = []
            image_manifest: list[dict[str, Any]] = []

            for index, picture in enumerate(document.pictures, start=1):
                image_id = f"image-{index:04d}"
                image = picture.get_image(doc=document)
                if image is None:
                    raise DoclingParsingError(
                        f"Docling did not return image data for {image_id}."
                    )

                image_buffer = BytesIO()
                image.save(image_buffer, format="PNG")
                content = image_buffer.getvalue()
                caption = picture.caption_text(doc=document)
                page_numbers = sorted(
                    {
                        int(provenance.page_no)
                        for provenance in (picture.prov or [])
                        if getattr(provenance, "page_no", None) is not None
                    }
                )
                images.append(
                    ParsedImage(
                        image_id=image_id,
                        content=content,
                        media_type="image/png",
                        caption=caption.strip() if caption and caption.strip() else None,
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
                    }
                )

            if not markdown:
                raise DoclingParsingError("Docling extracted no text from the PDF.")

            manifest = {
                "format": "pdf",
                "page_count": len(document.pages),
                "image_count": len(images),
                "images": image_manifest,
            }
            return ParsedDocument(markdown, images, manifest)
    except DoclingParsingError:
        raise
    except Exception as error:
        raise DoclingParsingError(
            f"Docling could not parse the PDF ({error.__class__.__name__})."
        ) from error
