[CmdletBinding()]
param(
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ToolsRoot = Join-Path $ProjectRoot ".ada\tools"
$DownloadRoot = Join-Path $ProjectRoot ".ada\cache\downloads\voicestudio"
$InstallRoot = Join-Path $ToolsRoot "VoiceStudio"
$DataRoot = Join-Path $ProjectRoot ".ada\voicestudio-data"
$InstallerPath = $null

New-Item -ItemType Directory -Force -Path $ToolsRoot, $DownloadRoot, $DataRoot | Out-Null
$ExistingExe = Join-Path $InstallRoot "VoiceStudio.exe"
if (-not (Test-Path $ExistingExe)) {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/debpalash/VoiceStudio/releases/latest" -Headers @{ "Accept" = "application/vnd.github+json" }
    $Asset = $Release.assets | Where-Object { $_.name -match '^VoiceStudio-[0-9.]+-win-x64\.exe$' } | Select-Object -First 1
    $Checksums = $Release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
    if (-not $Asset -or -not $Checksums) { throw "The latest VoiceStudio Windows installer or checksum file was not found." }

    $InstallerPath = Join-Path $DownloadRoot $Asset.name
    $ChecksumPath = Join-Path $DownloadRoot "SHA256SUMS.txt"
    if (-not (Test-Path $InstallerPath)) {
        Invoke-WebRequest -Uri $Asset.browser_download_url -OutFile $InstallerPath -UseBasicParsing
    }
    Invoke-WebRequest -Uri $Checksums.browser_download_url -OutFile $ChecksumPath -UseBasicParsing
    $ChecksumLine = Select-String -Path $ChecksumPath -Pattern ("^([0-9a-fA-F]{64})\s+\*?" + [regex]::Escape($Asset.name) + "$") | Select-Object -First 1
    if (-not $ChecksumLine) { throw "The VoiceStudio release checksum did not contain $($Asset.name)." }
    $Expected = $ChecksumLine.Matches[0].Groups[1].Value.ToLowerInvariant()
    $Actual = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Expected -ne $Actual) { throw "VoiceStudio installer SHA-256 verification failed." }

    Write-Host "Installing VoiceStudio into $InstallRoot..." -ForegroundColor Yellow
    $Process = Start-Process -FilePath $InstallerPath -ArgumentList @("/S", "/D=$InstallRoot") -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw "VoiceStudio installer returned exit code $($Process.ExitCode)." }
}
if (-not (Test-Path $ExistingExe)) {
    $Found = Get-ChildItem -Path $InstallRoot -Filter "VoiceStudio.exe" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Found) { throw "VoiceStudio.exe was not found under $InstallRoot after installation." }
    $ExistingExe = $Found.FullName
}

Write-Host "VoiceStudio app: $ExistingExe"
Write-Host "VoiceStudio data and model directory: $DataRoot"
Write-Host "VoiceStudio is installed project-locally. Run scripts/run_voicestudio.ps1 to start it."
if ($Launch) {
    $env:OMNIVOICE_DATA_DIR = $DataRoot
    Start-Process -FilePath $ExistingExe -WorkingDirectory (Split-Path $ExistingExe)
}
