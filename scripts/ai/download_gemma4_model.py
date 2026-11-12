"""Download the Gemma 4 GGUF and matching multimodal projector into Ada's model directory."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = ROOT / ".ada" / "cache"
HF_CACHE = CACHE_ROOT / "huggingface"
DESTINATION = ROOT / "models" / "vision" / "gemma-4-12b"
DEFAULT_REPO = "ggml-org/gemma-4-12B-it-GGUF"


def choose_model_file(files: list[str], explicit: str | None, quantization: str) -> str:
    if explicit:
        if explicit not in files:
            raise ValueError(f"Model file '{explicit}' was not found in the repository.")
        return explicit
    candidates = [
        name for name in files
        if name.lower().endswith(".gguf")
        and "mmproj" not in name.lower()
        and quantization.casefold() in name.casefold()
    ]
    if len(candidates) != 1:
        raise ValueError(
            "Could not select one model GGUF automatically. "
            f"Matching files: {candidates or '(none)'}. Pass --model-file with the exact repository filename."
        )
    return candidates[0]


def choose_mmproj_file(files: list[str], explicit: str | None) -> str:
    if explicit:
        if explicit not in files:
            raise ValueError(f"Projector file '{explicit}' was not found in the repository.")
        return explicit
    candidates = [
        name for name in files
        if name.lower().endswith(".gguf") and "mmproj" in name.lower()
    ]
    preferred = [name for name in candidates if "bf16" in name.lower() or "bfloat16" in name.lower()]
    if len(preferred) == 1:
        return preferred[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        "Could not select one multimodal projector automatically. "
        f"Matching files: {candidates or '(none)'}. Pass --mmproj-file with the exact repository filename."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Gemma 4 GGUF + mmproj into the Ada project.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Hugging Face model repository.")
    parser.add_argument("--quantization", default="Q4_K_M", help="Quantization token used to select the model file.")
    parser.add_argument("--model-file", help="Exact model GGUF filename (optional when one match exists).")
    parser.add_argument("--mmproj-file", help="Exact mmproj GGUF filename (optional when one match exists).")
    parser.add_argument("--force", action="store_true", help="Replace existing destination files.")
    args = parser.parse_args()

    # All Hugging Face and temporary download state stays inside the Ada folder.
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT / "downloads").mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT / "pip").mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT / "xdg").mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(HF_CACHE)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_CACHE / "hub")
    os.environ["PIP_CACHE_DIR"] = str(CACHE_ROOT / "pip")
    os.environ["XDG_CACHE_HOME"] = str(CACHE_ROOT / "xdg")
    os.environ["TEMP"] = str(CACHE_ROOT / "tmp")
    os.environ["TMP"] = str(CACHE_ROOT / "tmp")

    model_target = DESTINATION / "model.gguf"
    mmproj_target = DESTINATION / "mmproj.gguf"
    if model_target.is_file() and mmproj_target.is_file() and not args.force:
        print("Gemma 4 model and projector are already installed project-locally.")
        return 0

    from huggingface_hub import HfApi, hf_hub_download

    token = os.environ.get("HF_TOKEN") or None
    api = HfApi(token=token)
    print(f"Inspecting {args.repo}...")
    files = api.list_repo_files(repo_id=args.repo, repo_type="model")
    model_file = choose_model_file(files, args.model_file, args.quantization)
    mmproj_file = choose_mmproj_file(files, args.mmproj_file)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    targets = [
        (model_file, DESTINATION / "model.gguf"),
        (mmproj_file, DESTINATION / "mmproj.gguf"),
    ]
    for remote_name, target in targets:
        if target.exists() and target.stat().st_size > 0 and not args.force:
            print(f"Already present, keeping: {target}")
            continue
        print(f"Downloading {remote_name}...")
        download_root = CACHE_ROOT / "downloads" / "gemma4"
        download_root.mkdir(parents=True, exist_ok=True)
        downloaded = Path(hf_hub_download(
            repo_id=args.repo,
            filename=remote_name,
            repo_type="model",
            local_dir=str(download_root),
            token=token,
        ))
        temporary = target.with_suffix(target.suffix + ".download")
        downloaded.replace(temporary)
        temporary.replace(target)
        print(f"Saved {target} ({target.stat().st_size:,} bytes)")

    print("Gemma 4 model and projector are in the Ada project.")
    print("Expected paths:")
    print(f"  {DESTINATION / 'model.gguf'}")
    print(f"  {DESTINATION / 'mmproj.gguf'}")
    print("If the repository requires access approval, accept its terms on Hugging Face and set HF_TOKEN in your shell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
