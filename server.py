#!/usr/bin/env python3
"""Local Chrome server for the Knowledge Galaxy. Static files are restricted to ./viewer."""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import unquote

from build import build_graph

ROOT = Path(__file__).resolve().parent
VIEWER = (ROOT / "viewer").resolve()
BACKEND = "http://127.0.0.1:8001"


class GalaxyHandler(BaseHTTPRequestHandler):
    server_version = "AdaKnowledgeGalaxy/1.0"

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _backend(self, endpoint: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            BACKEND + endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path == "/graph":
            try:
                self._json(200, build_graph())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return

        relative = path.lstrip("/") or "index.html"
        candidate = (VIEWER / relative).resolve()
        try:
            candidate.relative_to(VIEWER)
        except ValueError:
            self.send_error(404)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type in {"text/html", "text/css", "application/javascript", "text/javascript"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path not in {"/chat", "/remember"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 64 * 1024:
                self._json(400, {"error": "Request must be between 1 byte and 64 KB."})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object.")
            if self.path == "/chat":
                result = self._backend("/chat", payload)
                graph = build_graph()
                path_to_index = {str(Path(node["path"]).resolve()).casefold(): node["id"] for node in graph["nodes"]}
                mapped = []
                for note in result.get("used_notes", []):
                    note_path = note.get("path")
                    if note_path:
                        index = path_to_index.get(str(Path(note_path).resolve()).casefold())
                        if index is not None:
                            mapped.append(index)
                result["nodes"] = mapped
                self._json(200, result)
                return

            result = self._backend("/remember", payload)
            if result.get("error"):
                self._json(200, result)
                return
            graph = build_graph()
            path_to_index = {str(Path(node["path"]).resolve()).casefold(): node["id"] for node in graph["nodes"]}
            saved_path = str(Path(result.get("path", "")).resolve()).casefold()
            result["node_index"] = path_to_index.get(saved_path)
            anchor_path = result.get("anchor_path")
            result["anchor_node_index"] = path_to_index.get(str(Path(anchor_path).resolve()).casefold()) if anchor_path else None
            self._json(200, result)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            self._json(exc.code, {"error": detail or str(exc)})
        except URLError:
            self._json(503, {"error": "Ada's backend is not running on 127.0.0.1:8001. Start Ada first."})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):
        print("[GALAXY] " + (fmt % args))


if __name__ == "__main__":
    build_graph()
    print("[GALAXY] Serving viewer files only at http://127.0.0.1:4700")
    print("[GALAXY] API requests are proxied to Ada's local backend on port 8001.")
    ThreadingHTTPServer(("127.0.0.1", 4700), GalaxyHandler).serve_forever()
