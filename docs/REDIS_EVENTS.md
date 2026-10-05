# События Redis Streams

## Обзор
 используется Redis Streams для асинхронной коммуникации между микросервисами. 
Redis Streams гарантирует доставку сообщений, поддерживает consumer groups и dead-letter queues.

## Основные стримы

### 1. `document:uploaded`
- **Producer:** Backend API
- **Consumer:** Parser Worker (Docling)
- **Описание:** Инициация пайплайна обработки нового PDF.
- **Payload:**
  ```json
  {
    "document_id": "uuid-string",
    "file_path": "/path/to/uploaded/file.pdf",
    "uploaded_by": "user_id_or_name",
    "timestamp": "2023-10-25T10:00:00Z"
  }