"""Tests for A.D.A's client connection to the existing Unreal MCP server."""
import asyncio
import base64
from types import SimpleNamespace

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



def test_mcp_tools_are_exposed_to_k2_and_image_results_are_kept_for_gemma():
    image_data = base64.b64encode(b"editor screenshot").decode("ascii")

    class FakeSession:
        async def call_tool(self, name, arguments):
            assert name == "get_actors"
            assert arguments == {"level": "Main"}
            return SimpleNamespace(
                isError=False,
                content=[
                    SimpleNamespace(type="text", text="Found 12 actors."),
                    SimpleNamespace(type="image", data=image_data, mimeType="image/png"),
                ],
            )

    client = UnrealMCPClient()
    client.session = FakeSession()
    client._tools = {
        "unreal_get_actors": SimpleNamespace(
            name="get_actors",
            description="List actors in the open level.",
            inputSchema={"type": "object", "properties": {"level": {"type": "string"}}},
        )
    }
    client._public_names = {"unreal_get_actors": "get_actors"}

    async def scenario():
        tools = await client.openai_tools()
        result = await client.call_tool("unreal_get_actors", {"level": "Main"})
        return tools, result

    tools, result = asyncio.run(scenario())

    assert tools[0]["function"]["name"] == "unreal_get_actors"
    assert tools[0]["function"]["parameters"]["properties"]["level"]["type"] == "string"
    assert "Found 12 actors." in result
    assert client.latest_image == (b"editor screenshot", "image/png")
