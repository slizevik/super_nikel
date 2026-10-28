param(
    [string[]]$ChangedFiles = @()
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-GuardedCommand {
    param(
        [string]$Label,
        [string]$Command
    )

    Write-Host "[lint] $Label"
    & powershell -NoLogo -Command $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed."
    }
}

function Get-AvailablePythonTools {
    $tools = @()
    $null = & python -m ruff --version 2>$null
    if ($LASTEXITCODE -eq 0) { $tools += "ruff" }

    $null = & python -m mypy --version 2>$null
    if ($LASTEXITCODE -eq 0) { $tools += "mypy" }

    return $tools
}

if ($ChangedFiles.Count -eq 0) {
    $ChangedFiles = @(
        Get-ChildItem -Path $repoRoot -Recurse -File |
        Where-Object {
            $_.Extension -in ".py", ".ts", ".tsx", ".js", ".jsx"
        } |
        Select-Object -ExpandProperty FullName
    )
}

$pythonFiles = @($ChangedFiles | Where-Object { $_ -match '\.py$' })
$tsFiles = @($ChangedFiles | Where-Object { $_ -match '\.(ts|tsx|js|jsx)$' })

if ($pythonFiles.Count -gt 0) {
    $available = Get-AvailablePythonTools
    if ($available.Count -eq 0) {
        Write-Host "[lint] Python static tools not installed. Skipping Python lint."
    }
    else {
        if ($available -contains "ruff") {
            Invoke-GuardedCommand -Label "ruff" -Command "python -m ruff check $($pythonFiles -join ' ')"
        }

        if ($available -contains "mypy") {
            Invoke-GuardedCommand -Label "mypy" -Command "python -m mypy $($pythonFiles -join ' ') --config-file '$repoRoot\pyproject.toml'"
        }
    }
}

if ($tsFiles.Count -gt 0) {
    $frontendDir = Join-Path $repoRoot "frontend"
    if (Test-Path (Join-Path $frontendDir "package.json")) {
        Push-Location $frontendDir
        try {
            $tscAvailable = & npx tsc --noEmit 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[lint] TypeScript check passed."
            }
            else {
                Write-Host "[lint] TypeScript check failed."
                exit 1
            }

            $eslintPackage = Join-Path $frontendDir "node_modules\eslint"
            if (Test-Path $eslintPackage) {
                & npx eslint . --ext .ts,.tsx,.js,.jsx
                if ($LASTEXITCODE -ne 0) {
                    exit 1
                }
            }
            else {
                Write-Host "[lint] eslint not installed; skipping JS lint."
            }
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Host "[lint] Frontend project not found; skipping TS lint."
    }
}

Write-Host "[lint] Post-execution validation completed."
exit 0
