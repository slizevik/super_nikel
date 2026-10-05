---
applyTo: "**/*.py"
---

# Архитектурные ограничения

## Трёхзвенная архитектура (СТРОГО СОБЛЮДАТЬ)

### Frontend
- Frontend общается ТОЛЬКО с Backend через HTTP REST API
- Frontend получает данные в формате JSON
- Frontend НИКОГДА не обращается к Neo4j или PostgreSQL напрямую

### Backend (Python API)
- Backend — единственный компонент с доступом к БД
- Neo4j: ТОЛЬКО через Bolt-протокол (порт 7687), официальный драйвер `neo4j`
- PostgreSQL: через `asyncpg` или `SQLAlchemy`
- Backend оркестрирует: Neo4j → LLM → Frontend
- Backend валидирует ответы LLM через Pydantic

### Neo4j
- Доступ ТОЛЬКО из Backend
- Протокол: Bolt (порт 7687), НЕ HTTP (порт 7474)
- Драйвер: `neo4j.AsyncGraphDatabase`
- В Neo4j попадают ТОЛЬКО валидированные сущности

### PostgreSQL
- Хранит: оригиналы PDF, markdown, картинки, векторы, staging-зону
- Таблицы: documents, proposed_entities, proposed_relations, document_embeddings
- pgvector для векторного поиска

### Kafka
- Все межсервисные коммуникации — через события
- Топики: document.uploaded, document.parsed, entities.proposed, entities.validated, entities.persisted, document.failed
- Формат событий: JSON (схемы в libs/kafka-events)

### LLM
- LLM-1 (тяжёлая): извлечение сущностей, работает асинхронно через Kafka
- LLM-2 (лёгкая): формирование ответов, работает синхронно в API
- LLM НЕ имеет прямого доступа к БД
- Backend передаёт в LLM данные из графа как контекст
- LLM ДОЛЖНА возвращать структурированный JSON (Pydantic-схема)

## Human-in-the-Loop
- LLM-1 извлекает сущности → сохраняет в PostgreSQL (proposed_entities) со статусом 'pending'
- Учёный валидирует через UI: approve/reject/edit
- Только после approve сущность переносится в Neo4j
- LLM-1 ДОЛЖНА возвращать: confidence, source_spans, reasoning, is_new