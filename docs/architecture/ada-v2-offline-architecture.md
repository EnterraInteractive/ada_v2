# A.D.A V2 — Offline-First Architecture and Completion Contract

## Product direction

A.D.A remains one desktop assistant. This document is the implementation contract for integrating the capabilities from the repository's JARVIS reference PDFs into the existing Electron, React, FastAPI/Socket.IO, and in-process llama.cpp application. It is not a second application and does not authorize replacing working features without a compatibility plan.

## Non-negotiable constraints

- K2-Horizon remains the primary reasoning, coding, and tool-use model.
- Gemma 4 remains available for vision and may be selected for chat where its registered capabilities permit it.
- Additional local models must be addable through the model registry and provider adapters, without hard-coded model-specific branches in the UI.
- Local inference, speech recognition, speech synthesis, model files, browser binaries, caches, indexes, captures, logs, and temporary files must live beneath the A.D.A project directory.
- No cloud LLM, cloud speech recognition, cloud TTS, or cloud coding agent may be required for normal assistant operation.
- Optional network-connected tools must be visibly identified and independently disableable.
- Preserve the existing browser, workspace, Unreal MCP, camera, gesture, and project-management capabilities.
- Do not run installation, model-download, build, or test operations on the user's machine before the user explicitly requests the completed release.

## Current implementation audit (repository branch: feature/ada-development-assistant-strip)

| Area | Current implementation | Completion gap |
|---|---|---|
| Primary reasoning | In-process llama.cpp with K2-Horizon GGUF | Runtime must be validated against the pinned build and actual model file |
| Vision | Gemma 4 GGUF + mmproj through llama.cpp multimodal handler | Validate image paths, handler compatibility, memory release, and failure recovery |
| Model extensibility | JSON model registry and Settings editor | Formalize provider/capability contract and validate model configs before loading |
| Voice | Gemini Live API adapter | Cloud-dependent; replace normal path with local STT + local TTS |
| Memory | SQLite FTS index and Markdown captures | Add lifecycle, retention, backup/recovery, and privacy controls |
| Knowledge | Markdown/text/PDF extraction and source IDs | Add robust parsing, indexing status, refresh/deletion behavior, and source-grounded answer enforcement |
| Knowledge Galaxy | React graph window backed by knowledge endpoints | Verify graph data semantics and interaction behavior |
| Browser | Playwright browser agent | Audit permission boundaries, navigation restrictions, and offline behavior |
| Workspace tools | Read/write/search/terminal tools | Review path containment, command approval, output limits, and audit logging |
| Unreal integration | Existing Unreal MCP client | Preserve as optional local integration; verify reconnect and tool permission behavior |
| Offline operation | Local text/vision inference and local knowledge | Current voice provider is cloud-only; browser and external MCP endpoints are optional network/local integrations |
| Packaging | Project-local Python, Node, browser, and caches | Verify every subprocess, environment variable, cache, and model path; document machine-level prerequisites |

## Target runtime architecture

1. **Conversation orchestrator:** one session and message history, independent of model provider.
2. **Model provider registry:** capability-based selection (chat, reasoning, coding, tools, vision, and future modalities). Model metadata declares provider, model path, context limits, quantization, GPU settings, and optional projector.
3. **Primary model:** K2-Horizon for reasoning, coding, planning, and tool orchestration.
4. **Specialist delegation:** Gemma 4 for image understanding and other registered specialist models for future capabilities. Delegation results return to the same conversation.
5. **Local voice pipeline:** local microphone capture → local VAD/utterance segmentation → local Whisper-family transcription → the same conversation orchestrator → local TTS → selected audio output. Voice must not bypass tool permissions or confirmation gates.
6. **Memory service:** explicit user-directed captures, searchable durable memory, editable/deletable records, and session context kept distinct from long-term memory.
7. **Knowledge service:** incremental document indexing, source metadata, chunk retrieval, source IDs, complete-source reading, and reindex/removal controls.
8. **Tool gateway:** one permission and confirmation layer for filesystem, terminal, browser, Unreal MCP, and future integrations.
9. **Offline policy:** local services are the default. External services require explicit enablement and must show when they are being used.

## Implementation sequence

### A. Runtime and model safety
- Formalize model-provider and capability interfaces.
- Validate model registry entries and paths before load.
- Add model-load serialization, cancellation, cleanup, and deterministic recovery.
- Verify K2 tool-call parsing and Gemma multimodal handling.
- Add a local model inventory and readiness report without downloading weights automatically.

### B. Fully local voice
- Add local speech-recognition and synthesis adapters with project-relative model paths.
- Replace cloud-only voice assumptions in server events and Settings.
- Preserve the existing microphone selection, mute, playback-device selection, and interruption behavior.
- Add utterance segmentation and a clear listening/thinking/speaking state machine.
- Keep Gemini only as an explicitly optional provider, never as a hidden fallback.

### C. Memory and knowledge
- Add safe document discovery and incremental indexing.
- Track source status, errors, modified/deleted files, and extraction quality.
- Improve retrieval with chunk-level ranking and source-grounded citations.
- Add memory review, edit, deletion, and export/backup operations.
- Ensure sensitive files and secrets are excluded.

### D. Tools and automation
- Centralize permissions and confirmations.
- Add tool execution audit records and cancellation/timeouts.
- Keep browser and Unreal MCP tools optional and local-first.
- Ensure external content is treated as untrusted input.

### E. Interface and release
- Present model, voice, memory, knowledge, and tool status in one consistent interface.
- Add explicit offline/online status and provider indicators.
- Remove CDN/runtime network requirements where practical.
- Add deterministic setup, preflight, health checks, recovery, and user documentation.

## Release gates

A.D.A is not complete merely because source files or setup scripts exist. The release is complete only when:
- all Python and frontend dependencies are pinned and reproducibly installed project-locally;
- local K2 chat and tool use work on the target RTX 5070 configuration;
- Gemma 4 vision works and model switching recovers correctly;
- local voice input and output work without a network connection;
- memory capture, search, source reading, reindex, deletion, and restart persistence work;
- browser and Unreal integrations respect permission gates;
- offline mode is verified with external network access disabled;
- all automated checks pass and known limitations are documented;
- no required model, runtime, cache, or generated data is placed outside the A.D.A project directory (machine drivers and explicitly documented build prerequisites are the exception).

## Current status

This contract is a scope and audit artifact, not a claim that the listed work is complete. No local installation, model download, build, or test has been run as part of authoring this document.
