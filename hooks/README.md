# Hooks

## read-agent-logs-before-work.ps1

This hook displays the latest entries in `.agent-logs` before a new task, helping
you review prior decisions, constraints, and project state.

Run:

```powershell
powershell -File .\hooks\read-agent-logs-before-work.ps1
```

## security-guard.ps1

Blocks dangerous actions such as deleting files or directories, resetting Git
history, writing outside the repository, and accessing paths outside the
workspace. Use it as a safety gate before critical operations.

Run:

```powershell
powershell -File .\hooks\security-guard.ps1 -Targets @('C:\develop\super_nikel\backend\app')
```

## tool-output-compress.ps1

Compresses long tool output to reduce context usage while preserving useful
information from the beginning and end of the output.

Run:

```powershell
powershell -File .\hooks\tool-output-compress.ps1 -InputPath .\logs\api\api.jsonl -MaxChars 8000 -MaxLines 200
```

## post-execution-lint.ps1

Runs basic validation after code changes: Python lint/type checks when
available, and a TypeScript check for the frontend. Exits with an error and
prints diagnostics when a check fails.

Run:

```powershell
powershell -File .\hooks\post-execution-lint.ps1 -ChangedFiles @(
  'C:\develop\super_nikel\backend\app\api\routes\documents.py',
  'C:\develop\super_nikel\frontend\src\App.tsx'
)
```
