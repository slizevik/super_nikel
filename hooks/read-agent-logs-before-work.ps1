$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$agentLogsPath = Join-Path $repoRoot ".agent-logs"

Write-Host "=== Hook: Review agent logs before work ==="

if (-not (Test-Path $agentLogsPath)) {
    Write-Host "The .agent-logs directory was not found. Create it before starting a new task."
    exit 0
}

$recentLogs = Get-ChildItem -Path $agentLogsPath -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5

if (-not $recentLogs) {
    Write-Host "No entries were found in .agent-logs. Start with a clean slate and save a brief log when the task is complete."
    exit 0
}

foreach ($log in $recentLogs) {
    Write-Host ""
    Write-Host "---- $($log.Name) ----"
    Get-Content -Path $log.FullName -Raw -Encoding UTF8
}

Write-Host ""
Write-Host "Review these recent logs before starting the new task."
