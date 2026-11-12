# Ada V2 — Reference Audit and Restructuring Direction

**Repository inspected:** `EnterraInteractive/ada_v2`  
**Branch inspected:** `main`  
**Scope:** Existing application, the three reference PDFs whose text is available, and the fourth PDF's presence in the repository.

## Executive decision

Do not replace Ada V2 with a separate JARVIS application. Evolve the current Electron + React + Python application into one local-first assistant. Keep the existing CAD, browser, printer, Kasa, camera, project, and desktop UI capabilities where they are useful. Replace the Gemini-only conversation path with a provider-neutral conversation layer that can use the user's K2 and Gemma 4 runtimes, while retaining Gemini as an optional provider only if desired.

This is a selective re-engineering, not a clean-room rewrite.

## Reference material found in the repository

All four PDFs are present under `docs/`:

1. `JARVIS-Prompt-Pack.pdf`
2. `Build-Jarvis-Fully-Offline-Prompt-Pack.pdf`
3. `Run-Jarvis-Fully-Local-Prompt-Pack.pdf`
4. `Build-Your-Own-Jarvis-Opus-5.5-Prompt-Pack.pdf`

The first three PDFs were text-indexed and reviewed. The Opus 5.5 PDF is present in the Git tree, but its contents were not returned by the available document-text extraction path in this audit. Its content is therefore **not** represented as reviewed here; do not infer its contents from its filename. Revisit it when an extractable copy is available.

### Requirements drawn from the reviewed PDFs

#### 1. Knowledge system / “galaxy”
- Index Markdown notes recursively.
- Give every indexed note a stable numeric index/ID.
- Store title, folder/group, and a useful text excerpt.
- Connect notes using title mentions and explicit wikilinks.
- Present a navigable visual knowledge map; selecting a node reveals its source excerpt and related nodes.
- Answer questions from retrieved notes, return the source node IDs used, and distinguish unsupported answers from facts found in notes.
- Small talk should not move the knowledge-map camera; source navigation is for knowledge questions.
- Add new notes by natural language commands such as “remember that …”.
- A successful capture must be written to disk, indexed immediately, and retrievable on the next question—not merely added to the current prompt.

#### 2. Local model / provider system
- Use a local inference server with an OpenAI-compatible chat interface where possible.
- Keep the provider endpoint, model identifier, and provider-specific request options in configuration.
- Support more than one model and switch models at runtime; show which model is active.
- Pin model/runtime versions rather than silently following “latest”.
- Keep the stable system/persona prompt before changing per-turn content to improve prompt-cache reuse.
- Keep a cloud provider optional and explicit. The fully-local mode must not depend on a cloud key.

The PDF examples use Ollama. That is a reference implementation, not a requirement to force Ada onto Ollama. Ada must integrate with the K2 and Gemma 4 runtimes already selected for this project. The local provider adapter should be configurable so additional compatible runtimes/models can be added later.

#### 3. Voice and hearing
- Local speech recognition using Whisper; the Windows path in the offline pack is `faster-whisper`, with NVIDIA acceleration when supported.
- Wake-word detection should be a separate, lightweight listening stage; full transcription should run only after wake.
- Support interrupt/barge-in so the user can stop Ada while she is speaking.
- Local TTS should be an independently configured engine, with voice/profile and model explicitly pinned.
- Chunk long speech at sentence boundaries and prefetch the next chunk while the current chunk plays; do not create unnatural mid-sentence pauses just to reduce first-audio latency.
- If local TTS is unavailable, use a clearly identified fallback rather than silently failing.
- Provide a mute control that applies to every playback route, including background/test sessions.

The offline pack documents VoiceStudio's Windows VoxCPM2 route. The Apple-only MLX audio configuration in the other pack is not suitable for this Windows machine.

#### 4. Proof, privacy, and reliability
- Build a live-chain preflight, not only unit tests.
- Measure hearing, inference, and speech latency separately and report total turn latency.
- Verify chat, TTS, STT round-trip, memory capture/retrieval, and the model actually configured.
- Audit outbound connections and make local-only mode fail if non-loopback network access occurs.
- Vendor frontend libraries that would otherwise load from a CDN when strict offline operation is required.
- Never claim an action completed until the tool returns a successful result.
- Keep confirmation gates for consequential actions.

#### 5. Broader “finished JARVIS” ideas
The original prompt pack distinguishes the starter knowledge assistant from the more developed JARVIS shown in videos. The latter is described as adding a voice-reactive HUD, wake word and true barge-in, Gmail/Calendar briefings, live web research, an agent inbox, confirmation-gated drafting, screen vision/computer control, history recall, model hot-swap, and personality controls. These are aspirational capability references, not proof that the starter prompt pack implements them. For Ada, extend its existing agents and integrations rather than copy claims that are not present in code.

## Existing Ada V2 baseline observed on `main`

### Current structure
- Desktop shell: Electron 28.
- UI: React 18 + Vite.
- Backend: Python, FastAPI, Socket.IO, Uvicorn.
- Current conversation/audio engine: Google Gemini Live API, configured directly in `backend/ada.py`.
- Existing agents: CAD, Playwright browser, Kasa smart home, printer workflows, face authentication, project manager.
- Existing UI components include chat, visualizer/audio bar, CAD, browser, printer, Kasa, and settings windows.

### Important gaps versus the references
- `backend/ada.py` creates a Google GenAI client at module import and hardcodes a Gemini Live model. There is no provider-neutral model interface in the inspected tree.
- `backend/web_agent.py` also requires `GEMINI_API_KEY` at import time. That prevents a clean no-key local-only startup even if the main conversation path is later made local.
- The current voice path is Gemini Live audio with a prebuilt voice. The inspected dependencies do not include local Whisper STT or a local TTS engine.
- Project history is JSONL and project files are concatenated into context; there is no Markdown knowledge index, source-grounded retrieval response, or interactive knowledge graph in the inspected UI.
- The current memory upload sends text into the active Gemini session; it is not a persistent searchable knowledge base.
- The `save_memory` handler in `backend/server.py` iterates over messages but, in the inspected implementation, does not write the message content to the opened file. This needs correction before treating it as reliable long-term memory.
- `backend/project_manager.py` clears the `projects/temp` directory on initialization. That behavior must be reviewed and made non-destructive before expanding persistent memory.
- `electron/main.js` starts the backend using the system `python` from PATH rather than an explicitly selected project-local interpreter. That conflicts with the requirement that the runtime be contained in the `ada_v2` directory.
- The Electron window currently enables Node integration and disables context isolation. This should be hardened as part of the desktop integration work.
- The current `.env.example` and README describe Gemini API-key setup as mandatory, and the README explicitly says the current application requires internet for Gemini. That is incompatible with local-first operation.
- Dependency versions in `requirements.txt` are mostly unpinned. The reference packs repeatedly stress pinning versions.

### Safety finding requiring priority
In `backend/web_agent.py`, a browser-computer-use safety decision with `require_confirmation` is logged and then auto-acknowledged to proceed. That reverses the confirmation-gate behavior described in the JARVIS references and is not acceptable for a broader computer-control assistant. This must be changed so the user explicitly approves the action before it proceeds.

## Target Ada architecture

Keep one app and one backend. Introduce clear internal boundaries:

1. **Model provider registry**
   - Provider contract for chat, streaming, tool calls, model listing, health, and capability reporting.
   - K2 and Gemma 4 configured as selectable local models.
   - Provider/model selection stored in Ada configuration and surfaced in the UI.
   - Optional cloud providers disabled unless explicitly configured and selected.
   - A single orchestration layer owns conversation history, prompt construction, tool dispatch, and result verification.

2. **Conversation and action orchestration**
   - One conversation pipeline for typed and spoken requests.
   - Tool definitions independent of any single model vendor's schema.
   - Central permission checks and confirmation requests.
   - Tool results returned to the model and user; action status must be evidence-based.

3. **Audio subsystem**
   - Capture and device selection.
   - Wake-word gate.
   - Local STT.
   - Conversation handoff.
   - Interruptible playback.
   - Local TTS adapter with cache, sentence-aware chunking, and fallback status.
   - One central mute/stop policy.

4. **Knowledge and memory**
   - Durable Markdown captures and imported documents.
   - Incremental index so new captures become searchable immediately.
   - Retrieval returns source IDs and excerpts.
   - Searchable project/chat history.
   - Graph data generated from the same index; the graph is a view of the knowledge base, not a second source of truth.

5. **Existing capability agents**
   - Preserve CAD, browser, printer, smart-home, and camera integrations.
   - Route them through the same tool registry, permissions, confirmations, and result reporting.
   - Keep agent-specific dependencies optional so missing CAD/printer hardware does not prevent Ada from starting.

6. **Portable runtime and data**
   - Resolve all runtime paths from the Ada project root, not the current working directory.
   - Launch the project-local Python environment explicitly from Electron.
   - Keep model caches, downloaded model files, virtual environments, logs, voice caches, settings, and memory under the selected `ada_v2` directory.
   - Provide a single configuration path for the install root and runtime directories.
   - Do not assume C: is available or use global package/model caches by default.

7. **Verification**
   - Preflight checks the actual running services and full user paths.
   - Report model load/availability, first-token latency, STT time, TTS first-audio time, and end-to-end turn time.
   - Test a memory capture followed immediately by retrieval.
   - Test interrupt and mute behavior.
   - Test tool confirmation and denial.
   - Run a local-only network drill and report every non-loopback connection.

## Implementation order

1. **Protect and inventory the active working tree.** Reconcile the GitHub `main` tree with the user's current local `ada_v2` directory before overwriting files. The inspected remote tree does not currently contain a `scripts/ai/` directory or the K2 runtime setup scripts discussed in the recent setup work; do not delete or replace local files based on this remote snapshot.
2. **Make startup portable.** Root-relative paths, project-local interpreter selection, data-directory configuration, optional imports, and no-key startup.
3. **Introduce the provider registry.** Wire the existing K2 and Gemma 4 runtimes through the same provider contract; retain Gemini only as an optional compatibility provider.
4. **Unify tool execution and safety.** Centralize confirmation enforcement and remove automatic safety acknowledgements.
5. **Build durable memory and retrieval.** Fix the current save handler, create Markdown capture/index pipeline, and return source IDs.
6. **Add local speech.** Integrate Windows-compatible local STT and configured TTS, then wake-word and barge-in.
7. **Add the knowledge graph to the existing UI.** Do not create a separate JARVIS website/application.
8. **Add preflight and offline proof.** Run end-to-end checks only after the corresponding chains are implemented.

## Non-goals / constraints

- Do not create a second assistant or separate JARVIS application.
- Do not remove working CAD, browser, printer, smart-home, camera, or project features without an explicit replacement decision.
- Do not make Ollama mandatory solely because it appears in the PDFs.
- Do not use the Apple-only MLX audio route on Windows.
- Do not require cloud API keys for local mode.
- Do not place model weights, virtual environments, Python packages, browser runtimes, caches, or user data on C: by default.
- Do not claim offline operation until the network drill passes.
- Do not claim the Opus 5.5 PDF was reviewed until its text has actually been extracted.

## Current status

This document records the first repository/reference audit. It is not a claim that the runtime has already been restructured or that any preflight has passed. The next code change should begin with startup portability and provider abstraction, after reconciling the remote tree with the user's current local K2/Gemma setup.
