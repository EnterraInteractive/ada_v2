"""Download local Whisper and Piper speech models into the A.D.A project."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".ada" / "cache" / "huggingface"
WHISPER_DEST = ROOT / "models" / "voice" / "whisper-small"
PIPER_DEST = ROOT / "models" / "voice" / "piper"
WHISPER_REPO = "Systran/faster-whisper-small"
PIPER_REPO = "rhasspy/piper-voices"
PIPER_FILES = (
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace existing model files.")
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    PIPER_DEST.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(CACHE)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE / "hub")
    os.environ["PIP_CACHE_DIR"] = str(ROOT / ".ada" / "cache" / "pip")
    os.environ["TEMP"] = str(ROOT / ".ada" / "cache" / "tmp")
    os.environ["TMP"] = os.environ["TEMP"]

    if WHISPER_DEST.exists() and any(WHISPER_DEST.iterdir()) and not args.force:
        print(f"Keeping existing Whisper model: {WHISPER_DEST}")
    else:
        WHISPER_DEST.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {WHISPER_REPO} into {WHISPER_DEST}")
        snapshot_download(
            repo_id=WHISPER_REPO,
            repo_type="model",
            local_dir=str(WHISPER_DEST),
            token=os.environ.get("HF_TOKEN") or None,
            force_download=args.force,
        )

    for filename in PIPER_FILES:
        target = PIPER_DEST / Path(filename).name
        if target.is_file() and target.stat().st_size > 0 and not args.force:
            print(f"Keeping existing Piper file: {target}")
            continue
        print(f"Downloading {filename}")
        downloaded = Path(hf_hub_download(
            repo_id=PIPER_REPO,
            filename=filename,
            repo_type="model",
            cache_dir=str(CACHE),
            token=os.environ.get("HF_TOKEN") or None,
            force_download=args.force,
        ))
        temporary = target.with_suffix(target.suffix + ".download")
        temporary.write_bytes(downloaded.read_bytes())
        temporary.replace(target)

    expected = [
        WHISPER_DEST / "model.bin",
        PIPER_DEST / "en_US-lessac-medium.onnx",
        PIPER_DEST / "en_US-lessac-medium.onnx.json",
    ]
    missing = [str(path) for path in expected if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError("Speech model download incomplete: " + ", ".join(missing))
    print("PASS: local Whisper and Piper model files are present under the A.D.A project.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
