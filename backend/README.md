# PDF ingestion API

## Run locally with Docker Compose

From the repository root:

```powershell
docker compose up --build -d --wait backend worker
```

Compose starts PostgreSQL, Redis, the API, and a Celery worker; the API applies
pending Alembic migrations before it starts. The interactive API documentation
is available at <http://localhost:8000/docs>.

## Run the manual-test frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite development server proxies API calls to
the backend on port 8000. Upload a PDF and the page polls its job status until
entity extraction finishes or reports the failing pipeline stage. The current
pipeline stops at `awaiting_persistence`; this means extraction succeeded, but
entities have not yet been written to Neo4j.

The default upload limit is 50 MiB and can be changed with
`MAX_UPLOAD_SIZE_BYTES`. Configure local passwords in `.env` before exposing
the services beyond the local machine.

`TOKEN_LIMIT` is the single configurable upper bound for estimated and
provider-reported LLM tokens per PDF ingestion job, including image-analysis
calls, document text, and model responses. Its value is snapshotted on upload
and persisted with the job so changing `.env` does not reset a running or
retried job. Before each provider request, the worker reserves a conservative
input estimate and the maximum allowed response size; the request's
`max_tokens` is capped to the remaining budget. If the next request cannot fit,
the job fails with `TOKEN_LIMIT_EXCEEDED` and no further LLM requests are made.
Text is conservatively estimated by UTF-8 byte length and images by their
dimensions; provider-reported usage replaces the estimate after a successful
response. Timed-out or failed calls keep their reservation because their
provider-side usage may be unknown. A request is skipped if less than 128
tokens remain for its response.

## Upload a PDF

Send a multipart request to `POST /api/v1/documents` with:

- `file`: a readable PDF file;
- `category`: a non-empty category of up to 100 characters.

The API returns HTTP 202 with a document ID and ingestion job ID. Check
`GET /jobs/{job_id}/status` (also available under `/api/v1`) for progress and
`GET /api/v1/documents/{id}` for
metadata and extracted text. Download the original file from
`GET /api/v1/documents/{id}/download`; list uploaded documents with
`GET /api/v1/documents`.

The worker extracts Markdown, images, captions, and a manifest using Docling.
It then calls the configured LLM provider to describe images and extract
ontology entities. Yandex Cloud is the default provider. Until
`YANDEX_CLOUD_API_KEY` and `YANDEX_CLOUD_FOLDER` are configured in `.env`, jobs
fail explicitly with `LLM_CREDENTIALS_MISSING`; they are never reported as
success. Configure models and endpoint with `YANDEX_CLOUD_MODEL`,
`YANDEX_VISION_MODEL`, and `YANDEX_CLOUD_BASE_URL`.

After successful extraction and validation, a job enters
`awaiting_persistence`. This is non-terminal: the document and extracted
results have not yet been committed to the knowledge graph. Only a future
pipeline stage that persists the graph may mark it `completed`.

`GET /api/v1/jobs/{job_id}` remains available as a compatibility route.

`GET /health/live` checks that the API process is running.
`GET /health/ready` checks PostgreSQL and Redis connectivity.
