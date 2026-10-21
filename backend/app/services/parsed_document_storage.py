import os
from pathlib import Path
from re import sub
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


def save_parsed_images(
    images: list[tuple[str, bytes]],
    document_id: UUID,
    output_directory: str | Path,
) -> dict[str, str]:
    image_directory = Path(output_directory) / f"{document_id}_images"
    paths: dict[str, str] = {}
    for image_id, content in images:
        safe_image_id = sub(r"[^A-Za-z0-9_-]", "_", image_id)
        destination = image_directory / f"{safe_image_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{safe_image_id}.",
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
        paths[image_id] = destination.relative_to(output_directory).as_posix()
    return paths


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
