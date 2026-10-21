import hashlib
from pathlib import Path

import pytest

from app.services.library_scanner import (
    LibraryConfigurationError,
    LibraryFileError,
    classify_scanned_file,
    resolve_library_file,
    scan_library,
)


def test_scan_reports_relative_path_and_content_hash(tmp_path: Path) -> None:
    pdf = tmp_path / "subfolder" / "paper.pdf"
    pdf.parent.mkdir()
    contents = b"%PDF-1.7 paper"
    pdf.write_bytes(contents)

    scan = scan_library(tmp_path)

    assert len(scan.files) == 1
    assert scan.files[0].relative_path == "subfolder/paper.pdf"
    assert scan.files[0].filename == "paper.pdf"
    assert scan.files[0].size_bytes == len(contents)
    assert scan.files[0].sha256 == hashlib.sha256(contents).hexdigest()
    assert scan.errors == []


def test_rescan_detects_content_change_and_ignores_unchanged_files(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 first")
    first_hash = scan_library(tmp_path).files[0].sha256
    unchanged_hash = scan_library(tmp_path).files[0].sha256
    pdf.write_bytes(b"%PDF-1.7 changed")
    changed_hash = scan_library(tmp_path).files[0].sha256

    assert classify_scanned_file(first_hash, unchanged_hash, "completed") == "unchanged"
    assert classify_scanned_file(first_hash, changed_hash, "completed") == "changed"
    assert classify_scanned_file(first_hash, changed_hash, "processing") == "busy"


def test_failed_or_unprocessed_same_file_can_be_retried() -> None:
    assert classify_scanned_file(None, "new-hash", None) == "new"
    assert classify_scanned_file("same", "same", "failed") == "retry"
    assert classify_scanned_file("same", "same", None) == "retry"


def test_scan_reports_invalid_pdf_without_indexing_it(tmp_path: Path) -> None:
    (tmp_path / "not-a-pdf.pdf").write_bytes(b"not a pdf")

    scan = scan_library(tmp_path)

    assert scan.files == []
    assert scan.errors[0].relative_path == "not-a-pdf.pdf"


def test_scan_requires_an_existing_configured_directory(tmp_path: Path) -> None:
    with pytest.raises(LibraryConfigurationError, match="not accessible"):
        scan_library(tmp_path / "missing")


def test_library_path_must_stay_inside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.pdf"
    outside.write_bytes(b"%PDF-1.7")
    try:
        with pytest.raises(LibraryFileError, match="outside"):
            resolve_library_file(tmp_path, str(outside))
    finally:
        outside.unlink(missing_ok=True)
