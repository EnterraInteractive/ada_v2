#!/usr/bin/env python3
"""Build the Knowledge Galaxy graph from Markdown notes using only Python's standard library."""
from __future__ import annotations

import json
import os
import re
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES_DIR = Path(os.environ.get("ADA_NOTES_DIR", ROOT / "notes")).expanduser().resolve()
VIEWER_DIR = ROOT / "viewer"
OUTPUT = VIEWER_DIR / "graph-data.js"
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
WORD = re.compile(r"[\w'-]{2,}", re.UNICODE)
IGNORED = {".git", ".ada", "node_modules", ".venv", "venv", "__pycache__"}


def build_graph() -> dict:
    VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    if NOTES_DIR.is_dir():
        for path in NOTES_DIR.rglob("*.md"):
            relative = path.relative_to(NOTES_DIR)
            if any(part.startswith(".") or part in IGNORED for part in relative.parts):
                continue
            if path.is_file():
                files.append(path)
    files.sort(key=lambda item: item.relative_to(NOTES_DIR).as_posix().casefold())

    nodes = []
    bodies = []
    wikilinks = []
    title_map: dict[str, list[int]] = {}
    for index, path in enumerate(files):
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = path.relative_to(NOTES_DIR)
        label_stem = re.sub(r"^\d{8}_\d{6}_\d+_", "", path.stem)
        label = label_stem.replace("_", " ").replace("-", " ").strip() or path.name
        clean = re.sub(r"\s+", " ", body).strip()
        excerpt = clean[:700] + ("…" if len(clean) > 700 else "")
        group = relative.parent.as_posix() if relative.parent.as_posix() != "." else "notes"
        nodes.append({
            "id": len(nodes),
            "label": label,
            "group": group,
            "excerpt": excerpt,
            "path": str(path.resolve()),
        })
        bodies.append(body)
        tags = {
            item.strip().split("|", 1)[0].strip().casefold()
            for item in WIKILINK.findall(body)
        }
        wikilinks.append(tags)
        title_map.setdefault(label.casefold(), []).append(len(nodes) - 1)

    links = set()
    for index, body in enumerate(bodies):
        for target in wikilinks[index]:
            for other in title_map.get(target, []):
                if other != index:
                    links.add(tuple(sorted((index, other))))
        for title, targets in title_map.items():
            if len(title) < 3:
                continue
            if re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", body, re.IGNORECASE):
                for other in targets:
                    if other != index:
                        links.add(tuple(sorted((index, other))))

    for left, right in combinations(range(len(nodes)), 2):
        if wikilinks[left] and wikilinks[left].intersection(wikilinks[right]):
            links.add((left, right))

    graph = {
        "nodes": nodes,
        "links": [{"source": left, "target": right} for left, right in sorted(links)],
    }
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    temporary = OUTPUT.with_suffix(".js.tmp")
    temporary.write_text(
        "(function(){ const GRAPH = " + payload + "; window.__GRAPH__ = GRAPH; })();\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    return graph


if __name__ == "__main__":
    graph = build_graph()
    print(f"Knowledge Galaxy: {len(graph['nodes'])} notes, {len(graph['links'])} links")
    print(f"Graph data written to {OUTPUT}")
