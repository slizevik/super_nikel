
### 6. `.github/instructions/validation.instructions.md`

```markdown
---
applyTo: "services/api/**/validation*.py, services/validator-worker/**/*.py"
---

# Правила для Human-in-the-Loop валидации

## Staging Area (PostgreSQL)
- Таблица proposed_entities хранит ВСЕ предложенные сущности
- Статусы: pending → approved/rejected/edited
- При rejected — сущность остаётся в истории (НЕ удаляется)
- При edited — сохраняется оригинал + версия учёного
- Поля: reviewed_by, reviewed_at, editor_notes

## API для валидации
- GET /documents/{id}/proposed-entities — список предложенных
- POST /documents/{id}/validate — массовая валидация
- PATCH /proposed-entities/{id} — редактирование одной сущности

## Validator Worker
- Подписывается на entities.validated
- Переносит approved/edited сущности в Neo4j
- При edited — проверять уникальность по нормализованному name
- После записи в Neo4j публиковать entities.persisted

## UI требования (для Frontend)
- Показывать цитаты из текста (source_spans)
- Цветовая индикация confidence: зелёный (>0.8), жёлтый (0.5-0.8), красный (<0.5)
- Массовые действия: "одобрить все высокоуверенные", "отклонить все низкоуверенные"
- Явный флаг "НОВАЯ сущность"
- Редактирование на месте (название, синонимы)

## Уведомления
- Фоновая задача: уведомления учёному о pending документах старше 24 часов