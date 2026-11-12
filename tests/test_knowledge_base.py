"""Tests for local knowledge indexing and durable captures."""
from knowledge_base import KnowledgeBase


def make_knowledge(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    database = tmp_path / ".ada" / "knowledge.sqlite3"
    captures = tmp_path / ".ada" / "memory" / "captures"
    return KnowledgeBase(database, captures, lambda: [docs]), docs


def test_markdown_documents_are_searchable_with_source_ids(tmp_path):
    knowledge, docs = make_knowledge(tmp_path)
    (docs / "World Design.md").write_text(
        "# World Design\n\nAlderlight contains a northern river and a mountain pass.",
        encoding="utf-8",
    )

    results = knowledge.search("Alderlight mountain pass", limit=3)

    assert len(results) == 1
    assert results[0]["title"] == "World Design"
    assert results[0]["source"].startswith("K")
    assert "mountain pass" in results[0]["excerpt"]


def test_remember_writes_markdown_and_indexes_it_immediately(tmp_path):
    knowledge, _docs = make_knowledge(tmp_path)

    saved = knowledge.remember("The first playable region is Alderlight.")

    assert saved["path"].endswith(".md")
    assert "Alderlight" in open(saved["path"], encoding="utf-8").read()
    results = knowledge.search("first playable region Alderlight")
    assert any(item["id"] == saved["id"] for item in results)


def test_graph_uses_contiguous_array_ids_and_links_wikilinks(tmp_path):
    knowledge, docs = make_knowledge(tmp_path)
    (docs / "Alderlight.md").write_text(
        "# Alderlight\n\nThe starting region for the world.",
        encoding="utf-8",
    )
    (docs / "World Plan.md").write_text(
        "# World Plan\n\nThe first area is [[Alderlight]].",
        encoding="utf-8",
    )

    graph = knowledge.graph()

    assert [node["id"] for node in graph["nodes"]] == list(range(len(graph["nodes"])))
    assert graph["count"] == 2
    assert len(graph["links"]) == 1



def test_read_source_returns_bounded_chunks_and_offsets(tmp_path):
    knowledge, docs = make_knowledge(tmp_path)
    (docs / "Long Note.md").write_text("# Long Note\n\n" + ("Alderlight river. " * 2500), encoding="utf-8")
    results = knowledge.search("Alderlight river")
    source_id = results[0]["id"]

    first = knowledge.read_source(source_id, offset=0, limit=1000)
    second = knowledge.read_source(source_id, offset=first["next_offset"], limit=1000)

    assert len(first["content"]) == 1000
    assert second["offset"] == first["next_offset"]
    assert second["content"]
