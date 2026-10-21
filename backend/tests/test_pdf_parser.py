import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

from PIL import Image

from app.services.parsed_document_storage import save_parsed_images
from app.services.pdf_parser import parse_pdf


class FakePdf:
    def __init__(self, pages) -> None:
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def __iter__(self):
        return iter(self.pages)


def install_pymupdf(monkeypatch, blocks) -> None:
    page = SimpleNamespace(
        rect=SimpleNamespace(width=600),
        get_text=lambda _kind: blocks,
    )
    pymupdf_module = ModuleType("pymupdf")
    pymupdf_module.open = lambda **_kwargs: FakePdf([page])
    monkeypatch.setitem(sys.modules, "pymupdf", pymupdf_module)


def text_block(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text, 0, 0)


def test_docling_adapter_returns_text_image_and_manifest(monkeypatch) -> None:
    install_pymupdf(monkeypatch, [])
    image = Image.new("RGB", (12, 8), color="red")
    picture = SimpleNamespace(
        get_image=lambda doc: image,
        caption_text=lambda doc: "Nickel recovery chart",
        prov=[SimpleNamespace(page_no=2)],
    )
    document = SimpleNamespace(
        pictures=[picture],
        pages={1: object(), 2: object()},
        export_to_markdown=lambda: "# Nickel recovery\nThe chart shows recovery.",
    )
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: SimpleNamespace(
        convert=lambda _path: SimpleNamespace(document=document)
    )
    package_module = ModuleType("docling")
    package_module.__path__ = []
    monkeypatch.setitem(sys.modules, "docling", package_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    parsed = parse_pdf(b"%PDF-1.7 test")

    assert parsed.markdown == "# Nickel recovery\nThe chart shows recovery."
    assert parsed.manifest["page_count"] == 2
    assert parsed.manifest["image_count"] == 1
    assert parsed.images[0].image_id == "image-0001"
    assert parsed.images[0].caption == "Nickel recovery chart"
    assert parsed.images[0].page_numbers == [2]
    assert parsed.images[0].media_type == "image/png"
    assert parsed.images[0].content.startswith(b"\x89PNG")
    assert parsed.manifest["detected_picture_count"] == 1
    assert parsed.manifest["skipped_picture_count"] == 0
    assert parsed.manifest["images"][0]["image_data_available"] is True
    assert parsed.manifest["text_extractor"] == "docling_markdown"


def test_docling_adapter_skips_picture_without_image_data(
    monkeypatch,
) -> None:
    install_pymupdf(monkeypatch, [])
    image = Image.new("RGB", (12, 8), color="blue")
    unavailable_picture = SimpleNamespace(
        get_image=lambda doc: None,
        caption_text=lambda doc: "Vector illustration",
        prov=[SimpleNamespace(page_no=1)],
    )
    valid_picture = SimpleNamespace(
        get_image=lambda doc: image,
        caption_text=lambda doc: "Recovery chart",
        prov=[SimpleNamespace(page_no=2)],
    )
    document = SimpleNamespace(
        pictures=[unavailable_picture, valid_picture],
        pages={1: object(), 2: object()},
        export_to_markdown=lambda: "# Nickel recovery\nRecovery increased.",
    )
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: SimpleNamespace(
        convert=lambda _path: SimpleNamespace(document=document)
    )
    package_module = ModuleType("docling")
    package_module.__path__ = []
    monkeypatch.setitem(sys.modules, "docling", package_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    warnings: list[dict] = []
    monkeypatch.setattr(
        "app.services.pdf_parser.logger",
        SimpleNamespace(warning=lambda event, **kwargs: warnings.append(kwargs)),
    )

    parsed = parse_pdf(b"%PDF-1.7 test")

    assert parsed.markdown == "# Nickel recovery\nRecovery increased."
    assert len(parsed.images) == 1
    assert parsed.images[0].image_id == "image-0002"
    assert parsed.manifest["image_count"] == 1
    assert parsed.manifest["detected_picture_count"] == 2
    assert parsed.manifest["skipped_picture_count"] == 1
    assert parsed.manifest["images"] == [
        {
            "image_id": "image-0001",
            "caption": "Vector illustration",
            "page_numbers": [1],
            "width": None,
            "height": None,
            "media_type": None,
            "image_data_available": False,
            "skip_reason": "image_data_unavailable",
        },
        {
            "image_id": "image-0002",
            "caption": "Recovery chart",
            "page_numbers": [2],
            "width": 12,
            "height": 8,
            "media_type": "image/png",
            "image_data_available": True,
        },
    ]
    assert warnings == [{"image_id": "image-0001", "page_numbers": [1]}]


def test_pdf_text_is_extracted_left_column_then_right_column(monkeypatch) -> None:
    install_pymupdf(
        monkeypatch,
        [
            text_block(40, 100, 270, 130, "Left column, first paragraph."),
            text_block(40, 150, 270, 180, "Left column, second paragraph."),
            text_block(330, 100, 560, 130, "Right column, first paragraph."),
            text_block(330, 150, 560, 180, "Right column, second paragraph."),
        ],
    )
    document = SimpleNamespace(
        pictures=[],
        pages={1: object()},
        export_to_markdown=lambda: "Docling fallback",
    )
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: SimpleNamespace(
        convert=lambda _path: SimpleNamespace(document=document)
    )
    package_module = ModuleType("docling")
    package_module.__path__ = []
    monkeypatch.setitem(sys.modules, "docling", package_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    parsed = parse_pdf(b"%PDF-1.7 test")

    assert parsed.markdown.index("Left column, first") < parsed.markdown.index(
        "Left column, second"
    )
    assert parsed.markdown.index("Left column, second") < parsed.markdown.index(
        "Right column, first"
    )
    assert parsed.markdown.index("Right column, first") < parsed.markdown.index(
        "Right column, second"
    )
    assert parsed.manifest["text_extractor"] == "pymupdf_ordered_blocks"


def test_pymupdf_detects_two_columns_in_a_generated_pdf(monkeypatch) -> None:
    import pymupdf

    pdf_document = pymupdf.open()
    page = pdf_document.new_page(width=600, height=800)
    page.insert_text((40, 100), "Left first paragraph")
    page.insert_text((40, 150), "Left second paragraph")
    page.insert_text((330, 100), "Right first paragraph")
    page.insert_text((330, 150), "Right second paragraph")
    pdf_bytes = pdf_document.tobytes()
    pdf_document.close()
    document = SimpleNamespace(
        pictures=[],
        pages={1: object()},
        export_to_markdown=lambda: "Docling fallback",
    )
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: SimpleNamespace(
        convert=lambda _path: SimpleNamespace(document=document)
    )
    package_module = ModuleType("docling")
    package_module.__path__ = []
    monkeypatch.setitem(sys.modules, "docling", package_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    parsed = parse_pdf(pdf_bytes)

    assert parsed.markdown.index("Left first") < parsed.markdown.index("Left second")
    assert parsed.markdown.index("Left second") < parsed.markdown.index("Right first")
    assert parsed.markdown.index("Right first") < parsed.markdown.index("Right second")


def test_pdf_text_keeps_full_width_heading_before_two_columns(monkeypatch) -> None:
    install_pymupdf(
        monkeypatch,
        [
            text_block(40, 20, 560, 50, "Full-width title"),
            text_block(40, 100, 270, 130, "Left body"),
            text_block(330, 100, 560, 130, "Right body"),
        ],
    )
    document = SimpleNamespace(
        pictures=[],
        pages={1: object()},
        export_to_markdown=lambda: "Docling fallback",
    )
    converter_module = ModuleType("docling.document_converter")
    converter_module.DocumentConverter = lambda: SimpleNamespace(
        convert=lambda _path: SimpleNamespace(document=document)
    )
    package_module = ModuleType("docling")
    package_module.__path__ = []
    monkeypatch.setitem(sys.modules, "docling", package_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    parsed = parse_pdf(b"%PDF-1.7 test")

    assert parsed.markdown.index("Full-width title") < parsed.markdown.index(
        "Left body"
    )
    assert parsed.markdown.index("Left body") < parsed.markdown.index("Right body")


def test_all_extracted_figures_are_saved_and_referenced(tmp_path: Path) -> None:
    document_id = uuid4()

    paths = save_parsed_images(
        [("image-0001", b"figure-data"), ("image-0002", b"other-figure")],
        document_id,
        tmp_path,
    )

    assert paths == {
        "image-0001": f"{document_id}_images/image-0001.png",
        "image-0002": f"{document_id}_images/image-0002.png",
    }
    for relative_path, content in zip(paths.values(), [b"figure-data", b"other-figure"]):
        assert (tmp_path / relative_path).read_bytes() == content
