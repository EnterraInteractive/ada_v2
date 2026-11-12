# A.D.A embedded inference runtime

A.D.A runs local models in-process through `llama-cpp-python`. It does not start
Ollama, llama-server, Docker, or another inference service.

## K2-Horizon compatibility

K2-Horizon GGUF requires llama.cpp release **b11454 or newer**. The ordinary
`llama-cpp-python 0.3.36` PyPI source package bundles an earlier llama.cpp
revision, so installing its standard wheel is not enough for K2.

A.D.A includes a reproducible Windows build path for the RTX 5070:

1. Activate A.D.A's Python 3.11 environment.
2. Install the normal app dependencies with `python -m pip install -r requirements.txt`.
3. Run `powershell -ExecutionPolicy Bypass -File scripts\\ai\\install_k2_runtime.ps1`.
4. Run `python scripts\\ai\\verify_k2_runtime.py`.
5. Run `python scripts\\ai\\verify_k2_runtime.py --full --tool-test` for an actual GPU generation and parsed function-call test.

The installer downloads the `llama-cpp-python 0.3.36` source distribution,
replaces its vendored llama.cpp source with upstream release `b11454`, and
builds the Python binding with CUDA for Blackwell consumer GPUs (`sm_120`).
It records the exact llama.cpp source commit and CUDA version in the ignored
local file `.ada/llama-cpp-build.json`.

## K2 model placement

Place the selected K2-Horizon 7B GGUF at:

`models/language/k2-horizon-7b/model.gguf`

Model weights are intentionally excluded from Git. Keep the GGUF inside this
project directory. Q4_K_M is a practical starting quantization for a 12 GB RTX
5070. A.D.A's existing 65,536-token context and system-RAM KV-cache placement
remain configurable; the installer does not silently reduce them.

## Build prerequisites

- Windows 10/11 x64
- Python 3.11 in the active A.D.A environment
- Git and CMake
- Visual Studio C++ build tools (MSVC)
- NVIDIA CUDA Toolkit 13.x and a current NVIDIA driver
- RTX 50-series GPU (the included build targets `sm_120`)

The installer stops if prerequisites are missing rather than silently falling
back to CPU or installing an incompatible prebuilt wheel.
