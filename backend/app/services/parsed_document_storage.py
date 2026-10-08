import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID


def save_parsed_markdown(
    markdown: str,
    document_id: UUID,
    output_directory: str | Path,
) -> Path:
    return _save_text_artifact(
        markdown,
        document_id,
        output_directory,
        suffix=".md",
    )


def save_model_response(
    response: str,
    document_id: UUID,
    output_directory: str | Path,
) -> Path:
    return _save_text_artifact(
        response,
        document_id,
        output_directory,
        suffix=".llm-response.txt",
    )


def _save_text_artifact(
    content: str,
    document_id: UUID,
    output_directory: str | Path,
    suffix: str,
) -> Path:
    destination_directory = Path(output_directory)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / f"{document_id}{suffix}"
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination_directory,
            prefix=f".{document_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        raise

    return destination
