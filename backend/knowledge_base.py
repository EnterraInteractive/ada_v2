"""Project-local document index, memory capture, and knowledge graph for A.D.A."""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Callable, Iterable


SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf"}
IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".vs", ".ada",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env", "Binaries", "Intermediate",
    "DerivedDataCache", "Saved", "Build", "dist", "coverage", "Cache",
}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "secrets.json", "credentials.json"}
TOKEN_RE = re.compile(r"[\w'-]{2,}", re.UNICODE)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class KnowledgeBase:
    """Incremental SQLite FTS index over project documents and durable captures.

    The database and captures live under the Ada project root. External workspaces
    are read-only sources; the assistant never writes captures into them.
    """

    def __init__(
        self,
        database_path: str | Path,
        capture_dir: str | Path,
        source_roots: Callable[[], Iterable[str | Path]],
        max_file_bytes: int = 8 * 1024 * 1024,
    ):
        self.database_path = Path(database_path).resolve()
        self.capture_dir = Path(capture_dir).resolve()
        self.source_roots = source_roots
        self.max_file_bytes = max_file_bytes
        self._indexed_this_process = False
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(title, content, tokenize='unicode61')
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)")

    @staticmethod
    def _title(path: Path, content: str) -> str:
        for line in content.splitlines()[:20]:
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title[:180]
        return path.stem.replace("_", " ").replace("-", " ").strip()[:180] or path.name

    @staticmethod
    def _excerpt(content: str, limit: int = 700) -> str:
        cleaned = re.sub(r"\s+", " ", content).strip()
        return cleaned[:limit] + ("…" if len(cleaned) > limit else "")

    def _read_document(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("PDF indexing requires pypdf; install the project requirements.") from exc
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                try:
                    if not reader.decrypt(""):
                        return ""
                except Exception:
                    return ""
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return path.read_text(encoding="utf-8", errors="replace")

    def _index_path(self, path: Path) -> int | None:
        try:
            stat = path.stat()
            if stat.st_size > self.max_file_bytes or path.name.lower() in SENSITIVE_NAMES:
                return None
            content = self._read_document(path).strip()
            if not content:
                return None
            digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            resolved = str(path.resolve())
            title = self._title(path, content)
            group_name = path.parent.name or "root"
            excerpt = self._excerpt(content)
            now = datetime.now(timezone.utc).isoformat()

            with self._connect() as db:
                existing = db.execute(
                    "SELECT id, content_hash, modified_ns, size_bytes FROM documents WHERE path = ?",
                    (resolved,),
                ).fetchone()
                if existing and existing["content_hash"] == digest and existing["modified_ns"] == stat.st_mtime_ns and existing["size_bytes"] == stat.st_size:
                    return int(existing["id"])

                if existing:
                    document_id = int(existing["id"])
                    db.execute("""
                        UPDATE documents
                        SET title=?, group_name=?, excerpt=?, content=?, content_hash=?,
                            modified_ns=?, size_bytes=?, indexed_at=?
                        WHERE id=?
                    """, (title, group_name, excerpt, content, digest, stat.st_mtime_ns, stat.st_size, now, document_id))
                    db.execute("DELETE FROM documents_fts WHERE rowid=?", (document_id,))
                else:
                    cursor = db.execute("""
                        INSERT INTO documents
                        (path, title, group_name, excerpt, content, content_hash, modified_ns, size_bytes, indexed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (resolved, title, group_name, excerpt, content, digest, stat.st_mtime_ns, stat.st_size, now))
                    document_id = int(cursor.lastrowid)

                db.execute(
                    "INSERT INTO documents_fts(rowid, title, content) VALUES (?, ?, ?)",
                    (document_id, title, content),
                )
                return document_id
        except Exception as exc:
            print(f"[KNOWLEDGE] Skipped {path}: {type(exc).__name__}: {exc}")
            return None

    def _iter_source_files(self, root: Path):
        if root.is_file():
            if root.suffix.lower() in SUPPORTED_SUFFIXES:
                yield root
            return
        if not root.is_dir():
            return
        for current, directories, filenames in os.walk(root):
            directories[:] = sorted(
                name for name in directories
                if name not in IGNORED_DIRECTORIES and not name.startswith(".")
            )
            for filename in sorted(filenames):
                path = Path(current) / filename
                if path.suffix.lower() in SUPPORTED_SUFFIXES and filename.lower() not in SENSITIVE_NAMES:
                    yield path

    def reindex(self) -> dict:
        indexed = 0
        skipped = 0
        roots = []
        for value in self.source_roots():
            root = Path(value).expanduser().resolve()
            if root not in roots and root.exists():
                roots.append(root)

        # Captures are always indexed, even when the active workspace changes.
        if self.capture_dir not in roots:
            roots.append(self.capture_dir)

        for root in roots:
            root_seen: set[str] = set()
            for path in self._iter_source_files(root):
                resolved = str(path.resolve())
                root_seen.add(resolved)
                if self._index_path(path) is None:
                    skipped += 1
                else:
                    indexed += 1

            # Remove stale entries only for roots that were successfully scanned.
            resolved_root = root.resolve()
            with self._connect() as db:
                all_paths = [row["path"] for row in db.execute("SELECT path FROM documents").fetchall()]
                existing_paths = []
                for stored_path in all_paths:
                    candidate = Path(stored_path)
                    if candidate == resolved_root or (resolved_root.is_dir() and candidate.is_relative_to(resolved_root)):
                        existing_paths.append(stored_path)
                stale = [path for path in existing_paths if path not in root_seen]
                for stale_path in stale:
                    row = db.execute("SELECT id FROM documents WHERE path=?", (stale_path,)).fetchone()
                    if row:
                        db.execute("DELETE FROM documents_fts WHERE rowid=?", (row["id"],))
                    db.execute("DELETE FROM documents WHERE path=?", (stale_path,))

        self._indexed_this_process = True
        with self._connect() as db:
            total = int(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        return {"indexed": indexed, "skipped": skipped, "total": total, "roots": [str(root) for root in roots]}

    def ensure_indexed(self) -> None:
        if not self._indexed_this_process:
            self.reindex()

    def search(self, query: str, limit: int = 6) -> list[dict]:
        self.ensure_indexed()
        tokens = TOKEN_RE.findall(query or "")
        if not tokens:
            return []
        expression = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:16])
        with self._connect() as db:
            rows = db.execute("""
                SELECT d.id, d.path, d.title, d.group_name, d.excerpt,
                       bm25(documents_fts, 5.0, 1.0) AS rank
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
            """, (expression, max(1, min(int(limit), 20)))).fetchall()
        return [
            {
                "id": int(row["id"]),
                "source": f"K{int(row['id'])}",
                "path": row["path"],
                "title": row["title"],
                "group": row["group_name"],
                "excerpt": row["excerpt"],
            }
            for row in rows
        ]

    def remember(self, text: str) -> dict:
        body = (text or "").strip()
        if not body:
            raise ValueError("There is nothing to remember.")
        words = re.findall(r"[\w'-]+", body, re.UNICODE)
        title = " ".join(words[:9]).strip().rstrip(".,:;!?") or "Memory"
        title = title[:100]
        slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:64] or "memory"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.capture_dir / f"{stamp}_{slug}.md"
        captured = datetime.now(timezone.utc).isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\nCaptured: {captured}\n\n{body}\n", encoding="utf-8")
        document_id = self._index_path(path)
        if document_id is None:
            raise RuntimeError("The memory file was written, but could not be added to the knowledge index.")
        self._indexed_this_process = True
        return {"id": document_id, "source": f"K{document_id}", "title": title, "path": str(path)}

    def graph(self, limit: int = 1200) -> dict:
        self.ensure_indexed()
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, path, title, group_name, excerpt, substr(content, 1, 20000) AS content FROM documents ORDER BY id LIMIT ?",
                (max(1, min(int(limit), 2000)),),
            ).fetchall()

        nodes = []
        row_to_index = {}
        for index, row in enumerate(rows):
            row_to_index[int(row["id"])] = index
            nodes.append({
                "id": index,
                "source_id": int(row["id"]),
                "label": row["title"],
                "group": row["group_name"],
                "path": row["path"],
                "excerpt": row["excerpt"],
            })

        title_lookup = {}
        for row in rows:
            title = str(row["title"]).strip().casefold()
            if len(title) >= 4:
                title_lookup.setdefault(title, int(row["id"]))
        title_pattern = None
        if title_lookup:
            alternatives = "|".join(re.escape(title) for title in sorted(title_lookup, key=len, reverse=True))
            title_pattern = re.compile(r"(?<!\w)(?:" + alternatives + r")(?!\w)", re.IGNORECASE)

        links = set()
        references_by_id = {}
        for row in rows:
            source_id = int(row["id"])
            body = str(row["content"])
            wiki_targets = {
                match.strip().split("|", 1)[0].strip().casefold()
                for match in WIKILINK_RE.findall(body)
            }
            references_by_id[source_id] = wiki_targets
            for target_title in wiki_targets:
                target_id = title_lookup.get(target_title)
                if target_id and target_id != source_id:
                    pair = tuple(sorted((source_id, target_id)))
                    links.add(pair)

            if title_pattern:
                for match in title_pattern.finditer(body):
                    target_id = title_lookup.get(match.group(0).casefold())
                    if target_id and target_id != source_id:
                        pair = tuple(sorted((source_id, target_id)))
                        links.add(pair)

        # Notes that share one or more explicit wikilinks are also connected.
        ids = list(references_by_id)
        for left, right in combinations(ids, 2):
            if references_by_id[left] and references_by_id[left].intersection(references_by_id[right]):
                links.add(tuple(sorted((left, right))))

        graph_links = [
            {"source": row_to_index[left], "target": row_to_index[right]}
            for left, right in sorted(links)
            if left in row_to_index and right in row_to_index
        ]
        return {"nodes": nodes, "links": graph_links, "count": len(nodes)}
