# Knowledge Galaxy

The Knowledge Galaxy is integrated into Ada's existing Knowledge Graph window and is also available as a local Chrome viewer.

## Notes folder

By default, Markdown notes are read recursively from the Ada project notes folder: notes/. Put your .md files there. Captures made with “remember that…” are written to notes/captures/.

To use a different folder, set ADA_NOTES_DIR to its absolute path in the environment used to launch both Ada and the viewer server. The same path must be visible to both processes.

## Credentials and privacy

On first backend launch, Ada creates config.json in the project root with these values:

    {
      "api_key": "PUT-YOUR-KEY-HERE",
      "model": "claude-opus-4-8"
    }

Add your Anthropic API key to that local file yourself. The file is Git-ignored, Vite explicitly denies browser access to it, and the Chrome viewer server serves static files exclusively from viewer/. The key is used only by Ada's Python backend and is never sent to the browser.

Note Q&A uses the Anthropic Messages API and therefore requires internet access and may incur API charges. Speech recognition and speech synthesis use the browser's built-in Web Speech APIs; no separate voice subscription or Python voice packages are used by the Galaxy.

## Chrome viewer

1. Start Ada normally so its FastAPI backend is listening on 127.0.0.1:8001.
2. In a second PowerShell window, from the Ada project root, run:

       .venv\Scripts\python.exe .\build.py
       .venv\Scripts\python.exe .\server.py

3. Open **http://127.0.0.1:4700** in Chrome.

The root server.py uses only Python's standard library. It serves static assets from viewer/ only and proxies /chat and /remember to Ada's local backend. build.py also uses only the Python standard library and writes viewer/graph-data.js.

The 3D renderer is loaded from the 3d-force-graph CDN, so the first browser load requires internet access for that library. Notes and graph data remain local.

## Behaviour

- Nodes have numeric IDs equal to their array positions.
- Filename-derived labels, folder groups, and 700-character excerpts are generated from Markdown notes.
- Connections are built from title mentions and shared [[wikilinks]].
- Note questions retrieve the six highest-scoring notes, weighting title matches more heavily.
- Source IDs are mapped back to the viewer's own node-array indexes before highlighting.
- Four or more sources illuminate the contributing cluster; smaller source sets fly to the top source and illuminate its direct neighbors.
- Typed or spoken “remember that…” captures create Markdown files and add them to the graph live.
- Small talk returns no source nodes and does not move the camera.
- Browser speech prefers an available British English voice. Chrome microphone permission is required for speech input.

## Manual verification checklist

After Ada and the Chrome viewer are running:

1. Open http://127.0.0.1:4700 in Chrome and allow the page to finish indexing.
2. Click once anywhere in the galaxy to unlock browser speech. Confirm the boot greeting is spoken with the actual note count.
3. Type a question whose answer is clearly stated in one note. Confirm a short answer appears and is spoken; the source node and its direct neighbors illuminate, the camera flies to the source, and the excerpt appears in the side panel.
4. Ask a question that requires facts from at least four notes. Confirm the contributing cluster illuminates without flying to one node.
5. Type “hello” or “tell me a joke”. Confirm Jarvis responds but the camera and source selection do not move.
6. Click the microphone and say a question about a note. Confirm “● listening…” then “● thinking…” appear, the transcript follows the normal chat flow, and the answer is spoken.
7. Ask a follow-up question that refers to the previous answer. Confirm the session history helps resolve the follow-up.
8. Type “remember that I prefer …” and submit. Confirm a Markdown file appears in notes/captures/, a new node is added without reloading the page, it appears near the most related existing node with a glow pulse, and Jarvis speaks a short confirmation.
9. Repeat the memory capture using the microphone.
10. Open http://127.0.0.1:4700/config.json and confirm it returns 404. Also confirm the root server cannot serve paths outside viewer/.

The first two note-question checks require actual Markdown notes with known facts. The microphone check requires Chrome microphone permission. The Anthropic Q&A check requires a valid key in the project-root config.json.
