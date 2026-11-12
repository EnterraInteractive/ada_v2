"""Verify A.D.A's embedded llama.cpp runtime against the K2-Horizon GGUF."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "language" / "k2-horizon-7b" / "model.gguf"
BUILD_RECORD = ROOT / ".ada" / "llama-cpp-build.json"


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Load K2 on the GPU and generate a short answer.")
    parser.add_argument("--tool-test", action="store_true", help="Also test parsed native function calling (implies --full).")
    args = parser.parse_args()

    print("A.D.A K2-Horizon runtime verification")
    print(f"Project root: {ROOT}")
    print(f"Model file:   {MODEL}")
    if not MODEL.is_file():
        return fail(f"K2 GGUF is missing. Expected: {MODEL}")

    if not BUILD_RECORD.is_file():
        print("WARNING: no local build record. The active package may be an unpatched PyPI wheel.")

    try:
        package_version = importlib.metadata.version("llama-cpp-python")
        import llama_cpp
        from llama_cpp import Llama
    except Exception as exc:
        return fail(f"llama-cpp-python import failed: {type(exc).__name__}: {exc}")

    print(f"llama-cpp-python: {package_version}")
    gpu_supported = bool(llama_cpp.llama_supports_gpu_offload())
    print(f"GPU offload:      {gpu_supported}")
    print(f"Backend info:     {llama_cpp.llama_print_system_info()}")

    if BUILD_RECORD.is_file():
        try:
            build = json.loads(BUILD_RECORD.read_text(encoding="utf-8-sig"))
            print(f"llama.cpp release: {build.get('llama_cpp_release')}")
            print(f"llama.cpp commit:  {build.get('llama_cpp_commit')}")
            print(f"CUDA target:       {build.get('cuda_architecture')}")
            if build.get("llama_cpp_release") != "b11454":
                print("WARNING: recorded source is not the pinned K2 baseline.")
        except (OSError, ValueError) as exc:
            print(f"WARNING: cannot read local build record: {exc}")

    if not gpu_supported:
        return fail("The installed binding has no GPU offload. Run scripts\\ai\\install_k2_runtime.ps1.")

    print("Probing GGUF architecture and tokenizer without loading model weights...")
    try:
        probe = Llama(model_path=str(MODEL), vocab_only=True, n_ctx=512, n_gpu_layers=0, verbose=False)
        vocab_size = probe.n_vocab()
        probe.close()
    except Exception as exc:
        return fail(
            "The native backend cannot open the K2 GGUF. The K2-Horizon architecture patch may be missing, "
            "or the model file may be damaged. "
            f"Native error: {type(exc).__name__}: {exc}"
        )

    print(f"GGUF architecture/tokenizer: OK (vocabulary size {vocab_size})")
    if not args.full and not args.tool_test:
        print("PASS: K2 architecture is recognized. Use --full to verify GPU generation.")
        return 0

    print("Loading K2 on the GPU for a short generation test...")
    model = None
    try:
        model = Llama(
            model_path=str(MODEL),
            n_ctx=4096,
            n_batch=256,
            n_gpu_layers=99,
            flash_attn=True,
            offload_kqv=False,
            type_k=getattr(llama_cpp, "GGML_TYPE_Q8_0"),
            type_v=getattr(llama_cpp, "GGML_TYPE_Q8_0"),
            verbose=False,
        )
        if args.tool_test:
            tools = [{
                "type": "function",
                "function": {
                    "name": "ada_runtime_probe",
                    "description": "A harmless local runtime verification function.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }]
            result = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": "You are testing tool calling. When asked to verify the local runtime, call the available ada_runtime_probe function."},
                    {"role": "user", "content": "Verify the local runtime now. Call ada_runtime_probe."},
                ],
                tools=tools,
                tool_choice="auto",
                temperature=1.0,
                top_p=0.95,
                max_tokens=256,
            )
            message = result["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                # The Python wrapper may return K2's native JSON/XML tool envelope
                # as text; verify the exact parser used by A.D.A as well.
                sys.path.insert(0, str(ROOT / "backend"))
                from assistant_engine import AssistantEngine
                parsed, visible = AssistantEngine._parse_native_tool_calls(
                    message.get("content") or message.get("reasoning_content") or ""
                )
                calls = parsed
                if not calls:
                    return fail(
                        "GPU generation worked, but neither the binding nor A.D.A's "
                        f"K2 envelope parser recognized a function call. Message: {message}"
                    )
            print(f"Parsed function call: {calls[0].get('function', {}).get('name')}")
        else:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": "Reply with exactly: K2 runtime is working."}],
                temperature=1.0,
                top_p=0.95,
                max_tokens=64,
            )
            answer = result["choices"][0]["message"].get("content", "")
            print(f"Generated response: {answer}")
            if not answer:
                return fail("K2 loaded but returned no visible answer.")
    except Exception as exc:
        return fail(f"Full GPU inference failed: {type(exc).__name__}: {exc}")
    finally:
        if model is not None:
            model.close()

    print("PASS: K2 loaded and generated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
