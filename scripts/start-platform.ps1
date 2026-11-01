param([switch]$SkipBuild)
$ErrorActionPreference='Stop'
$platformRoot=Split-Path -Parent $PSScriptRoot
Push-Location $platformRoot
try {
    if (-not $SkipBuild) {
        Push-Location (Join-Path $platformRoot 'frontend')
        try {
            if (-not (Test-Path -LiteralPath 'node_modules')) { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' } }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }
    & (Join-Path $platformRoot '.venv\Scripts\python.exe') -m uvicorn api.main:app --host 127.0.0.1 --port 8000
} finally { Pop-Location }
