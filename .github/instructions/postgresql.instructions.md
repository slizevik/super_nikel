---
applyTo: "**/migrations/**/*.py,**/models.py,**/*postgres*.sql"
---

# PostgreSQL rules

- Treat SQLAlchemy models and Alembic revisions under `backend/migrations/versions/` as the application schema source of truth.
- Add forward-only Alembic migrations for schema changes; do not rely on editing an already-applied revision.
- Preserve constraints, indexes, and foreign-key behavior when changing models.
- Keep the pgvector extension enabled in local initialization. Verify vector dimensions and model configuration agree before changing either.
- Use bound parameters and avoid logging credentials or document contents.
