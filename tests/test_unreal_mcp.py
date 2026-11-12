"""Tests for A.D.A's client connection to the existing Unreal MCP server."""
import asyncio

from unreal_mcp import UnrealMCPClient


def test_unreal_mcp_defaults_to_the_existing_local_editor_endpoint():
    client = UnrealMCPClient()
    status = client.status()

    assert status["url"] == "http://127.0.0.1:8000/mcp"
    assert status["enabled"] is True
    assert status["connected"] is False


def test_disabled_unreal_mcp_does_not_start_a_connection():
    client = UnrealMCPClient({"enabled": False})
    assert asyncio.run(client.openai_tools()) == []
    assert client.status()["connected"] is False


def test_unreal_mcp_tools_are_not_called_when_integration_is_disabled():
    client = UnrealMCPClient({"enabled": False})
    result = asyncio.run(client.call_tool("unreal_get_actors", {}))
    assert result.startswith("Unreal MCP is unavailable:")


def test_unreal_mcp_rejects_remote_plain_http_without_network_access():
    client = UnrealMCPClient({"url": "http://example.com/mcp"})
    connected = asyncio.run(client.connect())

    assert connected is False
    assert "local HTTP" in client.last_error
