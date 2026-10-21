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

## Available: scan and index a read-only article library

1. The operator configures `LIBRARY_ROOT` in `.env`; Docker mounts that host
   directory into the API and worker as `/library:ro`.
2. The UI calls `POST /api/v1/library/scan`. The backend recursively finds
   valid PDFs, stores their relative paths and SHA-256 hashes, and creates jobs
   for new or changed files.
3. The worker reads each source PDF from the mounted directory, extracts
   coordinate-ordered text with PyMuPDF, and detects/crops figures with Docling.
   It stores extracted text and figure files and marks the indexing job
   `completed`; it does not call an LLM or copy the original PDF into PostgreSQL.
4. Repeated scans skip unchanged documents. Changed documents are re-indexed;
   missing files remain listed and are marked unavailable.
5. The UI lists library documents, their source availability, and the latest
   processing status. Original library PDFs open from the backend. Separately
   uploaded documents are not included in this library listing.

The LLM remains limited to single PDF/DOCX files explicitly uploaded through
the upload form. For those uploads, all available figure files are retained,
but only up to `MAX_IMAGES_FOR_LLM` (default 8) receive LLM image analysis.
Markdown and extracted figures are written under `PARSED_DOCUMENTS_DIR`; in
Compose, the worker writes to `/processed`, mounted from the configured host
directory.

## Planned: human validation and graph persistence

The desired workflow requires a review queue for extracted facts, evidence,
and unclassified terms. A reviewer should approve, reject, or correct the
result before graph persistence. This queue and reviewer interface are not
implemented.

## Planned: search and answering

Natural-language search, graph exploration, source-backed LLM answers, chat
history, and filters are product goals, but are not currently exposed by the
API or frontend.
