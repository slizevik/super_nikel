import sys
from types import ModuleType, SimpleNamespace

from PIL import Image

from app.services.pdf_parser import parse_pdf


def test_docling_adapter_returns_text_image_and_manifest(monkeypatch) -> None:
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


def test_docling_adapter_skips_picture_without_image_data(
    monkeypatch,
) -> None:
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
