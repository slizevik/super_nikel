# Architecture

## Current implementation

```text
React UI (frontend/)
        | HTTP
FastAPI API (backend/)
        | enqueue
Celery worker -- Redis broker/result backend
        |
        +-- Docling PDF parsing
        +-- LLM image description and entity extraction (UI uploads only)
        |
        +-- PostgreSQL + pgvector (document metadata, jobs, chunks)
        +-- Neo4j (schema initialized; ingestion persistence is not wired)

Read-only local PDF library:
Host folder -> backend scan API -> PostgreSQL path/hash/job -> Celery/Docling
Folder documents are not copied into PostgreSQL and do not invoke an LLM.
```

Docker Compose currently runs PostgreSQL, Neo4j, Redis, the API, and a Celery
worker. The API accepts PDF and DOCX uploads and stores metadata and original
file bytes in PostgreSQL. The Celery worker converts DOCX to PDF with LibreOffice
and stores the result under `CONVERTED_PDF_DIR` before parsing.
An optional `LIBRARY_ROOT` bind mount is read-only. The library scan API detects
PDFs by relative path and SHA-256; unchanged files are not reprocessed, changed
files receive a new job, and removed files remain in the database as unavailable.
Library files use PyMuPDF for coordinate-ordered text extraction and Docling
for figure detection/cropping. Detected figure images are saved under
`PARSED_DOCUMENTS_DIR/<document_id>_images` and referenced by the job manifest.
Only individual PDF/DOCX files uploaded through the UI call the configured LLM
provider. For uploads, at most `MAX_IMAGES_FOR_LLM` figures (default 8) receive
LLM image analysis, while all available figure files are retained. Successful
extraction of an uploaded file stops at
`awaiting_persistence`; it is not yet a completed graph-ingestion flow.
Extracted text is also written atomically to
`PARSED_DOCUMENTS_DIR/<document_id>.md` by the worker. In Docker Compose the
host directory configured by `PARSED_DOCUMENTS_DIR` is mounted read-write at
`/processed`. The raw entity-extraction response is saved beside
it as `<document_id>.llm-response.txt` before schema validation; response bodies
are not written to application logs.

The API and worker emit structured JSON logs to stdout and to separate rotating
files under `logs/`. HTTP requests carry a generated `X-Request-ID`; worker
events include `job_id` and `document_id`. Application logs are available with
PowerShell `Get-Content -Wait` or `docker compose logs -f backend worker`.

## Target architecture and status

| Component | Target role | Current status |
|---|---|---|
| API | Upload, status, and future query endpoints | FastAPI exists in `backend/` |
| Parser worker | Convert source documents to structured text | Docling runs in the existing Celery task; scanned-library PDFs skip LLM calls |
| Extractor worker | Extract ontology entities and relations | LLM extraction runs in the existing task |
| Validator | Review and persist approved graph data | Automatic schema validation exists; separate worker and human review do not |
| PostgreSQL | Document metadata, jobs, and vector chunks | Upload bytes or library relative paths, jobs, and Alembic migrations |
| Neo4j | Knowledge graph | Schema constraints exist; pipeline writes are not implemented |
| Celery + Redis broker | Current background task transport | Active: Redis is used as the Celery broker/result backend |
| Human-in-the-Loop review | Future validation workflow for extracted entities | Planned feature; not implemented in the current app |
| Frontend | Upload and monitor processing | React UI exists; chat and graph exploration do not |

`services/` and `libs/` are scaffolding for a possible future decomposition.
The executable source of truth remains in `backend/`, `frontend/`, and `docker/`.

## Human-in-the-Loop

A human validation workflow is part of the target architecture, but it is not
implemented yet. The current implementation validates extraction and schema
constraints automatically, and the pipeline remains intentionally limited to the
`awaiting_persistence` stage until a future persistence layer is added. This
feature should be designed as a follow-up step with explicit reviewer metadata,
review decisions, and audit history rather than being treated as current runtime
behavior.
