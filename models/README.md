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

A.D.A voice uses Gemini Live API for speech input/output. Microphone PCM is
streamed to Gemini and Gemini's generated audio is streamed back. No local
speech model is loaded and no voice weights belong here.

Gemini is the speech interface, not the primary reasoning engine. Every spoken
request is routed through the `ask_ada_local` function to A.D.A's local
K2-Horizon assistant, which retains the normal reasoning, coding, and Unreal
project-tool responsibilities. Gemini speaks the local assistant's response.

Copy `.env.example` to `.env` in the project root and set
`GEMINI_API_KEY`. The API key must never be committed. The selected Live API
model defaults to `gemini-3.8-live` and can be overridden with
`GEMINI_LIVE_MODEL`.

## Git behavior

Downloaded model weights and voice assets are excluded by `.gitignore`.
The registry, provider metadata, and these instructions remain versioned.
