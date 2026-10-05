# Application logs

The API and Celery worker write structured JSON Lines logs to separate,
rotating files:

- `logs/api/api.jsonl` — API and HTTP request events
- `logs/worker/worker.jsonl` — document processing events and errors

Log files are local runtime data and are ignored by Git. Each file keeps the
current log and up to five rotated files of 10 MiB each by default. Settings
can be changed with `LOG_DIR`, `LOG_LEVEL`, `LOG_MAX_BYTES`, and
`LOG_BACKUP_COUNT` in `.env`.

From the repository root, follow the files in PowerShell:

```powershell
Get-Content .\logs\api\api.jsonl -Wait
Get-Content .\logs\worker\worker.jsonl -Wait
```

Filter for error events:

```powershell
Select-String -Path .\logs\api\api.jsonl,.\logs\worker\worker.jsonl -Pattern '"level":"error"'
```

Docker also retains bounded stdout logs. Follow both application services with:

```powershell
docker compose logs -f backend worker
```

HTTP responses include an `X-Request-ID`. API log entries contain that request
ID; worker entries include `job_id` and `document_id` for correlating ingestion
events. Do not log credentials, request bodies, or full document contents.
