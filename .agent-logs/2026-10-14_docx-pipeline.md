Цель: добавить поддержку DOCX в начале ingestion pipeline.
Файлы: backend API/worker, миграция БД, frontend, Compose/Docker, docs, тесты.
Решение: оригинал сохраняется; Celery конвертирует DOCX в PDF через LibreOffice до Docling.
Риски: worker image нужно пересобрать; ошибка/таймаут конвертера завершает job с DOCX_CONVERSION_FAILED.
