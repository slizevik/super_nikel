Мой план такой.

Цель MVP
Пользователь задаёт вопрос на русском, например:
“Какие датасеты используются в исследованиях по локализации mRNA?”
Система:
переводит вопрос в английский для поиска по научной литературе
ищет релевантные фрагменты в индексированных PDF
использует оба варианта: русское и английское
отвечает на русском, опираясь только на найденные фрагменты
даёт citation на документы/фрагменты
Что исправить в текущей реализации
Сейчас у вас принципиально:
поиск по tsvector по extracted_text
без нормализации терминов
без embeddings
без перевода запроса
без многокодового индексирования по chunk
Это значит:

русские/английские терминологические различия не учитываются
“датасеты” ≠ “datasets”, “benchmark”, “training corpus”, “RNA-seq data”
научные статьи часто пишутся на английском, а вопрос задаётся по-русски
Ключевая идея: hybrid retrieval
Нужно сделать 3 уровня поиска:
Полнотекстовый поиск:

BM25 / PostgreSQL full-text search
по извлечённому тексту статей
быстрый и понятный
хорошо работает для точных совпадений
Нормализация терминов:

привести слова к базовой форме
использовать словарь для scientific terms
добавить aliases:
dataset ↔ datasets ↔ benchmark, cohort, data source, training set
mRNA localization ↔ RNA localization, subcellular localization, transcript localization
RNA-seq ↔ RNAseq, transcriptome sequencing
Embeddings / pgvector:

создать эмбеддинги для чанков текста
индексировать в pgvector
на вопрос искать по смыслу
в итоговом retrieval объединять:
top-k full-text
top-k semantic
top-k translated-query
затем объединять и ранжировать
Это позволит закрыть именно ваш кейс: “я спрашиваю один способ, а в статье термин был другим”.

Перевод сообщения на английский
Нужно сделать отдельный слой query translation, не вплетённый в LLM-ответ. Схема:
Пользователь пишет вопрос на русском
Backend:
сохраняет исходный вопрос
создаёт search_query_en через лёгкий перевод/переход к английским терминам
создаёт search_query_ru для локального русского полнотекстового поиска
Потом запускается retrieval по:
исходной форме
английскому переводу
нормализованным терминам
embeddings
Пример:

RU: “какие датасеты используются”
EN: “which datasets are used”
expanded query:
datasets
dataset
benchmark
training set
data source
RNA-seq data
transcriptome datasets
Ответ на русском, но с английским контекстом
Нужна не одна модель, а правильный пайплайн:
retrieval выбирает релевантные фрагменты
фрагменты могут быть на английском
в prompt для LLM:
“Ты специалист по научным статьям.”
“Используй только эти фрагменты.”
“Отвечай на русском.”
“Если в фрагментах нет ответа, говори, что недостаточно данных.”
т.е. модель читает английские фрагменты, но формирует ответ на русском
это даёт лучшее качество и сохраняет ваш язык интерфейса
Практический план по этапам
Этап 1. Ядро retrieval

сделать chunking по документам
хранить текст чанками
в каждом чанке хранить:
document_id
chunk_id
source_path
page_number
text
language
token_count
добавить индекс по тексту
проверить, что поиск по одному вопросу уже работает на реальных PDF
Задача:

минимальный рабочий pipeline: file → extract text → chunk → index → search by terms
Этап 2. Нормализация терминов и научный словарь

собрать список терминов для вашей тематики:
mRNA localization
RNA localization
subcellular localization
dataset
benchmark
RNA-seq
transcriptomics
cell line
localization studies
добавить synonyms mapping
использовать как расширение query
добавить поддержка английского/русского эквивалентов
Этап 3. Перевод запроса

сделать QueryNormalizer
возвращает:
raw_ru
normalized_ru
translated_en
expanded_terms
for English retrieval use translated_en and expanded_terms
для локального пользователя this is a transparent layer
Этап 4. Hybrid search

объединить:
full-text
semantic vectors
synonym-expanded terms
weight:
full-text 0.45
semantic 0.45
synonyms 0.10
на выходе получаем 10–20 релевантных чанков
Этап 5. Answer pipeline

выбрать 5–8 лучших чанков
отправить их в LLM
strict prompt:
only use retrieved chunks
no external knowledge
answer in Russian
cite document IDs
if weak evidence -> say “не хватает доказательств”
добавить validation:
all cited docs must be in retrieval set
no duplicate document IDs
no hallucination beyond extracted content
Этап 6. Оценка на реальной библиотеке

собрать 30–50 реальных вопросов по вашему направлению
categories:
dataset identification
method search
localization-related articles
mRNA targeting papers
benchmark comparison
оценивать:
recall of relevant papers
citation correctness
answer groundedness
Что сделать прямо сейчас без перегруза
Если хотите быстро войти в рабочий режим, я бы делал так:
Шаг A: добавить query_expansion для русско-английского терминов
Шаг B: добавить translated_query и поиск по английскому варианту
Шаг C: сделать hybrid_search из full-text + embeddings
Шаг D: добавить prompt “ответ на русском, опираясь только на найденные фрагменты”
Шаг E: оценить на 20 реальных вопросах
Это даст вам заметный результат без большой архитектурной “магии”.

Что НЕ нужно на первом этапе
графовая БД как ядро
сложная онтология
full document/entity extraction из старой концепции
LLM на этапе indexing
сложный пользовательский чат с историей и агентами
Рекомендуемый стек под этот MVP
FastAPI
PostgreSQL
pgvector
Redis для задач
Python + PyMuPDF/Docling
Yandex GPT for translation + answering
frontend React/TS
Итоговый вердикт
Да, ваша идея правильная:
сначала именно retrieval quality
потом уже “умный” assistant
без этого проект будет просто “красивой оболочкой вокруг плохого поиска”
Самый правильный MVP для вашей магистерской:

local library of PDFs
English-aware search
hybrid retrieval
Russian answer generation
citation by source
strict no-hallucination rules