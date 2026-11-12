$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Ada's project-local Python was not found. Complete Ada setup before launching the Knowledge Galaxy."
}

$GraphVendor = Join-Path $ProjectRoot "viewer\vendor\3d-force-graph.min.js"
if (-not (Test-Path $GraphVendor)) {
    throw "The offline 3D graph library is missing. Complete npm ci so the pinned vendor is staged under viewer/vendor."
}

try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:8001/status" -TimeoutSec 3
} catch {
    throw "Ada's backend is not running. Start Ada first, then run this launcher again."
}

Push-Location $ProjectRoot
try {
    & $Python ".\build.py"
    if ($LASTEXITCODE -ne 0) { throw "Knowledge Galaxy graph generation failed." }
    Write-Host ""
    Write-Host "Knowledge Galaxy is available at: http://127.0.0.1:4700" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop the local viewer server."
    & $Python ".\server.py"
} finally {
    Pop-Location
}
