import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


PDF_MIME_TYPE = "application/pdf"
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
PDF_SIGNATURE = b"%PDF-"


class DocxConversionError(RuntimeError):
    pass


def convert_docx_to_pdf(
    docx_bytes: bytes,
    document_id: str,
    output_directory: str | Path,
    libreoffice_binary: str,
    timeout_seconds: int,
) -> Path:
    destination_directory = Path(output_directory).resolve()
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / f"{document_id}.pdf"

    try:
        with TemporaryDirectory(
            prefix=f".{document_id}-",
            dir=destination_directory,
        ) as temporary_directory:
            working_directory = Path(temporary_directory)
            source_path = working_directory / "source.docx"
            converted_directory = working_directory / "output"
            profile_directory = working_directory / "profile"
            converted_directory.mkdir()
            profile_directory.mkdir()
            source_path.write_bytes(docx_bytes)

            try:
                subprocess.run(
                    [
                        libreoffice_binary,
                        f"-env:UserInstallation={profile_directory.as_uri()}",
                        "--headless",
                        "--convert-to",
                        "pdf:writer_pdf_Export",
                        "--outdir",
                        str(converted_directory),
                        str(source_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except FileNotFoundError as error:
                raise DocxConversionError(
                    f"LibreOffice executable '{libreoffice_binary}' was not found."
                ) from error
            except subprocess.TimeoutExpired as error:
                raise DocxConversionError(
                    "DOCX to PDF conversion exceeded the "
                    f"{timeout_seconds}-second timeout."
                ) from error
            except subprocess.CalledProcessError as error:
                raise DocxConversionError(
                    "LibreOffice failed to convert the DOCX "
                    f"(exit code {error.returncode})."
                ) from error

            converted_path = converted_directory / "source.pdf"
            if not converted_path.is_file():
                raise DocxConversionError(
                    "LibreOffice completed without producing a PDF."
                )

            with converted_path.open("rb") as converted_file:
                if converted_file.read(len(PDF_SIGNATURE)) != PDF_SIGNATURE:
                    raise DocxConversionError(
                        "LibreOffice produced a file that is not a valid PDF."
                    )

            os.replace(converted_path, destination)
    except DocxConversionError:
        raise
    except OSError as error:
        raise DocxConversionError(
            f"DOCX to PDF conversion failed ({error.__class__.__name__})."
        ) from error

    return destination
