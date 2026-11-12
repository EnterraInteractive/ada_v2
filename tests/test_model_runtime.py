"""Tests for the embedded llama-cpp-python runtime and model handoff."""
import asyncio
import base64

import pytest

from model_runtime import LocalModelRuntime, ModelRuntimeError


class FakeLlama:
    def __init__(self, model_id, calls, closed):
        self.model_id = model_id
        self.calls = calls
        self.closed = closed

    def create_chat_completion(self, **kwargs):
        self.calls.append((self.model_id, kwargs))
        return {"choices": [{"message": {"content": f"response from {self.model_id}"}}]}

    def close(self):
        self.closed.append(self.model_id)


def make_runtime(tmp_path):
    primary = tmp_path / "k2.gguf"
    vision = tmp_path / "gemma.gguf"
    mmproj = tmp_path / "gemma-mmproj.gguf"
    for path in (primary, vision, mmproj):
        path.write_bytes(b"test")
    settings = {"model_runtime": {
        "primary_model_id": "k2",
        "vision_model_id": "gemma",
        "models": [
            {"id": "k2", "name": "K2-Horizon 7B", "model_path": str(primary),
             "capabilities": ["chat", "coding", "tools"], "context_size": 65536,
             "gpu_layers": 99, "max_tokens": 32768, "cache_type_k": "q8_0",
             "cache_type_v": "q8_0", "no_kv_offload": True,
             "chat_template_kwargs": {"reasoning_effort": "high", "tool_call_format": "json"}},
            {"id": "gemma", "name": "Gemma 4 12B", "model_path": str(vision),
             "mmproj_path": str(mmproj), "chat_handler": "gemma4",
             "capabilities": ["vision"], "context_size": 8192, "gpu_layers": 99},
        ],
    }}
    runtime = LocalModelRuntime(settings)
    calls = []
    closed = []
    runtime._load_model_sync = lambda model: FakeLlama(model["id"], calls, closed)
    return runtime, calls, closed


def test_runtime_is_embedded_and_does_not_require_a_server_executable():
    runtime = LocalModelRuntime({"model_runtime": {
        "primary_model_id": "k2",
        "models": [{"id": "k2", "model_path": "C:/models/k2.gguf"}],
    }})
    assert runtime.status()["backend"] == "in-process llama-cpp-python"
    assert "process" not in runtime.__dict__


def test_vision_model_requires_a_matching_projector(tmp_path):
    model_path = tmp_path / "gemma.gguf"
    model_path.write_bytes(b"test")
    runtime = LocalModelRuntime({"model_runtime": {"vision_model_id": "gemma"}})
    with pytest.raises(ModelRuntimeError, match="mmproj"):
        runtime._load_model_sync({"id": "gemma", "model_path": str(model_path)})


def test_switching_roles_unloads_the_previous_model_and_returns_vision_findings(tmp_path):
    runtime, calls, closed = make_runtime(tmp_path)

    async def scenario():
        primary = await runtime.chat([{"role": "user", "content": "Inspect the Unreal project."}])
        assert primary["choices"][0]["message"]["content"] == "response from k2"
        assert runtime.active_model_id == "k2"

        vision = await runtime.analyze_image("Describe this editor screenshot.", b"image-bytes", "image/png")
        assert vision == "response from gemma"
        assert runtime.active_model_id == "gemma"

    asyncio.run(scenario())

    assert closed == ["k2"]
    assert [model_id for model_id, _ in calls] == ["k2", "gemma"]
    vision_messages = calls[1][1]["messages"]
    image_part = vision_messages[0]["content"][1]
    assert image_part["type"] == "image_url"
    encoded = image_part["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(encoded) == b"image-bytes"


def test_primary_model_receives_tool_schemas_and_k2_generation_settings(tmp_path):
    runtime, calls, _closed = make_runtime(tmp_path)
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]

    asyncio.run(runtime.chat([{"role": "user", "content": "Read the file."}], tools=tools))

    _model_id, request = calls[0]
    assert request["tools"] == tools
    assert request["tool_choice"] == "auto"
    assert request["max_tokens"] == 32768
