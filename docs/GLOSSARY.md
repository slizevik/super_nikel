# Словарь сущностей графа

## Узлы (Node Labels)

| Label | Описание | Пример | Ключевые свойства |
|-------|----------|--------|-------------------|
| Material | материал | никель, сульфат никеля, сплав Fe-Ni | name, formula, synonyms |
| Process | процесс | кучное выщелачивание, биоокисление | name, description |
| Equipment | оборудование | реактор, колонна, автоклав | name, type |
| Property | свойство | концентрация, pH, температура | name, unit, value_range |
| Experiment | эксперимент | серия опытов из статьи | id, description, date |
| Publication | публикация | статья, доклад | title, doi, year, authors |
| Document | загруженный документ | PDF/DOCX/PPTX | filename, upload_date, path |
| Expert | эксперт | автор, исследователь | name, affiliation |
| Facility | лаборатория/институт | ИМет УрО РАН | name, country |
| Condition | условие | холодный климат, режим 80°C | name, value, unit |
| Country | страна | Россия, Китай | name, code |
| Claim | утверждение | (этап 2) | text, confidence, source |

## Отношения (Relationship Types)

| Тип | От → К | Пример |
|-----|--------|--------|
| uses_material | Process, Experiment → Material | процесс использует материал |
| operates_at_condition | Process, Equipment → Condition | оборудование работает при заданном условии |
| produces_output | Process, Experiment → Property | процесс даёт выходное свойство |
| described_in | Any defined type except Document → Document | сущность описана в документе |
| validated_by | Experiment, Claim → Expert, Publication | эксперимент подтверждён экспертом или публикацией |
| contradicts | Claim → Claim | утверждение противоречит другому утверждению |

## Правила
- НЕ придумывать новые labels или relation types без обсуждения
- При добавлении новой сущности — обновить этот файл
- Текущий проект использует закрытую онтологию, закреплённую в `backend/app/db/ontology.py`
- Human-in-the-Loop является будущей функцией и пока не считается текущим runtime-сценарием