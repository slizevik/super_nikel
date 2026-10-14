# Снимок проекта

Дата снимка: 2026-10-13

## Назначение

Super Nikel — система загрузки научных PDF, извлечения текста и изображений,
извлечения сущностей/связей по закрытой онтологии и подготовки данных для
будущего графа знаний.

## Фактическая архитектура и сервисы

- **Frontend:** React 18 + TypeScript + Vite в `frontend/`. Общается с backend
  по HTTP; отдельного frontend-сервиса в `docker-compose.yml` нет.
- **API:** FastAPI в `backend/`; принимает PDF, хранит документы и задания,
  предоставляет API списка/загрузки документов, деталей и статуса заданий,
  health endpoints.
- **Фоновые задачи:** Celery worker, брокер и backend результатов — Redis.
  В Compose worker запускается с concurrency=1.
- **Обработка:** Docling преобразует PDF в Markdown и обрабатывает изображения;
  настроенный Yandex LLM описывает полезные изображения и извлекает сущности
  с отношениями. Текущая модель по умолчанию:
  `gpt://b1ghh2ufu3o0t33psog1/deepseek-v4.1-flash/latest`.
- **Артефакты обработки:** Markdown сохраняется в
  `data/processed/<document_id>.md`, сырой ответ извлечения —
  `data/processed/<document_id>.llm-response.txt`. Каталог примонтирован
  worker-контейнеру и исключён из Git.
- **Логи:** структурированные логи backend/worker в stdout и ротируемые файлы
  в `logs/`; содержимое документа и ответа LLM в приложенческие логи не пишется.

## Хранилища и состояние обработки

- **PostgreSQL + pgvector подключены.** Compose использует
  `pgvector/pgvector:0.8.1-pg15`, данные сохраняются в volume `postgres_data`.
- Оригинальный PDF, метаданные и SHA-256 хранятся в таблице `documents`.
  SHA-256 вычисляется, но автоматическая дедупликация загрузок не выполняется.
- Задание хранит разобранный текст, manifest, описания изображений, расход
  токенов, статус и `extraction_result` (JSONB) в `ingestion_jobs`.
- Результат после успешной валидации сохраняется в PostgreSQL со статусом
  `awaiting_persistence`. API заданий возвращает `extraction_result`.
- В проекте есть модель `DocumentChunk` с pgvector embedding, однако это не
  означает, что текущий PDF pipeline записывает извлечённые сущности в векторы.

## Neo4j: подготовлено, но не подключено к pipeline

- В `docker-compose.yml` объявлен Neo4j `5.26-community`, Bolt URI для
  сервисов — `bolt://neo4j:7687`, данные/логи вынесены в volumes.
- Есть Cypher-скрипты онтологии и проверки ограничений в `docker/neo4j/`.
  Загрузка схемы оформлена отдельным Compose-сервисом с profile `schema`.
- Python-пакет `neo4j` указан в `requirements.txt`; настройки URI, пользователя
  и пароля предусмотрены в конфигурации.
- **Не реализованы** клиент Neo4j в backend, вызов из pipeline, запись узлов и
  отношений, связывание их с документом и проверка идемпотентности.
- Поэтому извлечённые сущности сейчас остаются в PostgreSQL JSONB; в Neo4j
  они не попадают. Наличие контейнера и схемы не означает, что графовая БД
  интегрирована с приложением.

## Текущий контракт извлечения

- Закрытая онтология: 12 типов узлов (`Material`, `Process`, `Equipment`,
  `Property`, `Experiment`, `Publication`, `Document`, `Expert`, `Facility`,
  `Condition`, `Country`, `Claim`) и 6 типов отношений с допустимыми
  направлениями в `backend/app/db/ontology.py`.
- Ответ LLM — JSON: `entities`, `relationships`, `unclassified_entities`.
- Максимум — 15 сущностей на документ. Backend проверяет evidence, объединяет
  канонические дубликаты, ранжирует по наличию в ключевых разделах, частоте
  упоминаний и связям, затем оставляет максимум 15; отношения с удалёнными
  концами отбрасываются.
- До 10 отношений. Успешное извлечение ещё не завершает графовую загрузку:
  статус остаётся `awaiting_persistence`.

## Настройки и секреты

Конфигурация загружается через Pydantic Settings из переменных окружения и
локального `.env`; шаблон имён настроек находится в `.env.example`.
Ключи Yandex, пароли и фактические локальные значения `.env` в этот снимок
не включены.

Основные настройки: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`,
`LLM_PROVIDER`, `YANDEX_CLOUD_FOLDER`, `YANDEX_CLOUD_API_KEY`,
`YANDEX_CLOUD_MODEL`, `LLM_REQUEST_TIMEOUT_SECONDS` (default 120),
`TOKEN_LIMIT`, `ENTITY_MIN_OCCURRENCES`, `ANALYZE_DOCUMENT_IMAGES`,
`PARSED_DOCUMENTS_DIR`, параметры chunking и логирования.

Docker Compose также содержит PostgreSQL, Redis, Neo4j и volumes для их данных.
API применяет Alembic migrations при запуске. Перезапуск контейнера сам по себе
не удаляет данные volumes; удаление volumes удаляет соответствующие данные.

## Не реализовано / дальнейшие крупные этапы

- Запись и чтение графа Neo4j из приложения.
- Идемпотентное объединение одинаковых сущностей при повторной загрузке разных
  копий статьи.
- Отдельный validator-worker, Human-in-the-Loop и UI для проверки сущностей.
- Поиск/чат и исследование графа во frontend.
- Kafka не используется: текущая фоновая коммуникация построена на
  Celery + Redis.

## Runtime при составлении снимка

Последняя проверка `docker compose ps --all`: worker был `Up`; backend завершился
с кодом 137, Neo4j — 143, PostgreSQL и Redis — с кодом 0. Это моментальный
статус среды, а не описание целевой конфигурации; перед запуском обработки
нужно проверить/поднять зависимости и API.
