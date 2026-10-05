-- Application tables are managed by Alembic. This script enables pgvector
-- when preparing a PostgreSQL database outside the Docker initialization path.
CREATE EXTENSION IF NOT EXISTS vector;
