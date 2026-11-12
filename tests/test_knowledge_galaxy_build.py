from __future__ import annotations

import json
from pathlib import Path

import build


def test_markdown_graph_uses_array_indexes_and_links_titles_and_wikilinks(tmp_path, monkeypatch):
    notes = tmp_path / "notes"
    viewer = tmp_path / "viewer"
    (notes / "Operations").mkdir(parents=True)
    (notes / "Finance").mkdir()
    (notes / "Operations" / "Inventory.md").write_text(
        "# Inventory\n\nSupplier Guide explains ordering. [[Shared Topic]]\n", encoding="utf-8"
    )
    (notes / "Operations" / "Supplier Guide.md").write_text(
        "# Supplier Guide\n\n[[Shared Topic]]\n", encoding="utf-8"
    )
    (notes / "Finance" / "Budget.md").write_text(
        "# Budget\n\nThis note also references [[Shared Topic]].\n", encoding="utf-8"
    )
    monkeypatch.setattr(build, "NOTES_DIR", notes)
    monkeypatch.setattr(build, "VIEWER_DIR", viewer)
    monkeypatch.setattr(build, "OUTPUT", viewer / "graph-data.js")

    graph = build.build_graph()

    assert [node["id"] for node in graph["nodes"]] == list(range(len(graph["nodes"])))
    assert graph["nodes"][0]["label"] == "Budget"
    assert graph["nodes"][0]["group"] == "Finance"
    assert len(graph["nodes"][0]["excerpt"]) <= 701
    edges = {
        tuple(sorted((link["source"], link["target"])))
        for link in graph["links"]
    }
    assert (0, 1) in edges  # Shared wikilink
    assert (1, 2) in edges  # Filename title mention
    generated = (viewer / "graph-data.js").read_text(encoding="utf-8")
    assert "const GRAPH =" in generated
    assert "window.__GRAPH__ = GRAPH" in generated


def test_galaxy_backend_uses_only_the_local_model_runtime():
    backend = Path(__file__).resolve().parents[1] / "backend" / "server.py"
    source = backend.read_text(encoding="utf-8")
    compile(source, str(backend), "exec")

    assert "await model_runtime.chat(messages=messages, max_tokens=600)" in source
    assert "GALAXY_SYSTEM_PROMPT" in source
    assert "api.anthropic.com" not in source
    assert "ANTHROPIC_API_KEY" not in source
    assert "_galaxy_chat_sync" not in source


def test_offline_galaxy_viewer_uses_local_assets_and_local_hearing():
    root = Path(__file__).resolve().parents[1]
    viewer = (root / "viewer" / "index.html").read_text(encoding="utf-8")
    assert 'src="/vendor/3d-force-graph.min.js"' in viewer
    assert "https://" not in viewer
    assert "http://" not in viewer
    assert "SpeechRecognition" not in viewer
    assert "webkitSpeechRecognition" not in viewer
    assert "getUserMedia" in viewer
    assert "function toggleHandsFree" in viewer
    assert "function addNote" in viewer
    assert "function speechChunks" in viewer
    assert "audio_wav" in viewer
    assert "decodeAudioData" in viewer
    assert "speechSynthesis" in viewer
    assert "localService" in viewer
    assert "/hear" in viewer and "/speak" in viewer


def test_local_voice_and_offline_drill_modules_compile():
    root = Path(__file__).resolve().parents[1]
    modules = [
        root / "server.py",
        root / "backend" / "server.py",
        root / "backend" / "local_voice.py",
        root / "backend" / "voice_studio.py",
        root / "backend" / "network_audit.py",
        root / "scripts" / "ai" / "download_local_voice_models.py",
        root / "scripts" / "ai" / "drill_offline.py",
    ]
    for module in modules:
        source = module.read_text(encoding="utf-8")
        compile(source, str(module), "exec")


def test_local_speech_models_and_voice_studio_are_project_local():
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "backend" / "settings.json").read_text(encoding="utf-8"))
    voice = settings["voice"]
    assert voice["whisper_model_path"] == "models/voice/whisper-large-v3-turbo"
    assert voice["wake_model_path"] == "models/voice/whisper-small"
    assert voice["piper_model_path"].startswith("models/voice/")
    studio = settings["voice_studio"]
    assert studio["url"] == "http://127.0.0.1:3900"
    assert studio["profile"] == "Jarvis"
    downloader = (root / "scripts" / "ai" / "download_local_voice_models.py").read_text(encoding="utf-8")
    assert "Systran/faster-whisper-small" in downloader
    assert "Systran/faster-whisper-large-v3-turbo" in downloader


def test_voice_studio_adapter_caches_locally_and_uses_loopback():
    root = Path(__file__).resolve().parents[1]
    source = (root / "backend" / "voice_studio.py").read_text(encoding="utf-8")
    assert "http://127.0.0.1:3900" in source
    assert '"/engines/select"' in source
    assert '"/profiles"' in source
    assert '"/v1/audio/speech"' in source
    assert '".ada" / "cache" / "voice"' in source
    assert "Standing by." in source
    backend = (root / "backend" / "server.py").read_text(encoding="utf-8")
    assert 'data.get("audio_wav")' in backend
    assert 'media_type="audio/wav"' in backend
    assert 'X-Jarvis-Voice' in backend


def test_offline_network_audit_and_drill_are_present():
    root = Path(__file__).resolve().parents[1]
    audit = (root / "backend" / "network_audit.py").read_text(encoding="utf-8")
    drill = (root / "scripts" / "ai" / "drill_offline.py").read_text(encoding="utf-8")
    viewer = (root / "viewer" / "index.html").read_text(encoding="utf-8")
    assert "socket.socket.connect" in audit
    assert "record_browser_resources" in audit
    assert "fetch('/network-audit'" in viewer
    assert 'self._backend("/network-audit/browser", payload)' in (root / "server.py").read_text(encoding="utf-8")
    assert "NON-LOCAL HOSTS" in drill
    assert "scripts" in str(root / "scripts")


def test_live_remember_and_status_routes_match_the_viewer_proxy_contract():
    root = Path(__file__).resolve().parents[1]
    backend = (root / "backend" / "server.py").read_text(encoding="utf-8")
    proxy = (root / "server.py").read_text(encoding="utf-8")
    viewer = (root / "viewer" / "index.html").read_text(encoding="utf-8")

    assert '@app.post("/remember")' in backend
    assert '"node_index": node.get("id") if node else None' in backend
    assert '"anchor_node_index": anchor.get("id") if anchor else None' in backend
    assert 'if path == "/brain":' in proxy and 'BACKEND + "/brain/status"' in proxy
    assert 'if path == "/voice":' in proxy and 'BACKEND + "/voice/status"' in proxy
    assert 'self._backend("/remember", payload)' in proxy
    assert 'result["node_index"] = path_to_index.get(saved_path)' in proxy
    assert 'result["anchor_node_index"]' in proxy
    assert "fetch('/brain')" in viewer and "fetch('/voice')" in viewer
    assert "addNote(result.anchor_node_index??null,result.node_index??null)" in viewer
    assert "showNode(node,true)" in viewer
