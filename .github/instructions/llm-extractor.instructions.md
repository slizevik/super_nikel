---
applyTo: "services/extractor-worker/**/*.py"
---

# Правила для LLM-1 (извлечение сущностей)

## Модель
- Использовать тяжёлую модель (например, gpt-4o)
- Температура: 0.0-0.2 (точность, не креативность)
- Максимум токенов ответа: до 32768 (с учётом доступного token budget задания)

## Формат ответа (Pydantic-схема)
```python
class ProposedEntity(BaseModel):
    label: str                    # Material, Process, etc. (из GLOSSARY.md)
    name: str
    properties: dict
    confidence: float             # 0.0 - 1.0
    source_spans: list[str]       # Цитаты из текста (50-200 символов)
    reasoning: str                # Почему это важная сущность (1-2 предложения)
    is_new: bool                  # Есть ли уже в графе
    suggested_relations: list[ProposedRelation]