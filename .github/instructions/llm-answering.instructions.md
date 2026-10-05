
### 5. `.github/instructions/llm-answering.instructions.md`

```markdown
---
applyTo: "services/api/**/llm*.py, libs/llm-clients/**/*.py"
---

# Правила для LLM-2 (формирование ответов)

## Модель
- Использовать лёгкую модель (например, gpt-4o-mini или gpt-6-luna)
- Температура: 0.3-0.5 (немного креативности для формулировок)
- Максимум токенов: 1000-1500 (лаконичный ответ)

## Формат ответа (Pydantic-схема)
```python
class AnswerResponse(BaseModel):
    summary: str                    # Краткий ответ
    central_entity: str             # Главная сущность запроса
    related_entities: list          # Связанные сущности
    relations_description: str      # Описание связей
    publications: list[PubRef]      # Статьи по релевантности
    confidence: float               # Уверенность (0-1)