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
        +-- LLM image description and entity extraction
        |
        +-- PostgreSQL + pgvector (documents, jobs, chunks)
        +-- Neo4j (schema initialized; ingestion persistence is not wired)
```

Docker Compose currently runs PostgreSQL, Neo4j, Redis, the API, and a Celery
worker. The API accepts PDF uploads and stores metadata and file bytes in
PostgreSQL. The worker parses documents, calls the configured LLM provider, and
validates extraction output. Successful extraction stops at
`awaiting_persistence`; it is not yet a completed graph-ingestion flow.

The API and worker emit structured JSON logs to stdout and to separate rotating
files under `logs/`. HTTP requests carry a generated `X-Request-ID`; worker
events include `job_id` and `document_id`. Application logs are available with
PowerShell `Get-Content -Wait` or `docker compose logs -f backend worker`.

## Target architecture and status

| Component | Target role | Current status |
|---|---|---|
| API | Upload, status, and future query endpoints | FastAPI exists in `backend/` |
| Parser worker | Convert source documents to structured text | Docling runs in the existing Celery task |
| Extractor worker | Extract ontology entities and relations | LLM extraction runs in the existing task |
| Validator | Review and persist approved graph data | Automatic schema validation exists; separate worker and human review do not |
| PostgreSQL | Document metadata, jobs, and vector chunks | Models and Alembic migrations exist |
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
