# Day Plan: чанкинг, embeddings и hybrid search

## Цель сессии

Перевести поиск по личной библиотеке SuperNikel от поиска по целому `extracted_text` к поиску по качественным фрагментам документов с сохранением страниц, секций и источников.

Целевой поток:

```text
PDF → структурированные текстовые блоки с номерами страниц → стабильные chunks с metadata → embedding каждого chunk → full-text + vector search → объединённые результаты → ответ LLM с проверяемыми цитатами
```

## Контекст проекта

SuperNikel — локальная исследовательская библиотека для статей по машинному обучению и локализации мРНК. Главная ценность — найти подтверждённый фрагмент статьи и получить ответ с источниками.

Основные принципы:

- статьи остаются в локальной папке пользователя;
- сканирование и извлечение текста не требуют генеративного LLM;
- LLM вызывается по явному вопросу пользователя;
- ответы опираются только на найденные фрагменты;
- каждая существенная мысль имеет проверяемый источник;
- retrieval важнее сложного графа знаний.

## Текущее состояние

### PDF parser

`backend/app/services/pdf_parser.py` возвращает `ParsedDocument` с общим markdown, изображениями и manifest. Он использует PyMuPDF, умеет упорядочивать двухколоночный текст, но пока не отдаёт структурированные текстовые блоки с номерами страниц.

### Database

`backend/app/db/models.py` уже содержит `DocumentChunk` с `document_id`, `chunk_index`, `content`, `token_count`, `embedding: Vector(1024)`, `embedding_model` и JSONB metadata. Есть уникальность по `document_id + chunk_index` и HNSW cosine index.

Нужно добавить явные поля `page_start`, `page_end`, `heading` и full-text index по `document_chunks.content`.

### Ingestion

`backend/app/tasks.py` выполняет parse, сохранение текста, анализ изображений и extraction. Создание chunks и embeddings ещё не встроено в рабочий pipeline. Индексация должна быть идемпотентной и безопасной при повторной обработке документа.

### Existing search

Сейчас есть GIN full-text index по `ingestion_jobs.extracted_text` и retrieval в `backend/app/api/routes/answers.py`. Новая реализация должна искать по chunks, сохранив проверку цитат.

## Техническое задание

### 1. Структурированные блоки PDF

Добавить:

```python
@dataclass(frozen=True)
class ParsedTextBlock:
    text: str
    page_number: int
    bbox: tuple[float, float, float, float] | None
    heading: str | None
    block_index: int
```

Расширить `ParsedDocument` полем `blocks: list[ParsedTextBlock]`.

Требования:

- страницы начинаются с 1;
- порядок блоков соответствует чтению;
- пустые блоки исключаются;
- текущая логика двух колонок сохраняется;
- общий markdown остаётся для обратной совместимости;
- heading переносится до нового заголовка;
- при неопределённости `heading = None`;
- bbox сохраняется при наличии.

Заголовки определяются детерминированно: markdown headings, короткие блоки с характерным стилем/размером, нумерованные секции вроде `1 Introduction` и `2.3 Dataset`.

### 2. Chunking service

Создать `backend/app/services/chunking.py` с контрактом:

```python
@dataclass(frozen=True)
class DocumentChunkDraft:
    chunk_index: int
    content: str
    token_count: int
    page_start: int
    page_end: int
    heading: str | None
    char_start: int
    char_end: int
```

Параметры первой версии: target 600 токенов, hard maximum 800, overlap 100. Не разрывать абзац без необходимости; короткие соседние блоки объединять; chunks должны быть стабильными при повторной обработке.

Токенизацию вынести в adapter. Допустим детерминированный fallback по словам с документированным ограничением.

### 3. Metadata

Минимальный metadata:

```json
{
  "page_start": 3,
  "page_end": 4,
  "heading": "2. Methods",
  "char_start": 12450,
  "char_end": 15880,
  "chunker_version": "v1"
}
```

Основные поля страниц и heading хранить также отдельными колонками.

### 4. Embedding abstraction

Создать `EmbeddingProvider` protocol с `model_name`, `dimensions`, `embed_documents()` и `embed_query()`.

Требования: конфигурационные model/dimensions, batch generation, проверка количества и размерности vectors, сохранение `embedding_model`, fake provider для тестов, отсутствие смешивания моделей.

Настройки:

```env
EMBEDDING_PROVIDER=...
EMBEDDING_MODEL=...
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BATCH_SIZE=...
```

Реальный provider подключить после стабилизации контрактов.

### 5. Индексация chunks

После parse: получить blocks, построить drafts, получить embeddings батчами, записать новые chunks и только затем завершить job. При ошибке транзакция откатывается, частичные chunks не остаются. Старые chunks не удалять до готовности новых. Для старых документов предусмотреть отдельную переиндексацию.

### 6. Full-text search

Создать GIN index по `to_tsvector('simple', content)` на `document_chunks`. Запрос возвращает document/chunk id, content, страницы, heading и lexical score.

### 7. Vector search

Использовать `ORDER BY embedding <=> :query_embedding`. Наружу отдавать `similarity = 1 - cosine_distance`. Исключать незавершённые документы, chunks без embedding, недоступные library documents и устаревшие наборы.

### 8. Hybrid retrieval

Создать `backend/app/services/retrieval.py` с `RetrievedChunk` и `search_library()`.

Алгоритм: lexical search, vector search, merge по `chunk_id`, нормализация score в 0–1, расчёт:

```text
hybrid_score = 0.45 * lexical_score + 0.55 * semantic_score
```

При отсутствии результатов одного метода использовать второй. Дедуплицировать одинаковые и почти одинаковые соседние chunks.

### 9. Answers API

Передавать LLM chunks, а не полный extracted text. Источник должен содержать `document_id`, `chunk_id`, title, `page_start`, `page_end`, heading и excerpt. Citation расширить `chunk_id`, страницами, heading и retrieval score. Сохранить запрет на неизвестные citation ids и вызов LLM при пустом результате.

## Что должно быть результатом

1. Parser отдаёт блоки с номерами страниц.
2. Реализован детерминированный chunker.
3. Chunks содержат текст, индекс, страницы, heading и token count.
4. В базе есть поля страницы и heading.
5. Есть embedding abstraction и fake provider.
6. Pipeline создаёт chunks для документа.
7. Есть full-text retrieval по chunks.
8. Есть vector retrieval через pgvector.
9. Есть hybrid retrieval.
10. Answers API получает chunks.
11. Цитаты содержат страницу и chunk id.
12. Существующие и новые тесты проходят.

## Инкремент на сегодня

Обязательно:

- добавить `ParsedTextBlock` и page-aware extraction;
- реализовать `chunking.py` и unit tests;
- добавить миграцию page/heading и GIN index;
- создать embedding protocol и fake provider;
- встроить chunk indexing в ingestion;
- реализовать lexical/vector merge;
- заменить retrieval в answers API;
- обновить citation schema;
- прогнать backend test suite.

Не включать сегодня: сложное распознавание таблиц, reranker, массовую миграцию старых документов, UI переход к страницам, Neo4j retrieval, несколько реальных embedding providers и большой benchmark.

## Критерии готовности

- тестовый PDF создаёт несколько chunks;
- page_start/page_end и heading корректны;
- индексы стабильны;
- embedding dimension проверяется;
- hybrid search объединяет результаты;
- повторная индексация не создаёт дубликаты;
- API содержит chunk/page citation;
- при отсутствии результатов LLM не вызывается;
- все тесты проходят.

## Порядок реализации

1. Уточнить dataclasses parser.
2. Реализовать page-aware blocks.
3. Реализовать chunker и tests.
4. Добавить миграцию и поля модели.
5. Реализовать embedding protocol/fake provider.
6. Встроить chunk indexing.
7. Реализовать lexical retrieval.
8. Реализовать vector retrieval.
9. Реализовать hybrid merge.
10. Интегрировать answers API.
11. Обновить тесты и выполнить проверки.
12. Зафиксировать ограничения и следующий инкремент.

## Открытые вопросы следующего этапа

- выбор реальной мультиязычной embedding-модели;
- локальный inference или внешний API;
- query/document prefixes;
- оценка качества hybrid search;
- переход к PDF по странице и bbox;
- необходимость reranker;
- приоритетные metadata-фильтры;
- массовая переиндексация без блокировки библиотеки.
