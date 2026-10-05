---
applyTo: "libs/neo4j-client/**/*.py, services/**/neo4j*.py"
---

# Правила для Neo4j

## Подключение
- Использовать ТОЛЬКО `neo4j.AsyncGraphDatabase`
- Протокол: Bolt (`bolt://` или `neo4j://`), порт 7687
- НЕ использовать HTTP API (порт 7474)
- Пул соединений настраивать через `AsyncDriver`

## Запросы
- Все операции записи — в транзакциях (`async with session.begin()`)
- Использовать MERGE вместо CREATE для идемпотентности
- Все узлы должны иметь свойство `source_document_id: str`
- Индексы создавать в `scripts/init-neo4j-schema.py`
- НЕ использовать APOC без явного указания в задаче
- Параметризовать запросы, НЕ конкатенировать строки

## Схема (из docs/SCHEMA_NEO4J.md)
- Узлы: Material, Process, Equipment, Property, Experiment, Publication, Document, Expert, Facility, Condition, Country, Claim
- Связи: USED_IN, USED_WITH, MEASURED, DESCRIBED_IN, AUTHORED_BY, AFFILIATED_WITH, LOCATED_IN, CONDUCTED_UNDER, CONTAINS, MENTIONED_IN
- НЕ придумывать новые labels или relation types

## Валидированные сущности
- В Neo4j попадают ТОЛЬКО сущности со статусом 'approved' или 'edited'
- Узлы получают свойства: `validated_by`, `validated_at`, `source_documents`
- При edited — проверять уникальность по нормализованному name (lowercase, trim)

## Логирование
- Логировать: query_text (DEBUG), execution_time_ms, records_fetched
- Ошибки ConstraintValidationFailed — WARNING (ожидаемое поведение при дублях)