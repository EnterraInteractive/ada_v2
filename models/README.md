# A.D.A local models and voice providers

All local model files live under this directory. Paths in the registry are
relative to the A.D.A project root, not the process working directory.

## Local inference models

- `language/k2-horizon-7b/model.gguf` — primary chat, coding, reasoning, and tool-use model.
- `vision/gemma-4-12b/model.gguf` — vision model.
- `vision/gemma-4-12b/mmproj.gguf` — matching multimodal projector for Gemma 4.

The filenames above are the expected defaults. If a downloaded GGUF has a
different filename, either rename it to the expected name or update its path in
both `registry.json` and A.D.A's per-machine model settings.

Add future local models as entries in `registry.json`. Per-machine settings can
override a registry entry's paths and inference parameters.

## Voice: Gemini API

A.D.A voice is configured as an API provider, not as a local model. No Gemini
voice weights belong here and voice does not consume local GPU VRAM. Provider
metadata is kept in `voice/gemini/`; the API key must be supplied through the
`GEMINI_API_KEY` environment variable and must never be committed.

The Gemini API voice adapter is a separate integration from local model
inference. Until that adapter is enabled and configured, voice remains disabled
rather than silently falling back to local Whisper or operating-system TTS.

## Git behavior

Downloaded model weights and voice assets are excluded by `.gitignore`.
The registry, provider metadata, and these instructions remain versioned.
