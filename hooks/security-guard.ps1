param(
    [string[]]$Targets = @(),
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Test-RepoPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        return $false
    }

    $repo = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\\')
    $full = $full.TrimEnd('\\')

    return $full.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)
}

$dangerousPatterns = @(
    'rm -rf',
    'rm\s+-rf',
    'Remove-Item\s+-Recurse\s+-Force',
    'Delete-Item\s+-Recurse\s+-Force',
    'git\s+reset\s+--hard',
    'git\s+clean\s+-fd',
    'drop\s+database',
    'DROP\s+DATABASE',
    'del\s+/s\s+/q',
    'rmdir\s+/s\s+/q',
    'Remove-Item\s+-LiteralPath\s+.*(\\|/)',
    'git\s+checkout\s+--\s+\.'
)

$commandText = $Targets -join " "
foreach ($pattern in $dangerousPatterns) {
    if ($commandText -match $pattern) {
        Write-Error "Security guard blocked dangerous action: '$pattern'"
        exit 1
    }
}

$workspaceTargets = if ($Targets.Count -gt 0) { $Targets } else { @((Get-Location).Path) }
foreach ($candidate in $workspaceTargets) {
    if (-not (Test-RepoPath -Path $candidate)) {
        Write-Error "Security guard blocked access outside repository: '$candidate'"
        exit 1
    }
}

Write-Host "[security-guard] Passed. Target scope is within the repository."
exit 0
