param(
    [string]$InputPath,
    [int]$MaxChars = 8000,
    [int]$MaxLines = 200
)

$ErrorActionPreference = "Stop"

function Get-Text {
    if ($InputPath) {
        if (-not (Test-Path -Path $InputPath)) {
            throw "Input file not found: $InputPath"
        }

        return [System.IO.File]::ReadAllText($InputPath)
    }

    return [Console]::In.ReadToEnd()
}

$text = Get-Text
if ([string]::IsNullOrWhiteSpace($text)) {
    Write-Output "[tool-output-compress] Empty output; no compression needed."
    exit 0
}

$lines = $text -split "`r?`n"
$length = $text.Length

if ($length -le $MaxChars -and $lines.Length -le $MaxLines) {
    Write-Output $text
    exit 0
}

$keepHead = ($lines | Select-Object -First $MaxLines) -join "`n"
$keepTail = ($lines | Select-Object -Last $MaxLines) -join "`n"

Write-Output "[tool-output-compress] Output truncated from $length chars and $($lines.Length) lines."
Write-Output "[tool-output-compress] Showing first $MaxLines lines and last $MaxLines lines."
Write-Output "--- BEGIN HEAD ---"
Write-Output $keepHead
Write-Output "--- OMITTED MIDDLE ---"
Write-Output $keepTail
Write-Output "--- END ---"
exit 0
