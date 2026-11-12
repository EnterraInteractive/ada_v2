[CmdletBinding()]
param(
    [switch]$SkipNode,
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvRoot = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvRoot "Scripts\\python.exe"
$CacheRoot = Join-Path $ProjectRoot ".ada\\cache"

$Directories = @(
    $CacheRoot,
    (Join-Path $CacheRoot "pip"),
    (Join-Path $CacheRoot "huggingface"),
    (Join-Path $CacheRoot "huggingface\\hub"),
    (Join-Path $CacheRoot "xdg"),
    (Join-Path $CacheRoot "torch"),
    (Join-Path $CacheRoot "tmp"),
    (Join-Path $ProjectRoot ".ada\\browsers")
)
New-Item -ItemType Directory -Force -Path $Directories | Out-Null

# Route installer caches and browser downloads into this repository.
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:XDG_CACHE_HOME = Join-Path $CacheRoot "xdg"
$env:TORCH_HOME = Join-Path $CacheRoot "torch"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $ProjectRoot ".ada\\browsers"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = $env:TEMP

Write-Host "A.D.A project-local setup" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Environment: $VenvRoot"
Write-Host "Caches and browser runtime: $CacheRoot"

if (-not (Test-Path $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv $VenvRoot
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $Detected = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($Detected -ne "3.11") {
            throw "Python 3.11 is required to create .venv. Found Python $Detected. Install Python 3.11, then rerun."
        }
        & python -m venv $VenvRoot
    } else {
        throw "Python 3.11 is required. Install Python 3.11, then rerun."
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the project-local Python environment." }
}

if (-not (Test-Path $Python)) { throw "Project-local Python was not created: $Python" }
$Version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($Version -ne "3.11") { throw "The project-local environment must use Python 3.11; found $Version." }

Write-Host "Installing Python dependencies into .venv..." -ForegroundColor Yellow
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip in .venv." }
& $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

if (-not $SkipPlaywright) {
    Write-Host "Installing Chromium into .ada\\browsers..." -ForegroundColor Yellow
    & $Python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }
}

if (-not $SkipNode) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm is required for the React/Electron interface. Install Node.js, then rerun."
    }
    Write-Host "Installing frontend dependencies into node_modules..." -ForegroundColor Yellow
    & npm ci --cache (Join-Path $CacheRoot "npm")
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
}

Write-Host ""
Write-Host "PASS: Python packages, caches, and browser runtime are project-local." -ForegroundColor Green
Write-Host "Next: powershell -ExecutionPolicy Bypass -File scripts\\ai\\install_k2_runtime.ps1"
Write-Host "Then: .\\.venv\\Scripts\\python.exe scripts\\ai\\download_k2_model.py"
Write-Host "Then: .\\.venv\\Scripts\\python.exe scripts\\ai\\verify_k2_runtime.py --full --tool-test"
Write-Host "Note: NVIDIA drivers, CUDA Toolkit 13.x, Git, CMake, and Node.js remain machine-level prerequisites."
