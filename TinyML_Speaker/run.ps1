param(
    [ValidateSet('setup', 'replay', 'train', 'receive', 'annotate', 'merge', 'evaluate', 'viewer', 'test')]
    [string]$Action = 'receive',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if ($Action -eq 'setup') {
    if (-not (Test-Path -LiteralPath $python)) {
        & python -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run .\run.ps1 setup first.'
}
if ($Action -eq 'test') {
    Push-Location $PSScriptRoot
    try { & $python -m pytest -q; $result = $LASTEXITCODE }
    finally { Pop-Location }
    exit $result
}
& $python (Join-Path $PSScriptRoot 'pipeline.py') $Action @CommandArgs
exit $LASTEXITCODE
