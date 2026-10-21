# API contracts

The active HTTP API is implemented in `backend/app/api/routes/` and mounted
under `/api/v1`.

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/v1/documents` | Accept a PDF or DOCX and category; returns HTTP 202 with document and job data |
| `GET` | `/api/v1/documents` | List library documents with latest job status and source availability |
| `GET` | `/api/v1/documents/{id}` | Return document metadata and extracted information |
| `GET` | `/api/v1/documents/{id}/download` | Download the original document |
| `POST` | `/api/v1/library/scan` | Scan configured `LIBRARY_ROOT`, queue newly discovered/changed PDFs, and return a scan summary |
| `GET` | `/api/v1/jobs/{job_id}` | Return ingestion job details |
| `GET` | `/api/v1/jobs/{job_id}/status` | Return job status with compatibility terminal/success flags |
| `GET` | `/health/live` | Check that the API process is running |
| `GET` | `/health/ready` | Check PostgreSQL and Redis readiness |

Uploads require a readable PDF or DOCX and a non-empty category (maximum 100
characters). The original upload is preserved. The worker converts DOCX to PDF
before parsing; the PDF and DOCX size limit is configurable. An extracted job in
`awaiting_persistence` is not terminal success. There are currently no Kafka
contracts, graph-query endpoint, chat-answering endpoint, or human-review
endpoint.

`LIBRARY_ROOT` is configured on the backend. The browser cannot submit an
arbitrary filesystem path. In Docker Compose the host folder is mounted
read-only at `/library` in the API and worker. Library PDFs are parsed by
Docling without LLM calls; only documents submitted through `POST /documents`
invoke the configured LLM provider. The scan response reports discovered,
queued, changed, unchanged, busy, and unreadable files. Library records retain
their relative path and content hash; original files stay in the source folder.
The latest job manifest identifies detected figures by page and caption and
includes a `stored_path` for each figure image saved under the configured
processed-document directory.

Every HTTP response includes an `X-Request-ID` response header. The same ID is
written to the structured API request log to help correlate client reports
with server-side failures.
