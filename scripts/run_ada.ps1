$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$NodeRoot = Join-Path (Join-Path (Join-Path $ProjectRoot ".ada") "tools") "node-v24.20.0-win-x64"
$NpmCommand = Join-Path $NodeRoot "npm.cmd"
$Python = Join-Path (Join-Path (Join-Path $ProjectRoot ".venv") "Scripts") "python.exe"

if (-not (Test-Path $Python)) {
    throw "Ada's project-local Python is missing. Run scripts/setup_local.ps1 first."
}
if (Test-Path $NpmCommand) {
    $env:PATH = "$NodeRoot;$env:PATH"
} elseif (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Ada's portable Node runtime is missing. Run scripts/setup_local.ps1 first."
} else {
    $NpmCommand = (Get-Command npm -ErrorAction Stop).Source
    Write-Warning "Using PATH npm because the portable Node runtime was not found."
}

$env:ADA_PROJECT_ROOT = $ProjectRoot
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Join-Path $ProjectRoot ".ada") "browsers"
$env:HF_HOME = Join-Path (Join-Path (Join-Path $ProjectRoot ".ada") "cache") "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:PIP_CACHE_DIR = Join-Path (Join-Path (Join-Path $ProjectRoot ".ada") "cache") "pip"
$env:TEMP = Join-Path (Join-Path (Join-Path $ProjectRoot ".ada") "cache") "tmp"
$env:TMP = $env:TEMP

Set-Location $ProjectRoot
& $NpmCommand run dev
exit $LASTEXITCODE
