# Architecture decisions

This is a concise decision log for the implementation as it exists today.
Update it when a decision changes; use separate dated ADR files if more detail
is needed.

## Use a modular backend before splitting services

The executable API and ingestion pipeline remain in `backend/`. The parallel
`services/` layout is a scaffold, not an independently deployable set of
workers. Split components only with coordinated runtime, migration, test, and
documentation changes.

## Use Celery and Redis for the current background queue

The current API enqueues work for a Celery worker through Redis. Kafka is not
added until an explicit event-driven service design is approved.

## Keep PostgreSQL and Neo4j responsibilities distinct

PostgreSQL stores document records, job state, and vector chunks; Neo4j has the
knowledge-graph schema. The current ingestion flow has not yet connected the
validated extraction output to graph persistence.

## Keep extraction incomplete until persistence succeeds

`awaiting_persistence` accurately represents extracted but not committed
knowledge. The application must not mark this work completed before graph
persistence succeeds.
