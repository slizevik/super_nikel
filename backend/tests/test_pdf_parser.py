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
