"""MCP client for the user's running Unreal Editor integration.

A.D.A is an MCP client only. It connects to the Unreal MCP endpoint; it does
not create another MCP server or launch another assistant application.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from urllib.parse import urlparse
from contextlib import AsyncExitStack
from typing import Any


class UnrealMCPClient:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.session = None
        self._stack: AsyncExitStack | None = None
        self._tools: dict[str, Any] = {}
        self._public_names: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.last_error: str | None = None
        self.latest_image: tuple[bytes, str] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.get("enabled", True)),
            "connected": self.session is not None,
            "url": self.config.get("url", "http://127.0.0.1:8000/mcp"),
            "tool_count": len(self._tools),
            "tools": list(self._public_names),
            "error": self.last_error,
        }

    async def _close_locked(self) -> None:
        stack, self._stack = self._stack, None
        self.session = None
        self._tools.clear()
        self._public_names.clear()
        self.latest_image = None
        if stack:
            await stack.aclose()

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def update_config(self, config: dict[str, Any]) -> None:
        async with self._lock:
            self.config.update(config or {})
            await self._close_locked()
            self.last_error = None

    async def _connect_locked(self) -> bool:
        if not self.config.get("enabled", True):
            return False
        if self.session is not None:
            return True

        url = str(self.config.get("url", "http://127.0.0.1:8000/mcp")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}):
            self.last_error = "Unreal MCP must use a local HTTP endpoint or an HTTPS endpoint."
            return False

        if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            try:
                _reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(parsed.hostname, parsed.port or 80),
                    timeout=0.5,
                )
                writer.close()
                await writer.wait_closed()
            except Exception as exc:
                self.last_error = f"Unreal MCP endpoint is not available at {url}: {exc}"
                return False

        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            # The v1 SDK API is pinned in requirements.txt for a stable transport contract.
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            read_stream, write_stream, _get_session_id = await stack.enter_async_context(
                streamablehttp_client(url)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            response = await session.list_tools()

            tools: dict[str, Any] = {}
            public_names: dict[str, str] = {}
            for tool in response.tools:
                public_name = "unreal_" + re.sub(r"[^a-zA-Z0-9_-]", "_", tool.name)
                tools[public_name] = tool
                public_names[public_name] = tool.name

            self._stack = stack
            self.session = session
            self._tools = tools
            self._public_names = public_names
            self.last_error = None
            return True
        except Exception as exc:
            await stack.aclose()
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    async def connect(self) -> bool:
        async with self._lock:
            return await self._connect_locked()

    async def openai_tools(self) -> list[dict[str, Any]]:
        async with self._lock:
            if not await self._connect_locked():
                return []
            result = []
            for public_name, tool in self._tools.items():
                schema = getattr(tool, "inputSchema", None) or {
                    "type": "object",
                    "properties": {},
                }
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    schema = {"type": "object", "properties": {}}
                result.append({
                    "type": "function",
                    "function": {
                        "name": public_name,
                        "description": (getattr(tool, "description", None) or f"Use the Unreal Editor tool {tool.name}."),
                        "parameters": schema,
                    },
                })
            return result

    def is_read_only(self, public_name: str) -> bool:
        tool = self._tools.get(public_name)
        annotations = getattr(tool, "annotations", None) if tool else None
        if isinstance(annotations, dict):
            return bool(annotations.get("readOnlyHint", annotations.get("read_only_hint", False)))
        return bool(getattr(annotations, "readOnlyHint", False))

    async def call_tool(self, public_name: str, arguments: dict[str, Any]) -> str:
        async with self._lock:
            if not await self._connect_locked():
                return f"Unreal MCP is unavailable: {self.last_error or 'not connected'}"
            actual_name = self._public_names.get(public_name)
            if not actual_name:
                return f"Unknown Unreal MCP tool: {public_name}"
            try:
                result = await self.session.call_tool(actual_name, arguments)
                parts = []
                for item in getattr(result, "content", []) or []:
                    if getattr(item, "type", "") == "text":
                        parts.append(getattr(item, "text", ""))
                    elif getattr(item, "type", "") == "image":
                        raw = getattr(item, "data", "")
                        mime_type = getattr(item, "mimeType", "image/png") or "image/png"
                        try:
                            image_bytes = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
                            self.latest_image = (image_bytes, mime_type)
                            parts.append("Unreal Editor returned an image. It is available to analyze_image with source='editor'.")
                        except Exception:
                            parts.append("Unreal Editor returned an image that A.D.A could not decode.")
                    else:
                        parts.append(str(item))
                body = "\n".join(part for part in parts if part)
                if len(body) > 40000:
                    body = body[:40000] + "\n[Unreal MCP output truncated at 40,000 characters.]"
                if getattr(result, "isError", False):
                    return "Unreal MCP tool reported an error:\n" + (body or "No error details were returned.")
                return body or "Unreal MCP tool completed without text output."
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                await self._close_locked()
                return f"Unreal MCP call failed: {self.last_error}"
