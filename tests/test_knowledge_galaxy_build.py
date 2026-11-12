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
