[CmdletBinding()]
param(
    [switch]$SkipNode,
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalDataRoot = Join-Path $ProjectRoot ".ada"
$CacheRoot = Join-Path $LocalDataRoot "cache"
$ToolsRoot = Join-Path $LocalDataRoot "tools"
$PythonInstallRoot = Join-Path $LocalDataRoot "python"
$VenvRoot = Join-Path $ProjectRoot ".venv"
$Python = Join-Path (Join-Path $VenvRoot "Scripts") "python.exe"

$Directories = @(
    $CacheRoot,
    (Join-Path $CacheRoot "pip"),
    (Join-Path $CacheRoot "huggingface"),
    (Join-Path (Join-Path $CacheRoot "huggingface") "hub"),
    (Join-Path $CacheRoot "xdg"),
    (Join-Path $CacheRoot "torch"),
    (Join-Path $CacheRoot "tmp"),
    (Join-Path $CacheRoot "downloads"),
    $ToolsRoot,
    $PythonInstallRoot,
    (Join-Path $LocalDataRoot "browsers")
)
New-Item -ItemType Directory -Force -Path $Directories | Out-Null

# All managed interpreters, packages, caches, and browser downloads stay in Ada.
$env:UV_CACHE_DIR = Join-Path $CacheRoot "uv"
$env:UV_PYTHON_INSTALL_DIR = $PythonInstallRoot
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:XDG_CACHE_HOME = Join-Path $CacheRoot "xdg"
$env:TORCH_HOME = Join-Path $CacheRoot "torch"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $LocalDataRoot "browsers"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = $env:TEMP

Write-Host "A.D.A project-local setup" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Python install: $PythonInstallRoot"
Write-Host "Virtual environment: $VenvRoot"
Write-Host "Caches and browser runtime: $CacheRoot"

if (-not (Test-Path $Python)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "Installing managed Python 3.11 under .ada/python..." -ForegroundColor Yellow
        & uv python install 3.11
        if ($LASTEXITCODE -ne 0) { throw "uv could not install Python 3.11 into the project-local Python directory." }
        & uv venv --seed --python 3.11 $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw "uv could not create the project-local .venv." }
    } else {
        throw "uv is required to place the Python runtime itself under .ada/python. Install uv, then rerun scripts/setup_local.ps1."
    }
}

if (-not (Test-Path $Python)) { throw "Project-local Python was not created: $Python" }
$Version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($Version -ne "3.11") { throw "The project-local environment must use Python 3.11; found $Version." }
$BasePrefix = & $Python -c "import sys; print(sys.base_prefix)"
$ResolvedPythonRoot = (Resolve-Path $PythonInstallRoot).Path
if (-not $BasePrefix.StartsWith($ResolvedPythonRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The existing .venv uses Python outside .ada/python. Rename the existing .venv folder and rerun setup_local.ps1 so uv can recreate it with a project-local interpreter."
}

Write-Host "Installing Python dependencies into .venv..." -ForegroundColor Yellow
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip in .venv." }
& $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

if (-not $SkipPlaywright) {
    Write-Host "Installing Chromium into .ada/browsers..." -ForegroundColor Yellow
    & $Python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }
}

$NodeVersion = "v24.20.0"
$NodeFolder = "node-$NodeVersion-win-x64"
$NodeRoot = Join-Path $ToolsRoot $NodeFolder
$NodeExe = Join-Path $NodeRoot "node.exe"
$NpmCommand = Join-Path $NodeRoot "npm.cmd"

if (-not $SkipNode) {
    if (-not (Test-Path $NodeExe)) {
        $NodeArchive = Join-Path (Join-Path $CacheRoot "downloads") "$NodeFolder.zip"
        $NodeUrl = "https://nodejs.org/dist/$NodeVersion/$NodeFolder.zip"
        Write-Host "Downloading portable Node.js $NodeVersion into .ada/tools..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri $NodeUrl -OutFile $NodeArchive -UseBasicParsing
        $ChecksumFile = Join-Path (Join-Path $CacheRoot "downloads") "SHASUMS256.txt"
        Invoke-WebRequest -Uri "https://nodejs.org/dist/$NodeVersion/SHASUMS256.txt" -OutFile $ChecksumFile -UseBasicParsing
        $ChecksumLine = Select-String -Path $ChecksumFile -Pattern ("^([0-9a-fA-F]{64})\s+" + [regex]::Escape("$NodeFolder.zip") + "$") | Select-Object -First 1
        if (-not $ChecksumLine) { throw "Could not find the published SHA-256 for $NodeFolder.zip." }
        $ExpectedHash = $ChecksumLine.Matches[0].Groups[1].Value.ToLowerInvariant()
        $ActualHash = (Get-FileHash -Path $NodeArchive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) { throw "Portable Node archive SHA-256 verification failed." }
        Expand-Archive -Path $NodeArchive -DestinationPath $ToolsRoot -Force
    }
    if (-not (Test-Path $NpmCommand)) { throw "Portable npm was not found under $NodeRoot." }
    $env:PATH = "$NodeRoot;$env:PATH"
    Write-Host "Installing frontend dependencies into node_modules..." -ForegroundColor Yellow
    & $NpmCommand ci --cache (Join-Path $CacheRoot "npm")
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
} elseif (Test-Path $NodeExe) {
    $env:PATH = "$NodeRoot;$env:PATH"
} elseif (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not available. Run setup_local.ps1 without -SkipNode to install portable Node."
}

# Copy MediaPipe's WASM binaries into Vite's public folder so gesture tracking
# does not fetch code from jsDelivr at runtime.
$MediapipeSource = Join-Path $ProjectRoot "node_modules/@mediapipe/tasks-vision/wasm"
$MediapipeDestination = Join-Path $ProjectRoot "public/mediapipe/wasm"
if (-not (Test-Path $MediapipeSource)) {
    throw "MediaPipe WASM files are missing. Run setup_local.ps1 without -SkipNode to install frontend dependencies."
}
New-Item -ItemType Directory -Force -Path $MediapipeDestination | Out-Null
Copy-Item -Path (Join-Path $MediapipeSource "*") -Destination $MediapipeDestination -Recurse -Force

Write-Host ""
Write-Host "PASS: Python runtime, Python packages, Node.js, npm packages, caches, MediaPipe WASM, and browser runtime are project-local." -ForegroundColor Green
Write-Host "Next: powershell -ExecutionPolicy Bypass -File scripts/ai/install_k2_runtime.ps1"
Write-Host "Then: .venv/Scripts/python.exe scripts/ai/download_k2_model.py"
Write-Host "Then: .venv/Scripts/python.exe scripts/ai/verify_k2_runtime.py --full --tool-test"
Write-Host "Note: NVIDIA driver, CUDA Toolkit 13.x, Git, CMake, and uv remain machine-level prerequisites."
