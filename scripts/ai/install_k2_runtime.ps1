[CmdletBinding()]
param([switch]$ForceRebuild)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildRoot = Join-Path $ProjectRoot ".ada\build\k2-runtime"
$DownloadRoot = Join-Path $BuildRoot "downloads"
$SourceRoot = Join-Path $BuildRoot "llama-cpp-python"
$VendorRoot = Join-Path $SourceRoot "vendor\llama.cpp"
$StampRoot = Join-Path $ProjectRoot ".ada"
$StampFile = Join-Path $StampRoot "llama-cpp-build.json"
Set-Location $ProjectRoot

Write-Host "A.D.A K2-Horizon runtime setup" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Build:   $BuildRoot"

$LocalPython = Join-Path (Join-Path (Join-Path $ProjectRoot ".venv") "Scripts") "python.exe"
if (-not (Test-Path $LocalPython)) {
    throw "Project-local Python was not found. Run powershell -ExecutionPolicy Bypass -File scripts/setup_local.ps1 first."
}
$Python = $LocalPython
$CacheRoot = Join-Path (Join-Path $ProjectRoot ".ada") "cache"
$env:PIP_CACHE_DIR = Join-Path $CacheRoot "pip"
$env:HF_HOME = Join-Path $CacheRoot "huggingface"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PIP_CACHE_DIR,$env:HF_HOME,$env:HUGGINGFACE_HUB_CACHE,$env:TEMP | Out-Null

$PythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($PythonVersion -ne "3.11") {
    throw "This pinned Windows build targets Python 3.11. Selected interpreter is $Python ($PythonVersion). Run scripts\\setup_local.ps1 with Python 3.11."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required." }
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { throw "CMake is required." }
if (-not (Get-Command nvcc -ErrorAction SilentlyContinue)) { throw "CUDA Toolkit 13.x is required for the RTX 5070 build." }

$CudaVersion = (& nvcc --version | Select-String -Pattern "release\s+(\d+\.\d+)" | Select-Object -First 1).Matches.Groups[1].Value
if (-not $CudaVersion.StartsWith("13.")) { throw "This profile targets CUDA 13.x. Detected CUDA $CudaVersion." }

New-Item -ItemType Directory -Force -Path $DownloadRoot,$StampRoot | Out-Null
$Sdist = Join-Path $DownloadRoot "llama_cpp_python-0.3.36.tar.gz"
if (-not (Test-Path $Sdist)) {
    & $Python -m pip download --no-deps --no-binary=:all: --dest $DownloadRoot "llama-cpp-python==0.3.36"
    if ($LASTEXITCODE -ne 0) { throw "Could not download llama-cpp-python source distribution." }
}

if ((Test-Path $SourceRoot) -and $ForceRebuild) { Remove-Item -Recurse -Force $SourceRoot }
if (-not (Test-Path (Join-Path $SourceRoot "pyproject.toml"))) {
    & $Python -c "import tarfile; tarfile.open(r'$Sdist','r:gz').extractall(r'$BuildRoot')"
    $Extracted = Join-Path $BuildRoot "llama_cpp_python-0.3.36"
    if (-not (Test-Path $Extracted)) { throw "Unexpected source archive layout." }
    if (Test-Path $SourceRoot) { Remove-Item -Recurse -Force $SourceRoot }
    Move-Item $Extracted $SourceRoot
}

$PinnedMarker = Join-Path $VendorRoot ".ada-k2-b11454"
if (-not (Test-Path $PinnedMarker) -or $ForceRebuild) {
    # The PyPI source archive includes an older llama.cpp tree. Always replace it;
    # merely checking for CMakeLists.txt would leave the incompatible source in place.
    if (Test-Path $VendorRoot) { Remove-Item -Recurse -Force $VendorRoot }
    New-Item -ItemType Directory -Force -Path (Split-Path $VendorRoot -Parent) | Out-Null
    & git clone --depth 1 --branch b11454 https://github.com/ggml-org/llama.cpp.git $VendorRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch llama.cpp b11454 (K2-Horizon architecture and chat/tool support)." }
    Set-Content -Path $PinnedMarker -Value "ggml-org/llama.cpp b11454" -Encoding ASCII
}
$LlamaCommit = (& git -C $VendorRoot rev-parse HEAD).Trim()
if (-not $LlamaCommit) { throw "Could not identify the llama.cpp source revision." }

# RTX 5070 is Blackwell consumer architecture (compute capability 12.0 / sm_120).
$env:CMAKE_ARGS = "-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120"
$env:FORCE_CMAKE = "1"
$env:CMAKE_BUILD_PARALLEL_LEVEL = [Math]::Max(4, [Environment]::ProcessorCount - 2).ToString()
Write-Host "Building embedded llama-cpp-python against llama.cpp b11454 ($LlamaCommit)." -ForegroundColor Yellow
Write-Host "CUDA: $CudaVersion | GPU target: sm_120"
& $Python -m pip install --force-reinstall --no-cache-dir $SourceRoot
if ($LASTEXITCODE -ne 0) { throw "CUDA build failed. Preserve this terminal output for diagnosis." }

$Verification = & $Python -c "import importlib.metadata as m, llama_cpp; print(m.version('llama-cpp-python')); print('GPU_OFFLOAD=' + str(bool(llama_cpp.llama_supports_gpu_offload()))); print(llama_cpp.llama_print_system_info())"
if ($LASTEXITCODE -ne 0 -or ($Verification -join [Environment]::NewLine) -notmatch "GPU_OFFLOAD=True") {
    throw "The package installed but GPU offload verification failed."
}
$BuildInfo = [ordered]@{
    package = "llama-cpp-python"
    package_version = "0.3.36"
    llama_cpp_release = "b11454"
    llama_cpp_commit = $LlamaCommit
    cuda_toolkit = $CudaVersion
    cuda_architecture = "sm_120"
    build_type = "CUDA"
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
}
$BuildInfo | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $StampFile
Write-Host "K2 runtime build installed." -ForegroundColor Green
Write-Host "Build record: $StampFile"
Write-Host "Next: .venv/Scripts/python.exe scripts/ai/verify_k2_runtime.py"
Write-Host "Full GPU and tool test: .venv/Scripts/python.exe scripts/ai/verify_k2_runtime.py --full --tool-test"
