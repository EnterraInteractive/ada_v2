"""Project-local outbound connection audit used by the Wi-Fi-off verification drill."""
from __future__ import annotations

import json
import socket
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_INSTALLED = False
_LOG_PATH: Path | None = None
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def _reason() -> str:
    for frame in reversed(traceback.extract_stack(limit=18)[:-2]):
        name = Path(frame.filename).name
        if name not in {"network_audit.py", "socket.py", "http", "client.py"}:
            return f"{name}:{frame.name}"
    return "unknown"


def _write(event: dict[str, Any]) -> None:
    if _LOG_PATH is None:
        return
    record = {"time": datetime.now(timezone.utc).isoformat(), **event}
    with _LOCK:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def install(project_root: str | Path) -> Path:
    global _INSTALLED, _LOG_PATH
    _LOG_PATH = Path(project_root).resolve() / ".ada" / "network-audit.jsonl"
    if _INSTALLED:
        return _LOG_PATH

    def audited_connect(sock, address):
        host = address[0] if isinstance(address, tuple) and address else str(address)
        port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
        _write({"kind": "server_socket", "host": str(host), "port": port, "reason": _reason()})
        return _ORIGINAL_CONNECT(sock, address)

    def audited_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, all_errors=False):
        host = address[0] if isinstance(address, tuple) and address else str(address)
        port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
        _write({"kind": "server_http_connection", "host": str(host), "port": port, "reason": _reason()})
        return _ORIGINAL_CREATE_CONNECTION(address, timeout, source_address, all_errors=all_errors)

    socket.socket.connect = audited_connect
    socket.create_connection = audited_create_connection
    _INSTALLED = True
    return _LOG_PATH


def record_browser_resources(hosts: list[str]) -> int:
    count = 0
    for host in hosts[:500]:
        if not isinstance(host, str) or not host.strip():
            continue
        _write({"kind": "browser_resource", "host": host.strip(), "reason": "browser Performance Resource Timing"})
        count += 1
    return count


def read_events() -> list[dict[str, Any]]:
    if _LOG_PATH is None or not _LOG_PATH.is_file():
        return []
    events = []
    for line in _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        except ValueError:
            continue
    return events


def clear_events() -> None:
    if _LOG_PATH is not None:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_PATH.write_text("", encoding="utf-8")
