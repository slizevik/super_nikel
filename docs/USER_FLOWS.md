# User flows

## Available: upload and monitor a PDF

1. A user submits a PDF and category through the React UI or
   `POST /api/v1/documents`.
2. The API checks the file type/signature and configured size limit, stores the
   source document and creates a job in PostgreSQL.
3. Celery dispatches asynchronous processing through Redis.
4. The worker parses the PDF with Docling, optionally analyzes images, extracts
   ontology entities through the configured LLM provider, and validates the
   result.
5. The UI polls job status and displays progress or an explicit failure.
6. Successful extraction currently ends at `awaiting_persistence`; no graph
   write or terminal success is claimed.

## Planned: human validation and graph persistence

The desired workflow requires a review queue for extracted facts, evidence,
and unclassified terms. A reviewer should approve, reject, or correct the
result before graph persistence. This queue and reviewer interface are not
implemented.

## Planned: search and answering

Natural-language search, graph exploration, source-backed LLM answers, chat
history, and filters are product goals, but are not currently exposed by the
API or frontend.
