"""Download a Q4_K_M K2-Horizon GGUF into A.D.A's project-local model folder."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "models" / "language" / "k2-horizon-7b" / "model.gguf"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="IFM/K2-Horizon-7B-GGUF", help="Hugging Face GGUF repository.")
    parser.add_argument("--quant", default="Q4_K_M", help="Quantization filename marker (default: Q4_K_M).")
    parser.add_argument("--force", action="store_true", help="Replace an existing project-local model file.")
    args = parser.parse_args()

    if DESTINATION.exists() and not args.force:
        print(f"Model already exists: {DESTINATION}")
        print("Use --force only if you intend to replace it.")
        return 0

    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError:
        print("Installing the Hugging Face download client...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "huggingface_hub>=0.26,<2"],
            check=False,
        )
        if result.returncode:
            return result.returncode
        from huggingface_hub import HfApi, hf_hub_download

    print(f"Inspecting {args.repo} for {args.quant} GGUF...")
    try:
        files = HfApi().list_repo_files(repo_id=args.repo, repo_type="model")
    except Exception as exc:
        print(f"Could not list repository files: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    marker = args.quant.casefold()
    candidates = [
        name for name in files
        if name.casefold().endswith(".gguf")
        and marker in Path(name).name.casefold()
        and "selective" not in Path(name).name.casefold()
    ]
    exact = [
        name for name in candidates
        if Path(name).name.casefold() == f"k2-horizon-7b-{marker}.gguf"
    ]
    if len(exact) == 1:
        selected = exact[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    elif not candidates:
        available = [name for name in files if name.casefold().endswith(".gguf")]
        print("No matching quantization found. Available GGUF files:")
        for name in available:
            print(f"  {name}")
        return 1
    else:
        print("Multiple matching GGUF files found; choose a repository or quantization with one unambiguous file:")
        for name in candidates:
            print(f"  {name}")
        return 1

    print(f"Downloading: {selected}")
    try:
        downloaded = Path(hf_hub_download(
            repo_id=args.repo,
            filename=selected,
            repo_type="model",
        ))
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        temporary = DESTINATION.with_suffix(".gguf.download")
        shutil.copy2(downloaded, temporary)
        temporary.replace(DESTINATION)
    except Exception as exc:
        print(f"Download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Installed project-local K2 model: {DESTINATION}")
    print(f"File size: {DESTINATION.stat().st_size:,} bytes")
    print("Next: python scripts/ai/verify_k2_runtime.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
