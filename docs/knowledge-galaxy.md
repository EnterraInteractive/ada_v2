# Knowledge Galaxy — Offline Implementation

The Knowledge Galaxy is part of A.D.A V2 and uses the same project-local backend and model runtime as the main assistant. It does not use a hosted LLM API.

## Notes and live captures

- Markdown notes are read recursively from `notes/` by default.
- Set `ADA_NOTES_DIR` to use another notes directory; the backend and viewer must use the same value.
- `POST /remember` writes a dated Markdown file into `notes/captures/`, indexes it immediately in the SQLite knowledge base, and returns its source information.
- The viewer refreshes the graph data after a successful capture; it does not require a manual reindex or page reload.

## Local model

Galaxy Q&A calls A.D.A's existing `LocalModelRuntime` in-process. The selected local model is configured in A.D.A Settings under `model_runtime.primary_model_id`. The model must be installed and loadable before asking note questions.

The retrieval layer ranks Markdown notes by keyword overlap and gives title matches extra weight. Up to six relevant notes are supplied to the local model. The model is instructed to answer only from those notes, treat note contents as untrusted reference material, and admit when the notes do not contain an answer. Short conversation history is retained per viewer session.

No Anthropic API key is required. The Galaxy does not create a cloud credential file. Do not add credentials to the viewer.

## Current speech integration

A.D.A already includes a project-local Whisper + Piper speech service in `backend/local_voice.py`, used by the main application through its Socket.IO audio pipeline. The standalone Galaxy viewer still has legacy browser speech code and is **not yet compliant** with the prompt pack's local Whisper hearing and VoiceStudio cloned-voice requirements. In particular, browser speech recognition must not be treated as offline hearing. This is an outstanding implementation item, not a completed feature.

## Viewer and network isolation

The standalone viewer is served by the root `server.py` on `127.0.0.1:4700`; the A.D.A backend listens on `127.0.0.1:8001`. The root server serves files only from `viewer/` and proxies its API requests to the local backend.

The current viewer still references its 3D graph library from a CDN. Therefore the viewer is **not yet verified to render with Wi-Fi disabled**. The offline release gate requires pinning and vendoring every browser dependency under `viewer/vendor/`, removing CDN references, and passing the network drill.

## Prompt-pack release gates still outstanding

1. Replace the viewer's CDN dependency with a pinned local vendor copy and record versions and source URLs.
2. Replace browser speech recognition with microphone capture, local Whisper transcription, wake-word handling, and push-to-talk.
3. Integrate VoiceStudio's local cloned-voice HTTP API, profile selection, WAV caching, warm-up, chunked playback, and explicit browser-voice fallback.
4. Add runtime brain selection and the visible BRAIN/VOICE status badge, preserving A.D.A's local runtime as the default.
5. Complete the outbound-connection and browser-resource network drill, including a Wi-Fi-off end-to-end test.
6. Verify the full capture flow, including title/date, immediate indexing, related-node placement, glow pulse, camera movement, and spoken success/failure confirmation.

A feature is not considered complete merely because its endpoint or UI exists. The release requires actual local runtime verification and a clean offline network drill.
