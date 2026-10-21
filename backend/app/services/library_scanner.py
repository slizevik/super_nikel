import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.services.document_conversion import PDF_SIGNATURE


@dataclass(frozen=True)
class ScannedPdf:
    relative_path: str
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ScanError:
    relative_path: str
    message: str


@dataclass(frozen=True)
class LibraryScan:
    files: list[ScannedPdf]
    errors: list[ScanError]


class LibraryConfigurationError(RuntimeError):
    pass


class LibraryFileError(RuntimeError):
    pass


def classify_scanned_file(
    stored_sha256: str | None,
    scanned_sha256: str,
    latest_job_status: str | None,
) -> str:
    if stored_sha256 is None:
        return "new"
    if stored_sha256 != scanned_sha256:
        return (
            "busy"
            if latest_job_status in {"queued", "processing"}
            else "changed"
        )
    if latest_job_status is None or latest_job_status == "failed":
        return "retry"
    return "unchanged"


def resolve_library_file(root: Path | None, relative_path: str) -> Path:
    if root is None:
        raise LibraryConfigurationError("LIBRARY_ROOT is not configured.")
    library_root = root.resolve(strict=True)
    candidate = (library_root / relative_path).resolve(strict=True)
    try:
        candidate.relative_to(library_root)
    except ValueError as error:
        raise LibraryFileError(
            "Library path resolves outside the configured root."
        ) from error
    if not candidate.is_file() or candidate.suffix.casefold() != ".pdf":
        raise LibraryFileError("Library document is not an available PDF file.")
    return candidate


def scan_library(root: Path | None) -> LibraryScan:
    if root is None:
        raise LibraryConfigurationError("LIBRARY_ROOT is not configured.")
    try:
        library_root = root.resolve(strict=True)
    except OSError as error:
        raise LibraryConfigurationError(
            "The configured library directory is not accessible."
        ) from error
    if not library_root.is_dir():
        raise LibraryConfigurationError(
            "The configured library path is not a directory."
        )

    files: list[ScannedPdf] = []
    errors: list[ScanError] = []
    for path in sorted(library_root.rglob("*")):
        if path.suffix.casefold() != ".pdf" or path.is_symlink():
            continue
        relative_path = path.relative_to(library_root).as_posix()
        try:
            digest = hashlib.sha256()
            size_bytes = 0
            signature = b""
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    if not signature:
                        signature = chunk[: len(PDF_SIGNATURE)]
                    digest.update(chunk)
                    size_bytes += len(chunk)
            if signature != PDF_SIGNATURE:
                errors.append(ScanError(relative_path, "File is not a valid PDF."))
                continue
            if size_bytes == 0:
                errors.append(ScanError(relative_path, "PDF file is empty."))
                continue
            files.append(
                ScannedPdf(
                    relative_path=relative_path,
                    filename=path.name,
                    size_bytes=size_bytes,
                    sha256=digest.hexdigest(),
                )
            )
        except OSError:
            errors.append(ScanError(relative_path, "File could not be read."))
    return LibraryScan(files=files, errors=errors)
