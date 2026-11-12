# Knowledge Galaxy — Offline Jarvis

The Galaxy is a local A.D.A V2 interface. Its default brain, notes, hearing, speech, memory, and graph are hosted by the project-local Ada backend. The viewer does not require a hosted LLM or browser speech-recognition service.

## Notes and live memory

- Markdown notes are read recursively from `notes/` by default. Set `ADA_NOTES_DIR` to use another notes directory; the backend and viewer must use the same value.
- Typed or transcribed text beginning with `remember that` is sent to `POST /remember`.
- The backend writes a dated Markdown file under `notes/captures/`, immediately indexes it in the local SQLite knowledge base, rebuilds the graph, and returns the new node and its best related anchor.
- The viewer's `addNote()` updates the running graph without a reload, places the new node at the anchor's coordinates, pulses it, opens its source panel, and flies the camera to it.
- The new capture is searchable by the very next `/chat` request. Failed writes or indexing return an error instead of a success receipt.
- `build.py` remains the canonical Markdown graph builder used by the standalone viewer server.

## Local brain

Galaxy Q&A calls Ada's existing in-process `LocalModelRuntime`; no hosted LLM API is used. The default local profile is K2-Horizon 7B and the configured big profile is Gemma 4 12B. The profiles are runtime-switchable:

- "switch to your local brain"
- "switch to your big brain"
- "which brain are you on"
- "switch to model MODEL_ID" for any registered local chat model

A model must exist in `models/registry.json` or the settings model list, and its model file must be present under the project. Switching is runtime-only; the configured boot brain remains the restart default. Claude is deliberately disabled in this offline build.

Retrieval ranks Markdown notes by keyword overlap and weights title matches more highly. Up to six relevant notes are supplied to the local model. The stable butler system prompt instructs it to answer only from those notes, treat note contents as untrusted reference material, and admit when the notes do not contain an answer. Short session history is retained.

## Local hearing

The standalone viewer uses `getUserMedia`, resamples the microphone to mono 16-bit 16 kHz WAV, and posts it to `/hear`; it does not use Web Speech Recognition or a hosted transcription API. `/speak` returns raw `audio/wav` and an `X-Jarvis-Voice` header.

- Push-to-talk sends the captured utterance directly to the large local Whisper command model.
- Hands-free mode uses the small local Whisper model to detect "Jarvis" / "Hey Jarvis". Utterances without the wake word are discarded. A wake word without a command prompts "Yes, sir?" and treats the next utterance as the command.
- The browser measures audio energy, ends an utterance after 700 ms of silence, and applies a 900 ms finish window for mid-sentence pauses. Speech under 300 ms is ignored.
- While Ada is speaking, the listener raises its threshold and only accepts "stop" or "wait" as interruption commands.
- Whisper models are stored under `models/voice/whisper-small` and `models/voice/whisper-large-v3-turbo`. Download both with `scripts/ai/download_local_voice_models.py`.

The main Ada voice service uses the large Whisper model for command transcription. Whisper falls back to CPU if CUDA loading fails.

## Local cloned voice

- VoiceStudio is configured at `http://127.0.0.1:3900`, with the Windows VoxCPM2 engine and a profile named `Jarvis`.
- The adapter selects the configured TTS engine, looks up the profile by name, calls the local OpenAI-compatible speech endpoint, caches WAVs by text and profile under `.ada/cache/voice/`, and warms the engine with "Standing by." at startup/after idle intervals.
- Answers are split into sentence-packed chunks of about 170 characters. The next chunk is fetched while the current chunk plays; sentences are never split to chase first-audio latency.
- If VoiceStudio is unavailable, Ada uses the project-local Piper voice. If both local engines fail, the viewer can use only a browser speech voice marked `localService`; it never selects a network voice. Voice commands can switch among the cloned profile, Piper, and local browser voice, or select another VoiceStudio profile by name.
- `?mute=1` prevents every playback path in the viewer while leaving local hearing available.

VoiceStudio's app is installed under `.ada/tools/VoiceStudio` by `scripts/ai/install_voicestudio.ps1`. Its Python environment, model weights, profiles, and data are directed to `.ada/voicestudio-data/` by `scripts/run_voicestudio.ps1`. The first VoiceStudio launch still requires installing its local runtime, selecting VoxCPM2, and creating a Jarvis profile from a voice recording you have permission to use.

## Viewer and offline browser assets

The standalone viewer is served by root `server.py` on `127.0.0.1:4700`; Ada's backend listens on `127.0.0.1:8001`.

The 3D graph library is pinned to `3d-force-graph@1.73.3`. `npm ci` runs `scripts/stage_galaxy_vendor.mjs`, which downloads the pinned file once into `viewer/vendor/`, verifies its content, records its SHA-256 and source URL in `viewer/vendor/VERSIONS.txt`, and the viewer loads only that local copy. The browser has no CDN reference in `viewer/index.html`.

## One-command project-local setup

Run `scripts/setup_local.ps1` from the repository root on the target Windows machine. By default it installs the project-local Python environment and packages, downloads K2-Horizon and Gemma 4 GGUF/projector files, builds the pinned CUDA llama.cpp runtime, downloads both Whisper models and Piper, stages the pinned graph vendor, installs the local browser runtime, and installs the VoiceStudio app under `.ada/`. The models live under `models/`; application runtimes, downloads, caches, and VoiceStudio data live under `.ada/`; the Python virtual environment and Node dependencies remain inside the repository. CUDA Toolkit 13.x, NVIDIA drivers, Git, CMake, and uv are machine-level prerequisites.

VoiceStudio's first launch remains a one-time interactive step: run `scripts/run_voicestudio.ps1`, install its local runtime into the project-local data directory, select VoxCPM2, and create the Jarvis voice profile using a recording you have permission to clone. The local Piper voice remains available if that step is skipped.

## Offline network drill

The backend instruments socket connections and records the host, port, and calling code location to `.ada/network-audit.jsonl`. The viewer reports browser Resource Timing hosts after each turn.

After setup and the one-time VoiceStudio profile creation, launch the whole local stack with `scripts/run_offline_jarvis.ps1`. It starts VoiceStudio, A.D.A, and the Knowledge Galaxy viewer in separate local windows. To run the verification drill, keep those services running and execute:

```powershell
.venv\Scripts\python.exe scripts\ai\drill_offline.py
```

The drill performs a real local `/chat`, synthesizes the answer through `/speak`, feeds that audio through `/hear`, opens the viewer in a muted Playwright tab, captures browser resource hosts, prints server connection reasons, and lists external URLs found in setup and optional integration code. Any non-loopback server connection or missing speech transcript fails the drill.

## Release verification still required

The implementation is in place, but it is not labelled verified until the current branch's CI run passes and the end-to-end drill has been run with the actual local models and VoiceStudio runtime. A final Wi-Fi-disabled run on the target Windows machine is also required; source inspection alone is not proof that every installed runtime behaves offline.
