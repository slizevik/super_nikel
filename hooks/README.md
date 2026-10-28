# Hooks

## read-agent-logs-before-work.ps1

Этот hook напоминает, что перед началом новой задачи нужно быстро посмотреть последние записи в `.agent-logs` и учесть уже принятые решения, ограничения и предыдущее состояние проекта.

Запуск:

```powershell
powershell -File .\hooks\read-agent-logs-before-work.ps1
```

## security-guard.ps1

Блокирует опасные действия: удаление файлов и каталогов, сброс Git-истории, запись вне рабочего репозитория, попытки работать с внешними путями. Используется как защитный gate перед критическими операциями.

Запуск:

```powershell
powershell -File .\hooks\security-guard.ps1 -Targets @('C:\develop\super_nikel\backend\app')
```

## tool-output-compress.ps1

Сжимает длинный вывод инструментов, чтобы не перегружать контекст и не терять полезные хвосты логов. Показывает начало и конец, сокращая перегруженный вывод.

Запуск:

```powershell
powershell -File .\hooks\tool-output-compress.ps1 -InputPath .\logs\api\api.jsonl -MaxChars 8000 -MaxLines 200
```

## post-execution-lint.ps1

Запускает минимальную валидацию после изменения кода: Python lint/typing при наличии и TS check для frontend. Если найдены ошибки, процесс завершается с ошибкой и возвращает диагностическую информацию агенту.

Запуск:

```powershell
powershell -File .\hooks\post-execution-lint.ps1 -ChangedFiles @(
  'C:\develop\super_nikel\backend\app\api\routes\documents.py',
  'C:\develop\super_nikel\frontend\src\App.tsx'
)
```
