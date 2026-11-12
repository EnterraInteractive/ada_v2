[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$InstallRoot = Join-Path $ProjectRoot ".ada\tools\VoiceStudio"
$DataRoot = Join-Path $ProjectRoot ".ada\voicestudio-data"
$Executable = Join-Path $InstallRoot "VoiceStudio.exe"

if (-not (Test-Path $Executable)) {
    $Executable = Get-ChildItem -Path $InstallRoot -Filter "VoiceStudio.exe" -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Executable -or -not (Test-Path $Executable)) {
    throw "Project-local VoiceStudio is missing. Run scripts/ai/install_voicestudio.ps1 first."
}

New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$env:OMNIVOICE_DATA_DIR = $DataRoot
Write-Host "Starting project-local VoiceStudio..."
Write-Host "Data, profiles, and model cache: $DataRoot"
Start-Process -FilePath $Executable -WorkingDirectory (Split-Path $Executable)
