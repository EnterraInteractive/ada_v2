[CmdletBinding()]
param(
    [switch]$SkipVoiceStudio,
    [switch]$SkipGalaxy
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PowerShell = (Get-Process -Id $PID).Path
$VoiceLauncher = Join-Path $ProjectRoot "scripts\run_voicestudio.ps1"
$AdaLauncher = Join-Path $ProjectRoot "scripts\run_ada.ps1"
$GalaxyLauncher = Join-Path $ProjectRoot "scripts\run_knowledge_galaxy.ps1"

function Test-LocalEndpoint([string]$Url) {
    try {
        $null = Invoke-RestMethod -Uri $Url -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

if (-not $SkipVoiceStudio -and -not (Test-LocalEndpoint "http://127.0.0.1:3900/health")) {
    Write-Host "Starting project-local VoiceStudio..." -ForegroundColor Cyan
    Start-Process -FilePath $PowerShell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$VoiceLauncher`"" -WorkingDirectory $ProjectRoot
}

if (-not (Test-LocalEndpoint "http://127.0.0.1:8001/status")) {
    Write-Host "Starting A.D.A..." -ForegroundColor Cyan
    Start-Process -FilePath $PowerShell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$AdaLauncher`"" -WorkingDirectory $ProjectRoot
}

$Deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $Deadline -and -not (Test-LocalEndpoint "http://127.0.0.1:8001/status")) {
    Start-Sleep -Seconds 2
}
if (-not (Test-LocalEndpoint "http://127.0.0.1:8001/status")) {
    throw "A.D.A did not become ready on 127.0.0.1:8001. Check the A.D.A terminal window."
}

if (-not $SkipGalaxy -and -not (Test-LocalEndpoint "http://127.0.0.1:4700/health")) {
    Write-Host "Starting the Knowledge Galaxy viewer..." -ForegroundColor Cyan
    Start-Process -FilePath $PowerShell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$GalaxyLauncher`"" -WorkingDirectory $ProjectRoot
    $ViewerDeadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $ViewerDeadline -and -not (Test-LocalEndpoint "http://127.0.0.1:4700/health")) {
        Start-Sleep -Seconds 1
    }
}
if (-not $SkipGalaxy -and (Test-LocalEndpoint "http://127.0.0.1:4700/health")) {
    Start-Process "http://127.0.0.1:4700"
}

Write-Host "A.D.A is running locally. VoiceStudio is optional; Piper and local browser speech remain available as fallbacks." -ForegroundColor Green
