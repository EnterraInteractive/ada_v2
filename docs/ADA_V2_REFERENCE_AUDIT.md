# Ada V2 — Jarvis Reference Audit (Active Development Branch)

**Active implementation branch:** `feature/ada-development-assistant-strip`  
**Repository:** `EnterraInteractive/ada_v2`  
**Audit purpose:** Adapt the repository's JARVIS reference packs to the existing K2/Gemma Ada architecture without creating a second application.

## Decision

Ada remains one Electron + React + Python desktop application. The existing K2-Horizon embedded llama.cpp runtime and Gemma 4 vision delegate are retained. The PDF examples' Ollama server is not substituted for this runtime. Their useful capabilities are added around Ada's existing model runtime and assistant engine.

This branch is the active implementation baseline because it contains:
- `backend/assistant_engine.py`
- `backend/model_runtime.py`
- `scripts/ai/install_k2_runtime.ps1`
- `scripts/ai/download_k2_model.py`
- `scripts/ai/verify_k2_runtime.py`
- `models/registry.json` with K2-Horizon 7B and Gemma 4 12B
- `backend/gemini_voice.py`, which routes speech requests into the local assistant

The four source PDFs were restored under `docs/` on this branch so the implementation and its reference material travel together.

## Reference documents

1. `docs/JARVIS-Prompt-Pack.pdf`
2. `docs/Build-Jarvis-Fully-Offline-Prompt-Pack.pdf`
3. `docs/Run-Jarvis-Fully-Local-Prompt-Pack.pdf`
4. `docs/Build-Your-Own-Jarvis-Opus-5.5-Prompt-Pack.pdf`

The first three documents' text was available for review. The Opus 5.5 PDF is present in the repository, but its text was not exposed by the document extraction path used in this pass. Its content is deliberately not represented as reviewed. It must be extracted and reviewed before its unique instructions are used.

## Requirements extracted from the readable PDFs

### A. Knowledge memory and source navigation
- Recursively index Markdown notes and documents.
- Give every source a stable ID; store title, group/folder, excerpt, and links.
- Link notes through title references and explicit wikilinks.
- Display a navigable knowledge graph in the existing application.
- Clicking a source should show its excerpt and related sources.
- Answer knowledge questions from retrieved sources, returning the source IDs used.
- Say plainly when indexed material does not support an answer.
- Keep ordinary conversation separate from source navigation.
- Support natural-language capture such as “remember that …”.
- A successful capture is a durable file, indexed immediately, and retrievable on the next turn.

### B. Model management
- Keep local inference as the normal/default mode.
- Use a provider-neutral contract so more models and runtimes can be registered.
- Support switching between registered models and show the active model.
- Keep model IDs, paths, versions, and tuning in configuration.
- Keep the system prompt stable and place changing retrieved content after it.
- A cloud model is optional and explicitly selected; local mode must not need a cloud key.

The PDFs use Ollama's OpenAI-compatible endpoint as an example. Ada already uses an embedded llama.cpp runtime, so Ollama is not a requirement. Keep K2-Horizon as the default primary assistant and Gemma 4 as a vision delegate that can also be selected as the primary chat model. Keep model roles and selectable models extensible.

### C. Speech
- Local speech-to-text using Whisper on Windows/Linux via faster-whisper.
- A lightweight wake-word stage before full transcription.
- Interrupt/barge-in while Ada is speaking.
- Local TTS as a separate provider with a pinned engine/model/profile.
- Sentence-aware speech chunks with the next chunk prefetched during playback.
- Explicit fallback state when local TTS is unavailable.
- A single mute/stop policy applied to all playback routes.

The Windows route in the offline PDF names VoiceStudio with VoxCPM2. The Apple-only MLX audio setup in the fully-local PDF is not applicable to this Windows system. Ada's existing Gemini Live voice should be preserved as an optional voice provider while a local path is added; do not break the currently working voice path.

### D. Reliability and privacy proof
- End-to-end preflight of the live running system, not only mocks or unit tests.
- Measure STT, inference, first-audio, and full-turn latency.
- Verify the configured model is available and returns non-empty output.
- Verify TTS produces a real audio file/stream.
- Verify an STT/TTS round trip.
- Verify memory write and immediate retrieval.
- Verify mute and interruption.
- Audit outbound connections and make local-only mode fail if a non-loopback connection is made.
- Remove CDN dependencies from the app's offline path or vendor exact pinned assets.
- Report actual results; never claim an action succeeded without tool evidence.

### E. Capabilities shown as the more advanced JARVIS target
The original prompt pack distinguishes its starter note assistant from the more developed JARVIS shown in videos. The latter is described as having a voice-reactive HUD, wake word/barge-in, Gmail and Calendar briefings, live web research, an agent inbox, confirmation-gated drafting, screen vision/computer control, history recall, model hot-swap, and personality controls. Treat these as capability ideas, not as features proven to exist in the starter implementation. Add only the integrations that are useful to Ada and that can be safely supported.

## Existing branch capabilities

| Area | Current implementation | Assessment |
|---|---|---|
| Primary local model | K2-Horizon 7B GGUF through in-process llama-cpp-python | Keep |
| Vision model | Gemma 4 12B GGUF + mmproj, loaded on demand | Keep; extend role registry if user wants it selectable for text chat too |
| Model registry | Project-local `models/registry.json` plus per-machine settings | Good base for future models |
| K2 runtime build | Pinned llama-cpp-python 0.3.36 + llama.cpp b11454 + CUDA sm_120 build script | Keep; installation paths need review |
| Assistant orchestration | Local K2 chat, tool calling, native K2 tool-call parser | Keep and extend |
| Tools | Workspace file operations, terminal commands, browser, projects, image delegation, Unreal MCP | Keep; centralize safety/permissions |
| Voice | Gemini Live API voice delegates requests to local K2 | Preserve as optional provider; add local STT/TTS for offline mode |
| Project memory | JSONL chat history and manual memory save/load | Useful but not semantic retrieval |
| Knowledge index | No Markdown/RAG index or graph in inspected branch | Missing |
| Wake word / local STT | Not present in inspected requirements or source tree | Missing |
| Local TTS | Not present; current voice provider is remote Gemini Live | Missing |
| Offline proof | K2 local inference is supported, but voice/browser/network paths are not fully proven offline | Missing |
| Preflight | K2 runtime verifier exists; whole-assistant live-chain preflight does not | Partial |
| Portable install | K2 build/model data are project-relative; Python environment and some caches may still be external | Needs correction |

## Gaps and risks to address

1. **No knowledge retrieval layer.** `ProjectManager.get_project_context()` builds a bounded workspace context and `search_project()` searches source files, but this is not a durable, source-attributed Markdown knowledge index or graph.
2. **No immediate capture-to-retrieval pipeline.** Manual memory save/load exists, but there is no single capture path that writes a note, updates the index, and makes it retrievable on the next question.
3. **No local hearing or local speech output.** The current voice service is Gemini Live API; it forwards spoken requests to K2 but depends on a remote API and `GEMINI_API_KEY`.
4. **Model roles are fixed in the current UI/config.** The runtime registry is extensible, but the user-facing experience is primarily K2 chat plus Gemma vision delegation, not a general model switcher.
5. **Local installation is not fully self-contained yet.** The README describes a Conda environment; the runtime installer expects the active Python 3.11 interpreter. Python packages, pip caches, Hugging Face caches, and Playwright browser storage must be explicitly rooted inside the Ada folder if the user's no-C-drive requirement is to be met.
6. **Electron process launch still uses `spawn('python', ...)`.** It does not explicitly launch the project's own `.venv` interpreter. This must be changed as part of the portable install work.
7. **Desktop security hardening remains.** The current Electron window enables Node integration and disables context isolation. This should be addressed without breaking the current UI.
8. **Local-only is not the same as all features offline.** Browser automation and the optional Gemini voice provider need network access. Ada must expose a clear local/offline mode and an honest list of network-dependent features.

## Target architecture for this branch

### 1. Keep the current core
- Electron + React UI.
- FastAPI + Socket.IO backend.
- K2-Horizon local reasoning, coding, and tool calls.
- Gemma 4 vision delegation.
- Existing Unreal MCP, workspace tools, browser, and project history.
- Existing Gemini Live voice as an optional provider until local voice has parity.

### 2. Add a unified provider/model control plane
- Keep `LocalModelRuntime` as the in-process GGUF engine.
- Make model roles and user-selectable chat models registry-driven.
- Permit future GGUF models without code changes where the chat format is compatible.
- Keep vision delegation as a distinct capability so the main model can request image analysis.
- Surface active model, role, load state, and failure reason in the UI.
- Keep cloud voice/model providers explicit and separate from local inference.

### 3. Add one durable knowledge service
- Source folders are explicitly configured and read-only by default.
- Captures are written as Markdown into Ada-managed memory.
- Index title, body, path, group, and source metadata.
- Add incremental re-indexing and immediate index updates after capture.
- Retrieval returns excerpts plus stable source IDs.
- Add a graph view in the existing React interface backed by the same index.
- The graph is a visualization, not a second source of truth.

### 4. Add local speech providers
- Local STT provider: faster-whisper on Windows.
- Wake-word detection remains lightweight and separate from full transcription.
- Local TTS provider: configurable VoiceStudio VoxCPM2 endpoint, if selected by the user.
- Retain Gemini Live as an optional remote voice provider.
- Centralize playback, interrupt, mute, and provider status.

### 5. Make installation portable
- Create and use `.venv/` inside the project root.
- Electron launches `.venv/Scripts/python.exe` on Windows (and the equivalent on other platforms).
- Root pip, Hugging Face, Playwright, model, runtime-build, voice-cache, log, and memory caches under project-local folders.
- Use project-relative paths everywhere.
- Distinguish required OS-level prerequisites (GPU driver/toolchain) from project-local Python packages, model weights, and browser runtimes.
- Do not silently write model weights or package caches to the user's Windows profile or C: drive.

### 6. Add live-chain preflight and offline drill
- Backend health and frontend availability.
- K2 load, response, and tool-call check.
- Gemma image-delegation check.
- Voice-provider health and STT/TTS round-trip where local voice is enabled.
- Capture and immediate retrieval check.
- Tool confirmation/denial check.
- Mute and barge-in checks.
- Network connection inventory in local-only mode.
- Per-stage and total latency report.

## Implementation sequence

1. Reconcile this branch with the user's current local `ada_v2` working tree before touching files. Preserve the existing K2/Gemma runtime scripts and any local changes.
2. Make the project-local Python environment, cache, browser, model, and runtime paths deterministic; update Electron to launch the local interpreter.
3. Complete the model registry/user-facing model selection without changing the current K2/Gemma roles by default.
4. Add durable Markdown memory, indexing, retrieval, and immediate capture indexing.
5. Add the knowledge graph view to the existing UI.
6. Add optional local STT/TTS, wake-word, interrupt, and unified mute control without removing Gemini voice.
7. Add the full preflight and local-only network drill.
8. Only then consider optional integrations from the advanced JARVIS feature list.

## Constraints

- No separate JARVIS application.
- Do not replace embedded llama.cpp with Ollama just because the PDFs use it.
- Do not remove K2-Horizon, Gemma 4, Unreal MCP, or existing development tools.
- Do not break the working Gemini voice path while adding local voice.
- Do not use Apple's MLX audio engine on Windows.
- Do not claim offline operation until the connection drill passes.
- Do not claim the Opus 5.5 PDF was reviewed until its text is extracted.
- Preserve user-local files, model weights, settings, and uncommitted changes.


## Implementation progress on this branch

The following work has now been committed to `feature/ada-development-assistant-strip`:

- Restored all four reference PDFs under `docs/` on the active K2/Gemma branch.
- Added this audit and implementation direction document.
- Added `scripts/setup_local.ps1`: uses uv-managed Python 3.11 under `.ada/python`, creates `.venv`, installs Python packages there, downloads portable Node.js 24.20.0 under `.ada/tools`, and routes pip, Hugging Face, npm, temporary, Playwright, and browser data into `.ada/`.
- Added `scripts/run_ada.ps1`; Electron now requires the project-local `.venv` instead of silently launching a global Python interpreter.
- Routed backend caches and Playwright browser storage into the project-local `.ada/` directories, including manual backend launches.
- Copied MediaPipe WASM assets from the installed package into the Vite public assets during setup, replaced remote noise textures with a local SVG, and removed the Google Fonts CDN import.
- Added `backend/knowledge_base.py`: local SQLite FTS index for Markdown, text, and PDF sources; stable numeric source IDs; wikilink/title-reference graph edges; durable Markdown captures; and immediate indexing after “remember that …”.
- Added bounded full-source reading by ID, both as an assistant tool and in the Knowledge Galaxy panel, so Ada can read complete PDF/reference contents in chunks instead of relying only on excerpts.
- Added `scripts/ai/download_gemma4_model.py` to place the Gemma 4 GGUF and matching projector in the project-local model directory with its Hugging Face cache contained in `.ada/`.
- Added SHA-256 verification for the portable Node.js archive before extraction.

- Connected knowledge retrieval and explicit memory capture to the assistant engine, and exposed local graph/search/reindex/capture API routes.
- Added the Knowledge Galaxy window to the existing Ada UI, including graph rotation/zoom, search, reindex, and source excerpt/path inspection.
- Exposed Gemma 4 as both a chat-capable and vision-capable model in the registry. K2 remains the default primary model.

### Not yet verified or implemented

- These commits have **not** been run on the user's machine. Do not treat setup, build, model load, PDF extraction, or the knowledge graph as runtime-verified yet.
- The Opus 5.5 PDF is present in `docs/`, and the new local indexer can extract PDFs with `pypdf`, but its contents were not available through the repository connector during this audit. Do not claim its unique recommendations have been reviewed.
- Local Whisper STT, local TTS, wake word, barge-in, and one unified playback/mute controller are not implemented yet. Preserve the existing Gemini Live voice path until local voice is ready.
- A full end-to-end preflight, outbound-connection audit, and strict local-only network drill remain outstanding.
- Advanced integrations such as Gmail/Calendar and an agent inbox remain ideas, not implemented features.

The next implementation work is local speech providers and full-chain preflight/offline verification. Before running setup or making further changes, reconcile this branch with the user's current local `ada_v2` working tree and preserve its existing model files and settings.
