"""In-process GGUF inference for A.D.A.

The llama.cpp Python binding is loaded into the A.D.A backend itself. A.D.A
keeps one model resident at a time and unloads it before switching roles.
No llama-server process, local model HTTP server, or external model manager is
started.
"""
from __future__ import annotations

import asyncio
import gc
import importlib
import json
from pathlib import Path
from typing import Any


class ModelRuntimeError(RuntimeError):
    pass


class LocalModelRuntime:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = settings.setdefault("model_runtime", {})
        self.model: Any | None = None
        self.active_model_id: str | None = None
        self._lock = asyncio.Lock()
        self._runtime_error: str | None = None

    def registry(self) -> dict[str, Any]:
        # The project-local registry supplies installable model definitions.
        # Per-machine settings may override paths or tuning without changing
        # the shared registry file.
        registry_path = self.project_root / "models" / "registry.json"
        registered: dict[str, dict[str, Any]] = {}
        if registry_path.is_file():
            try:
                registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
                for model in registry_data.get("models", []):
                    if isinstance(model, dict) and model.get("id"):
                        registered[model["id"]] = dict(model)
            except (OSError, ValueError, TypeError):
                pass

        for model in self.config.get("models", []):
            if isinstance(model, dict) and model.get("id"):
                model_id = model["id"]
                registered[model_id] = {**registered.get(model_id, {}), **model}
        return registered

    def _resolve_path(self, value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _file_exists(self, value: Any) -> bool:
        path = self._resolve_path(value)
        return bool(path and path.is_file())

    def _runtime_status(self) -> tuple[bool, str | None, bool]:
        try:
            llama_cpp = importlib.import_module("llama_cpp")
            gpu_offload = bool(llama_cpp.llama_supports_gpu_offload())
            self._runtime_error = None if gpu_offload else "llama-cpp-python loaded, but this build has no GPU offload support."
            return True, self._runtime_error, gpu_offload
        except Exception as exc:
            self._runtime_error = f"{type(exc).__name__}: {exc}"
            return False, self._runtime_error, False

    def status(self) -> dict[str, Any]:
        models = self.registry()
        primary_id = self.config.get("primary_model_id", "")
        vision_id = self.config.get("vision_model_id", "")
        primary = models.get(primary_id, {})
        vision = models.get(vision_id, {})
        runtime_available, runtime_error, gpu_offload_supported = self._runtime_status()
        primary_configured = runtime_available and self._file_exists(primary.get("model_path"))
        vision_configured = (
            runtime_available
            and self._file_exists(vision.get("model_path"))
            and self._file_exists(vision.get("mmproj_path"))
        )
        return {
            "backend": "in-process llama-cpp-python",
            "runtime_available": runtime_available,
            "gpu_offload_supported": gpu_offload_supported,
            "runtime_error": runtime_error,
            "configured": primary_configured,
            "primary_configured": primary_configured,
            "vision_configured": vision_configured,
            "running": self.model is not None,
            "active_model_id": self.active_model_id,
            "primary_model_id": primary_id,
            "vision_model_id": vision_id,
            "models": [
                {
                    "id": model["id"],
                    "name": model.get("name", model["id"]),
                    "capabilities": model.get("capabilities", []),
                    "configured": self._file_exists(model.get("model_path")),
                    "has_mmproj": self._file_exists(model.get("mmproj_path")),
                }
                for model in models.values()
            ],
        }

    async def update_config(self, config: dict[str, Any]) -> None:
        async with self._lock:
            old = repr(self.config)
            self.config.update(config or {})
            if old != repr(self.config):
                await self._unload_model()

    def _load_model_sync(self, model_config: dict[str, Any]):
        model_id = model_config["id"]
        model_path = self._resolve_path(model_config.get("model_path"))
        if model_path is None or not model_path.is_file():
            raise ModelRuntimeError(
                f"GGUF model file is missing for '{model_config.get('name', model_id)}': {model_path}"
            )

        is_vision_model = model_id == self.config.get("vision_model_id")
        mmproj_path = model_config.get("mmproj_path")
        resolved_mmproj_path = self._resolve_path(mmproj_path)
        if is_vision_model and (resolved_mmproj_path is None or not resolved_mmproj_path.is_file()):
            raise ModelRuntimeError(
                "The selected vision model requires its matching mmproj GGUF file."
            )

        try:
            import llama_cpp
            from llama_cpp import Llama
        except Exception as exc:
            raise ModelRuntimeError(
                "The in-process llama-cpp-python runtime is unavailable. "
                "Install the CUDA-enabled package from A.D.A's requirements."
            ) from exc

        requested_gpu_layers = int(model_config.get("gpu_layers", -1))
        if requested_gpu_layers != 0 and not llama_cpp.llama_supports_gpu_offload():
            raise ModelRuntimeError(
                "This llama-cpp-python build has no GPU offload support. Install A.D.A's CUDA 13.0 wheel, "
                "or set GPU layers to 0 to explicitly use CPU inference."
            )

        chat_handler = None
        if is_vision_model:
            handler_name = str(model_config.get("chat_handler") or ("gemma4" if model_id == "gemma-4-12b" else "mtmd")).lower()
            try:
                import llama_cpp.llama_chat_format as chat_formats
                handler_classes = {
                    "gemma4": "Gemma4ChatHandler",
                    "mtmd": "MTMDChatHandler",
                    "llava15": "Llava15ChatHandler",
                    "llava16": "Llava16ChatHandler",
                    "qwen25vl": "Qwen25VLChatHandler",
                    "minicpmv26": "MiniCPMv26ChatHandler",
                    "moondream": "MoondreamChatHandler",
                }
                class_name = handler_classes.get(handler_name, handler_name)
                handler_class = getattr(chat_formats, class_name, None)
                if handler_class is None:
                    raise ModelRuntimeError(f"Unknown multimodal chat handler: {handler_name}")
                handler_args = {
                    "clip_model_path": str(resolved_mmproj_path),
                    "verbose": False,
                }
                try:
                    chat_handler = handler_class(**handler_args, use_gpu=True)
                except TypeError:
                    chat_handler = handler_class(**handler_args)
            except Exception as exc:
                raise ModelRuntimeError(
                    f"Could not initialize the {handler_name} multimodal handler: {exc}"
                ) from exc

        kwargs: dict[str, Any] = {
            "model_path": str(model_path),
            "n_gpu_layers": int(model_config.get("gpu_layers", -1)),
            "n_ctx": int(model_config.get("context_size", 32768)),
            "n_batch": int(model_config.get("batch_size", 512)),
            "verbose": False,
            "flash_attn": bool(model_config.get("flash_attn", True)) and requested_gpu_layers != 0,
            "use_mmap": True,
        }
        if model_config.get("threads"):
            kwargs["n_threads"] = int(model_config["threads"])
        if model_config.get("no_kv_offload"):
            kwargs["offload_kqv"] = False
        for cache_key, llama_key in (("cache_type_k", "type_k"), ("cache_type_v", "type_v")):
            cache_type = model_config.get(cache_key)
            if cache_type:
                constant = "GGML_TYPE_" + str(cache_type).upper()
                if not hasattr(llama_cpp, constant):
                    raise ModelRuntimeError(f"Unsupported KV cache type: {cache_type}")
                kwargs[llama_key] = getattr(llama_cpp, constant)
        if chat_handler is not None:
            kwargs["chat_handler"] = chat_handler

        try:
            instance = Llama(**kwargs)
        except Exception as exc:
            raise ModelRuntimeError(
                f"Could not load '{model_config.get('name', model_id)}' in-process: {exc}"
            ) from exc

        template_kwargs = model_config.get("chat_template_kwargs") or {}
        if template_kwargs:
            base_handler = (
                instance.chat_handler
                or instance._chat_handlers.get(instance.chat_format)
            )
            if base_handler is not None:
                def configured_handler(**call_kwargs):
                    merged = dict(template_kwargs)
                    merged.update(call_kwargs)
                    return base_handler(**merged)
                instance.chat_handler = configured_handler

        return instance

    async def _ensure_model(self, model_id: str) -> dict[str, Any]:
        model_config = self.registry().get(model_id)
        if not model_config:
            raise ModelRuntimeError(f"Model '{model_id}' is not registered.")
        if self.model is not None and self.active_model_id == model_id:
            return model_config

        await self._unload_model()
        self.model = await asyncio.to_thread(self._load_model_sync, model_config)
        self.active_model_id = model_id
        return model_config

    async def _unload_model(self) -> None:
        instance, self.model = self.model, None
        self.active_model_id = None
        if instance is not None:
            try:
                await asyncio.to_thread(instance.close)
            finally:
                del instance
                await asyncio.to_thread(gc.collect)

    async def stop(self) -> None:
        async with self._lock:
            await self._unload_model()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        model_id = model_id or self.config.get("primary_model_id")
        if not model_id:
            raise ModelRuntimeError("No primary model is selected in A.D.A. Settings.")

        async with self._lock:
            model_config = await self._ensure_model(model_id)
            request = {
                "messages": messages,
                "temperature": float(model_config.get("temperature", 0.2)),
                "top_p": float(model_config.get("top_p", 0.95)),
                "top_k": int(model_config.get("top_k", 64)),
                "max_tokens": int(max_tokens or model_config.get("max_tokens", 4096)),
                "stream": False,
            }
            if tools:
                request["tools"] = tools
                request["tool_choice"] = "auto"

            try:
                return await asyncio.to_thread(
                    self.model.create_chat_completion,
                    **request,
                )
            except Exception as exc:
                raise ModelRuntimeError(
                    f"In-process model request failed for '{model_config.get('name', model_id)}': {exc}"
                ) from exc

    async def analyze_image(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> str:
        vision_id = self.config.get("vision_model_id")
        if not vision_id:
            raise ModelRuntimeError("No vision model is selected in A.D.A. Settings.")
        import base64
        encoded = base64.b64encode(image_bytes).decode("ascii")
        result = await self.chat(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ],
            }],
            model_id=vision_id,
            max_tokens=2048,
        )
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return message.get("content", "") or ""
