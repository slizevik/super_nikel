# Промпты для LLM

## LLM-1: Извлечение сущностей (тяжёлая модель)

### Задача
Извлечь из markdown-документа сущности и связи в соответствии с текущей схемой `backend/app/schemas/extraction.py`.

### Вход
- markdown-текст
- закрытый список допустимых типов сущностей из `backend/app/db/ontology.py`
- контекст исходного документа

### Выход (JSON, Pydantic-схема)
```python
class ExtractedEntity(BaseModel):
    id: str
    type: EntityType
    label: str
    canonical_label: str
    aliases: list[str]
    evidence: str

class ExtractedRelationship(BaseModel):
    source_id: str
    target_id: str
    type: RelationshipType
    evidence: str

class UnclassifiedEntity(BaseModel):
    text: str
    context: str

class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
    unclassified_entities: list[UnclassifiedEntity] = []
```

### Правила
- Всегда возвращать все три верхнеуровневых ключа: `entities`,
  `relationships`, `unclassified_entities`; для отсутствующей категории
  возвращать пустой массив.
- Не возвращать `{}`. Если типизированные сущности и связи не подтверждаются,
  вернуть пустые массивы и отдельно перечислить подходящие
  `unclassified_entities`; все три пустых массива допустимы только если в
  документе нет релевантных сущностей.
- `entities` и `relationships` должны ссылаться друг на друга по `id`/`source_id`/`target_id`.
- Все типы сущностей и связи должны быть из `EntityType` и `RelationshipType`.
- `evidence` должен содержать подтверждение из текста.
- `relationships` запрещено создавать для сущностей, которых нет в `entities`.
- Для `unclassified_entities` сохраняются термины без привязки к закрытой онтологии.

## LLM-2: Формирование ответа (лёгкая модель)

### Задача
Генерировать ответ по фактическим данным из текущего приложения, не выдумывая источники, сущности или связи.

### Вход
- пользовательский запрос
- данные из базы/источников, полученные в контексте запроса
- релевантные публикации и метаданные документа

### Выход (JSON, Pydantic-схема)
```python
class AnswerResponse(BaseModel):
    summary: str
    central_entity: str
    related_entities: list
    relations_description: str
    publications: list[PubRef]
    confidence: float
```

### Правила
- Ответ должен строиться на основании проверенных данных, а не на догадках модели.
- Не заполнять поля в обход текущего контракта.
- Не создавать новые типы сущностей или связи, если они не предусмотрены схемой.