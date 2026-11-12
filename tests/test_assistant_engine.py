"""Tests for the local development assistant's K2 tool-call adapter."""
import json

from assistant_engine import AssistantEngine, TOOLS


def test_local_tool_registry_exposes_development_capabilities():
    names = {item["function"]["name"] for item in TOOLS}
    assert {
        "read_file",
        "read_directory",
        "search_project",
        "write_file",
        "run_terminal_command",
        "analyze_image",
        "browser_navigate",
        "browser_read_page",
        "create_project",
        "switch_project",
    }.issubset(names)


def test_parse_k2_xml_json_tool_call():
    content = '<tool_call>{"name":"read_file","arguments":{"path":"Source/Game.cpp"}}</tool_call>'
    calls, visible = AssistantEngine._parse_native_tool_calls(content)

    assert visible == ""
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "Source/Game.cpp"}


def test_parse_k2_raw_json_tool_call():
    content = '{"name":"browser_navigate","arguments":{"url":"https://example.com"}}'
    calls, visible = AssistantEngine._parse_native_tool_calls(content)

    assert visible == ""
    assert calls[0]["function"]["name"] == "browser_navigate"
    assert json.loads(calls[0]["function"]["arguments"])["url"] == "https://example.com"


def test_normal_assistant_text_is_not_misread_as_a_tool_call():
    content = "I inspected the project and found three modules."
    calls, visible = AssistantEngine._parse_native_tool_calls(content)

    assert calls == []
    assert visible == content



def test_tool_confirmation_is_bound_to_the_requesting_socket_session():
    import asyncio

    captured = {}

    async def confirm(session_id, tool_name, arguments):
        captured.update(session_id=session_id, tool=tool_name, arguments=arguments)
        return True

    engine = AssistantEngine(
        runtime=None,
        project_manager=None,
        permissions={"unreal_mcp": True},
        confirmation_callback=confirm,
    )
    approved = asyncio.run(engine._confirm(
        "socket-session-1",
        "unreal_get_actors",
        {"level": "Main"},
        "unreal_mcp",
    ))

    assert approved is True
    assert captured == {
        "session_id": "socket-session-1",
        "tool": "unreal_get_actors",
        "arguments": {"level": "Main"},
    }


def test_tool_confirmation_fails_closed_without_a_socket_session():
    import asyncio

    async def confirm(*_args):
        raise AssertionError("Confirmation must not be requested without a session.")

    engine = AssistantEngine(
        runtime=None,
        project_manager=None,
        permissions={"run_terminal_command": True},
        confirmation_callback=confirm,
    )
    assert asyncio.run(engine._confirm(None, "run_terminal_command", {"command": "pwd"})) is False
