$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$agentLogsPath = Join-Path $repoRoot ".agent-logs"

Write-Host "=== Hook: читать agent-logs перед работой ==="

if (-not (Test-Path $agentLogsPath)) {
    Write-Host "Каталог .agent-logs не найден. Создайте его перед началом новой задачи."
    exit 0
}

$recentLogs = Get-ChildItem -Path $agentLogsPath -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5

if (-not $recentLogs) {
    Write-Host "В .agent-logs пока нет записей. Начни задачу с чистого листа и сохраняй краткий лог после завершения."
    exit 0
}

foreach ($log in $recentLogs) {
    Write-Host ""
    Write-Host "---- $($log.Name) ----"
    Get-Content -Path $log.FullName -Raw
}

Write-Host ""
Write-Host "Сделай выводы из последних логов до старта новой задачи."
