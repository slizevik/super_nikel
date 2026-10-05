# PostgreSQL schema

Alembic migrations in `backend/migrations/versions/` are authoritative for the
application schema. SQLAlchemy models are in `backend/app/db/models.py`.

| Table | Purpose |
|---|---|
| `documents` | PDF metadata, checksum, original file bytes, and source metadata |
| `ingestion_jobs` | Processing status, step, errors, extraction output, and token budget |
| `document_chunks` | Text chunks, embeddings, and chunk metadata |

PostgreSQL is run with the `pgvector` extension. Local extension initialization
is in `docker/postgres/init/001-enable-pgvector.sql`. The requested
`scripts/init-postgres-schema.sql` also enables that extension; it is not a
replacement for Alembic migrations.

Check the configured embedding model and vector dimension together before
changing the existing schema or environment defaults.
