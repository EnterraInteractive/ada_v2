import json
import os
import re
import shutil
import time
from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".vs", ".ada",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env", "Binaries", "Intermediate",
    "DerivedDataCache", "Saved", "Build", "dist", "coverage", "Cache",
}
TEXT_EXTENSIONS = {
    ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md",
    ".html", ".css", ".jsonl", ".h", ".hpp", ".c", ".cc", ".cpp",
    ".cs", ".ini", ".uproject", ".uplugin", ".xml", ".cmake",
    ".csproj", ".sln", ".sh", ".ps1", ".yaml", ".yml", ".toml",
}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "secrets.json", "credentials.json"}


class ProjectManager:
    """Manages named A.D.A projects and explicitly selected external workspaces."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.projects_dir = self.workspace_root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.current_project = "temp"
        self.active_project_path = self.projects_dir / "temp"
        self.is_external_workspace = False

        temp_path = self.projects_dir / "temp"
        if temp_path.exists():
            shutil.rmtree(temp_path)
        temp_path.mkdir(parents=True, exist_ok=True)
        (temp_path / "browser").mkdir(exist_ok=True)

    def create_project(self, name: str):
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
        if not safe_name:
            return False, "Project name is empty or invalid."
        project_path = (self.projects_dir / safe_name).resolve()
        if project_path.parent != self.projects_dir.resolve():
            return False, "Invalid project name."
        if project_path.exists():
            return False, f"Project '{safe_name}' already exists."
        project_path.mkdir(parents=True)
        (project_path / "browser").mkdir(exist_ok=True)
        self.current_project = safe_name
        self.active_project_path = project_path
        self.is_external_workspace = False
        return True, f"Created and opened project '{safe_name}'."

    def switch_project(self, name: str):
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
        project_path = (self.projects_dir / safe_name).resolve()
        if project_path.parent != self.projects_dir.resolve() or not project_path.is_dir():
            return False, f"Project '{safe_name}' does not exist."
        self.current_project = safe_name
        self.active_project_path = project_path
        self.is_external_workspace = False
        return True, f"Switched to project '{safe_name}'."

    def open_workspace(self, path: str):
        candidate = Path(path).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            return False, f"Workspace is not a directory: {candidate}"
        self.active_project_path = candidate
        self.current_project = candidate.name
        self.is_external_workspace = True
        return True, f"Opened workspace '{candidate.name}' at {candidate}"

    def list_projects(self):
        return sorted(d.name for d in self.projects_dir.iterdir() if d.is_dir() and d.name != "temp")

    def get_current_project_path(self):
        return self.active_project_path

    def resolve_path(self, path: str = ".") -> Path:
        root = self.get_current_project_path().resolve()
        supplied = Path(path or ".").expanduser()
        candidate = supplied.resolve() if supplied.is_absolute() else (root / supplied).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise PermissionError(f"Path is outside the active workspace: {candidate}")
        return candidate

    def _history_path(self):
        if self.is_external_workspace:
            history_dir = self.active_project_path / ".ada"
            history_dir.mkdir(parents=True, exist_ok=True)
            return history_dir / "chat_history.jsonl"
        return self.active_project_path / "chat_history.jsonl"

    def log_chat(self, sender: str, text: str):
        log_file = self._history_path()
        entry = {"timestamp": time.time(), "sender": sender, "text": text}
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_project_context(self, max_file_size: int = 5000, max_total_chars: int = 16000) -> str:
        project_path = self.get_current_project_path()
        if not project_path.exists():
            return f"Workspace '{self.current_project}' does not exist."

        files = []
        for root, dirs, names in os.walk(project_path):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRECTORIES)
            for name in names:
                if name.lower() in SENSITIVE_NAMES or name.lower().endswith((".key", ".pem", ".p12")):
                    continue
                full_path = Path(root) / name
                try:
                    relative = full_path.relative_to(project_path).as_posix()
                except ValueError:
                    continue
                files.append(relative)
                if len(files) >= 500:
                    break
            if len(files) >= 500:
                break

        def priority(relative: str):
            normalized = relative.replace(chr(92), "/").lower()
            filename = Path(relative).name.lower()
            if filename in {"agents.md", "readme.md", "contributing.md"} or normalized.endswith((".uproject", ".uplugin")):
                return 0
            if normalized.startswith("config/") or filename in {"defaultengine.ini", "defaultgame.ini", "defaultinput.ini"}:
                return 1
            if normalized.startswith("source/") or "/source/" in normalized or filename.endswith((".build.cs", ".target.cs")):
                return 2
            return 3

        files.sort(key=lambda relative: (priority(relative), relative.casefold()))
        lines = [
            f"=== Active Development Workspace: {self.current_project} ===",
            f"Workspace root: {project_path}",
            f"Workspace type: {'external repository' if self.is_external_workspace else 'A.D.A managed project'}",
            f"Indexed files (up to 500): {len(files)}",
        ]
        lines.extend(f"  {name}" for name in files)
        lines.append("")
        remaining = max_total_chars
        for relative in files:
            if Path(relative).suffix.lower() not in TEXT_EXTENSIONS:
                continue
            full_path = self.resolve_path(relative)
            try:
                if full_path.stat().st_size > max_file_size:
                    continue
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue
            if not content.strip():
                continue
            section = f"--- {relative} ---\n{content}\n"
            if len(section) > remaining:
                lines.append("(Project context limit reached; use search/read tools for additional files.)")
                break
            lines.append(section)
            remaining -= len(section)
            if remaining <= 0:
                break
        return "\n".join(lines)

    def search_project(self, query: str, max_results: int = 40):
        if not query:
            return "Search query cannot be empty."
        results = []
        root = self.get_current_project_path()
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
            for name in files:
                if name.lower() in SENSITIVE_NAMES:
                    continue
                path = Path(current) / name
                if path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if query.casefold() in line.casefold():
                            results.append(f"{path.relative_to(root).as_posix()}:{number}: {line[:500]}")
                            if len(results) >= max_results:
                                return "\n".join(results)
                except (OSError, UnicodeError):
                    continue
        return "\n".join(results) if results else f"No matches found for '{query}'."

    def save_memory(self, memory_text: str):
        memory_dir = self.get_current_project_path() / ".ada"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "memory.txt").write_text(memory_text, encoding="utf-8")
        return memory_dir / "memory.txt"

    def get_memory_context(self, max_chars: int = 12000):
        memory_file = self.get_current_project_path() / ".ada" / "memory.txt"
        if not memory_file.is_file():
            return ""
        try:
            return memory_file.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError:
            return ""

    def get_recent_chat_history(self, limit: int = 16, max_chars: int = 12000):
        log_file = self._history_path()
        if not log_file.exists():
            return []
        history = []
        used_chars = 0
        try:
            with open(log_file, "r", encoding="utf-8") as handle:
                recent_lines = handle.readlines()[-limit:]
            for line in reversed(recent_lines):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                size = len(str(item.get("text", "")))
                if history and used_chars + size > max_chars:
                    break
                history.append(item)
                used_chars += size
            history.reverse()
        except OSError as exc:
            print(f"[ProjectManager] Failed to read chat history: {exc}")
        return history
