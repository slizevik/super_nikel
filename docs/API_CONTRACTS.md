# API contracts

The active HTTP API is implemented in `backend/app/api/routes/` and mounted
under `/api/v1`.

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/v1/documents` | Accept a PDF and category; returns HTTP 202 with document and job data |
| `GET` | `/api/v1/documents` | List uploaded documents |
| `GET` | `/api/v1/documents/{id}` | Return document metadata and extracted information |
| `GET` | `/api/v1/documents/{id}/download` | Download the original document |
| `GET` | `/api/v1/jobs/{job_id}` | Return ingestion job details |
| `GET` | `/api/v1/jobs/{job_id}/status` | Return job status with compatibility terminal/success flags |
| `GET` | `/health/live` | Check that the API process is running |
| `GET` | `/health/ready` | Check PostgreSQL and Redis readiness |

Uploads require a readable PDF and a non-empty category (maximum 100
characters). The upload size limit is configurable. An extracted job in
`awaiting_persistence` is not terminal success. There are currently no Kafka
contracts, graph-query endpoint, chat-answering endpoint, or human-review
endpoint.

Every HTTP response includes an `X-Request-ID` response header. The same ID is
written to the structured API request log to help correlate client reports
with server-side failures.
