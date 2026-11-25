param([switch]$SkipBuild, [switch]$WithRaceHost)
# Starts the Race Hype engine (and site) on http://127.0.0.1:8000.
#   -SkipBuild     reuse the existing frontend build
#   -WithRaceHost  also start the optional "Emma" OBS host service (services/stream_host.py, port 8172).
#                  It is an experiment kept for manual use: the race broadcast, fullscreen view, team radio and the
#                  AI commentator never depend on it. Its OBS overlay is /design/race-host/index.html.
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
    $python = Join-Path $platformRoot '.venv\Scripts\python.exe'
    $hostService = $null
    if ($WithRaceHost) {
        Write-Host 'Starting the optional race host (Emma) on http://127.0.0.1:8172 - OBS overlay: http://127.0.0.1:8000/design/race-host/index.html'
        $hostService = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','services.stream_host:app','--host','127.0.0.1','--port','8172' -WindowStyle Hidden -PassThru
    }
    try {
        & $python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
    } finally {
        if ($hostService -and !$hostService.HasExited) { $hostService.Kill($true) }
    }
} finally { Pop-Location }
