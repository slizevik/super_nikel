import subprocess
from pathlib import Path

import pytest

from app.services.document_conversion import (
    DocxConversionError,
    convert_docx_to_pdf,
)


def test_docx_conversion_saves_pdf_for_pipeline(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "source.pdf").write_bytes(b"%PDF-1.7 converted")

    monkeypatch.setattr("app.services.document_conversion.subprocess.run", run)

    result = convert_docx_to_pdf(
        b"docx-bytes",
        "document-123",
        tmp_path,
        "libreoffice",
        90,
    )

    assert result == tmp_path / "document-123.pdf"
    assert result.read_bytes() == b"%PDF-1.7 converted"
    assert calls[0][0] == "libreoffice"
    assert "--headless" in calls[0]
    assert calls[0][calls[0].index("--convert-to") + 1] == "pdf:writer_pdf_Export"
    assert not list(tmp_path.glob(".document-123-*"))


def test_docx_conversion_accepts_relative_output_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    def run(command, **_kwargs):
        profile_uri = next(
            argument
            for argument in command
            if argument.startswith("-env:UserInstallation=")
        ).split("=", maxsplit=1)[1]
        assert profile_uri.startswith("file:///")
        output_directory = Path(command[command.index("--outdir") + 1])
        assert output_directory.is_absolute()
        (output_directory / "source.pdf").write_bytes(b"%PDF-1.7 converted")

    monkeypatch.setattr("app.services.document_conversion.subprocess.run", run)

    result = convert_docx_to_pdf(
        b"docx-bytes",
        "document-123",
        "data/ingestion/converted",
        "libreoffice",
        90,
    )

    assert result == tmp_path / "data" / "ingestion" / "converted" / "document-123.pdf"
    assert result.read_bytes() == b"%PDF-1.7 converted"


def test_docx_conversion_reports_missing_pdf_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.services.document_conversion.subprocess.run",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(DocxConversionError, match="without producing a PDF"):
        convert_docx_to_pdf(
            b"docx-bytes",
            "document-123",
            tmp_path,
            "libreoffice",
            90,
        )

    assert not (tmp_path / "document-123.pdf").exists()


def test_docx_conversion_rejects_non_pdf_output(monkeypatch, tmp_path: Path) -> None:
    def run(command, **_kwargs):
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "source.pdf").write_bytes(b"not a PDF")

    monkeypatch.setattr("app.services.document_conversion.subprocess.run", run)

    with pytest.raises(DocxConversionError, match="not a valid PDF"):
        convert_docx_to_pdf(
            b"docx-bytes",
            "document-123",
            tmp_path,
            "libreoffice",
            90,
        )

    assert not (tmp_path / "document-123.pdf").exists()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(), "was not found"),
        (subprocess.TimeoutExpired("libreoffice", 5), "exceeded the 90-second timeout"),
    ],
)
def test_docx_conversion_reports_process_errors(
    monkeypatch,
    tmp_path: Path,
    error: Exception,
    message: str,
) -> None:
    def run(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("app.services.document_conversion.subprocess.run", run)

    with pytest.raises(DocxConversionError, match=message):
        convert_docx_to_pdf(
            b"docx-bytes",
            "document-123",
            tmp_path,
            "libreoffice",
            90,
        )
