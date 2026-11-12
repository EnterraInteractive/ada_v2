import sys
import asyncio
import copy

# Fix for asyncio subprocess support on Windows
# MUST BE SET BEFORE OTHER IMPORTS
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import socketio
import uvicorn
from fastapi import FastAPI
import asyncio
import threading
import sys
import os
import json
import base64
import uuid
from datetime import datetime
from pathlib import Path



# Ensure we can sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from authenticator import FaceAuthenticator
from model_runtime import LocalModelRuntime
from assistant_engine import AssistantEngine
from project_manager import ProjectManager
from web_agent import WebAgent
from voice_service import LocalVoiceService
from unreal_mcp import UnrealMCPClient

# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
app_socketio = socketio.ASGIApp(sio, app)

import signal

# --- SHUTDOWN HANDLER ---
def signal_handler(sig, frame):
    print(f"\n[SERVER] Caught signal {sig}. Exiting gracefully...")
    # Stop the local voice capture thread before the backend exits.
    if voice_service:
        voice_service.stop_event.set()
    # Stop the managed local inference child process before the backend exits.
    if model_runtime.process and model_runtime.process.poll() is None:
        try:
            model_runtime.process.terminate()
        except Exception:
            pass
    # Force kill
    print("[SERVER] Force exiting...")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Global state
voice_service = None
authenticator = None
SETTINGS_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = str(SETTINGS_DIR / "settings.local.json")
SETTINGS_TEMPLATE_FILE = str(SETTINGS_DIR / "settings.json")

DEFAULT_SETTINGS = {
    "face_auth_enabled": False, # Default OFF as requested
    "tool_permissions": {
        "write_file": True,
        "read_directory": True,
        "read_file": True,
        "create_project": True,
        "switch_project": True,
        "list_projects": True,
        "browser_navigate": True,
        "browser_click": True,
        "browser_type": True,
        "browser_press": True,
        "browser_read_page": False,
        "browser_screenshot": False,
        "browser_wait": False,
        "browser_close": True,
        "search_project": False,
        "run_terminal_command": True,
        "analyze_image": False,
        "unreal_mcp": True,
        "unreal_mcp_readonly": False
    },
    "camera_flipped": False,
    "workspace_path": "E:\\Unreal Projects\\EnterraOnline",
    "unreal_mcp": {"enabled": True, "url": "http://127.0.0.1:8000/mcp"},
    "model_runtime": {
        "primary_model_id": "k2-horizon-7b",
        "vision_model_id": "gemma-4-12b",
        "models": [
            {"id": "k2-horizon-7b", "name": "K2-Horizon 7B", "model_path": "models/language/k2-horizon-7b/model.gguf", "capabilities": ["chat", "coding", "reasoning", "tools"], "context_size": 65536, "gpu_layers": 99, "max_tokens": 32768, "cache_type_k": "q8_0", "cache_type_v": "q8_0", "no_kv_offload": true, "temperature": 1.0, "top_p": 0.95, "top_k": 64, "chat_template_kwargs": {"reasoning_effort": "high", "tool_call_format": "json"}},
            {"id": "gemma-4-12b", "name": "Gemma 4 12B Vision", "model_path": "models/vision/gemma-4-12b/model.gguf", "mmproj_path": "models/vision/gemma-4-12b/mmproj.gguf", "chat_handler": "gemma4", "chat_template_kwargs": {"enable_thinking": true}, "capabilities": ["vision"], "context_size": 8192, "gpu_layers": 99, "max_tokens": 2048, "temperature": 1.0, "top_p": 0.95, "top_k": 64}
        ]
    },
    "voice": {"provider": "gemini_api", "enabled": False, "api_key_env": "GEMINI_API_KEY"}
}

SETTINGS = copy.deepcopy(DEFAULT_SETTINGS)

def load_settings():
    global SETTINGS
    source_file = SETTINGS_FILE if os.path.exists(SETTINGS_FILE) else SETTINGS_TEMPLATE_FILE
    if os.path.exists(source_file):
        try:
            with open(source_file, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new keys exist
                # Deep merge for tool_permissions would be better but shallow merge of top keys + tool_permissions check is okay for now
                for k, v in loaded.items():
                    if k == "tool_permissions" and isinstance(v, dict):
                         SETTINGS["tool_permissions"].update(v)
                    elif k == "unreal_mcp" and isinstance(v, dict):
                         SETTINGS["unreal_mcp"].update(v)
                    elif k == "model_runtime" and isinstance(v, dict):
                         runtime_values = dict(v)
                         if isinstance(v.get("models"), list):
                             default_models = {
                                 model["id"]: model
                                 for model in DEFAULT_SETTINGS["model_runtime"]["models"]
                             }
                             merged_models = []
                             for model in v["models"]:
                                 defaults = default_models.get(model.get("id"), {}).copy()
                                 defaults.update(model)
                                 if model.get("id") == "k2-horizon-7b" and not model.get("cache_type_k"):
                                     k2_defaults = default_models.get("k2-horizon-7b", {})
                                     for key in ("context_size", "max_tokens", "cache_type_k", "cache_type_v"):
                                         defaults[key] = k2_defaults[key]
                                 merged_models.append(defaults)
                             runtime_values["models"] = merged_models
                         SETTINGS["model_runtime"].update(runtime_values)
                         for legacy_key in ("executable", "host", "port", "startup_timeout_seconds"):
                             SETTINGS["model_runtime"].pop(legacy_key, None)
                    elif k == "voice" and isinstance(v, dict):
                        # Migrate legacy local Whisper/OS-TTS settings to the
                        # selected Gemini API provider. Never silently fall
                        # back to local voice when the old settings file loads.
                        if v.get("provider") == "gemini_api":
                            SETTINGS["voice"].update(v)
                        else:
                            SETTINGS["voice"] = copy.deepcopy(DEFAULT_SETTINGS["voice"])
                    else:
                        SETTINGS[k] = v
            if not SETTINGS.get("workspace_path") and Path("E:/Unreal Projects/EnterraOnline").is_dir():
                SETTINGS["workspace_path"] = "E:/Unreal Projects/EnterraOnline"
            print(f"Loaded settings from {source_file}")
        except Exception as e:
            print(f"Error loading settings: {e}")

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(SETTINGS, f, indent=4)
        print("Settings saved.")
    except Exception as e:
        print(f"Error saving settings: {e}")

# Load on startup. Create a per-machine settings file from the tracked defaults once.
load_settings()
if not os.path.exists(SETTINGS_FILE):
    save_settings()

authenticator = None
PROJECT_ROOT = Path(__file__).resolve().parent.parent
project_manager = ProjectManager(str(PROJECT_ROOT))
model_runtime = LocalModelRuntime(SETTINGS)
assistant_engine = None
browser_agent = None
unreal_mcp_client = None
latest_uploaded_image = None
latest_camera_image = None
latest_image_name = None
pending_tool_confirmations = {}

def get_latest_image(source='latest'):
    if source == 'camera':
        return latest_camera_image
    if source == 'attachment':
        return latest_uploaded_image
    if source == 'editor':
        return unreal_mcp_client.latest_image if unreal_mcp_client else None
    return latest_uploaded_image or latest_camera_image or (unreal_mcp_client.latest_image if unreal_mcp_client else None)
# tool_permissions is now SETTINGS["tool_permissions"]

@app.on_event("startup")
async def startup_event():
    global assistant_engine, browser_agent, unreal_mcp_client
    print("[SERVER] A.D.A backend starting")
    workspace = SETTINGS.get("workspace_path")
    if workspace:
        try:
            success, message = project_manager.open_workspace(workspace)
            print(f"[SERVER] {message}")
            if not success:
                SETTINGS["workspace_path"] = ""
        except (OSError, ValueError) as exc:
            print(f"[SERVER] Saved workspace could not be opened: {exc}")
            SETTINGS["workspace_path"] = ""

    async def send_engine_event(event, payload):
        await sio.emit(event, payload)

    async def browser_update(payload):
        await sio.emit("browser_frame", payload)

    browser_agent = WebAgent(on_update=browser_update)
    unreal_mcp_client = UnrealMCPClient(SETTINGS.get("unreal_mcp", {}))
    print(f"[SERVER] Unreal MCP client configured: {unreal_mcp_client.status()} (connects lazily when needed)")
    assistant_engine = AssistantEngine(
        runtime=model_runtime,
        project_manager=project_manager,
        permissions=SETTINGS.get("tool_permissions", {}),
        confirmation_callback=request_tool_confirmation,
        image_callback=get_latest_image,
        web_agent=browser_agent,
        unreal_mcp=unreal_mcp_client,
        response_callback=send_engine_event,
    )


@app.get("/status")
async def status():
    return {"status": "running", "service": "A.D.A Backend", "backend_port": 8001, "models": model_runtime.status(), "unreal_mcp": unreal_mcp_client.status() if unreal_mcp_client else {"connected": False}}

async def request_tool_confirmation(sid, tool_name, arguments):
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    pending_tool_confirmations[request_id] = future
    await sio.emit("tool_confirmation_request", {
        "id": request_id,
        "tool": tool_name,
        "args": arguments,
    }, room=sid)
    try:
        return await asyncio.wait_for(future, timeout=120)
    except asyncio.TimeoutError:
        return False
    finally:
        pending_tool_confirmations.pop(request_id, None)


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('status', {'msg': 'Connected to A.D.A Backend'}, room=sid)
    await sio.emit('model_status', model_runtime.status(), room=sid)
    if unreal_mcp_client:
        await sio.emit('unreal_mcp_status', unreal_mcp_client.status(), room=sid)
    await sio.emit('workspace_status', {
        'name': project_manager.current_project,
        'path': str(project_manager.get_current_project_path())
    }, room=sid)

    global authenticator
    
    # Callback for Auth Status
    async def on_auth_status(is_auth):
        print(f"[SERVER] Auth status change: {is_auth}")
        await sio.emit('auth_status', {'authenticated': is_auth})

    # Callback for Auth Camera Frames
    async def on_auth_frame(frame_b64):
        await sio.emit('auth_frame', {'image': frame_b64})

    # Initialize Authenticator if not already done
    if authenticator is None:
        authenticator = FaceAuthenticator(
            reference_image_path="reference.jpg",
            on_status_change=on_auth_status,
            on_frame=on_auth_frame
        )
    
    # Check if already authenticated or needs to start
    if authenticator.authenticated:
        await sio.emit('auth_status', {'authenticated': True})
    else:
        # Check Settings for Auth
        if SETTINGS.get("face_auth_enabled", False):
            await sio.emit('auth_status', {'authenticated': False})
            # Start the auth loop in background
            asyncio.create_task(authenticator.start_authentication_loop())
        else:
            # Bypass Auth
            print("Face Auth Disabled. Auto-authenticating.")
            # We don't change authenticator state to true to avoid confusion if re-enabled? 
            # Or we should just tell client it's auth'd.
            await sio.emit('auth_status', {'authenticated': True})

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def start_audio(sid, data=None):
    global voice_service

    if SETTINGS.get("face_auth_enabled", False) and authenticator and not authenticator.authenticated:
        await sio.emit("error", {"msg": "Authentication Required"}, room=sid)
        return

    voice_config = SETTINGS.get("voice", {})
    if voice_config.get("provider", "gemini_api") == "gemini_api":
        if not voice_config.get("enabled", False):
            await sio.emit("error", {"msg": "Gemini API voice is selected but disabled. Configure the Gemini API key and enable voice after the API adapter is installed."}, room=sid)
            return
        await sio.emit("error", {"msg": "Gemini API voice is selected. The remote voice transport still needs to be connected; local voice fallback is intentionally disabled."}, room=sid)
        return

    if voice_service and voice_service.started:
        await sio.emit("status", {"msg": "Local voice is already running."}, room=sid)
        return

    device_name = (data or {}).get("device_name")
    await sio.emit("status", {"msg": "Loading local speech recognition model..."}, room=sid)

    async def on_speech(recognized_text):
        await sio.emit("transcription", {"sender": "You", "text": recognized_text}, room=sid)
        if not assistant_engine:
            await sio.emit("error", {"msg": "Local assistant engine is not initialized."}, room=sid)
            return
        await sio.emit("assistant_status", {"state": "thinking"}, room=sid)
        try:
            answer = await assistant_engine.respond(recognized_text, session_id=sid)
            await sio.emit("transcription", {"sender": "ADA", "text": answer}, room=sid)
            if voice_service:
                voice_service.speak(answer)
            await sio.emit("assistant_status", {"state": "idle"}, room=sid)
        except Exception as exc:
            await sio.emit("error", {"msg": f"Voice request failed: {exc}"}, room=sid)
            await sio.emit("assistant_status", {"state": "error"}, room=sid)

    async def on_voice_status(payload):
        await sio.emit("status", payload, room=sid)

    async def on_voice_error(payload):
        global voice_service
        await sio.emit("error", payload, room=sid)
        if str((payload or {}).get("msg", "")).startswith("Microphone error") and voice_service:
            failed_service = voice_service
            await failed_service.stop()
            voice_service = None

    try:
        voice_service = LocalVoiceService(
            on_speech=on_speech,
            on_status=on_voice_status,
            on_error=on_voice_error,
            device_name=device_name,
            model_size=voice_config.get("model_size", "base.en"),
            vad_aggressiveness=voice_config.get("vad_aggressiveness", 2),
        )
        await voice_service.start()
        await sio.emit("status", {"msg": "A.D.A Started"})
    except Exception as exc:
        print(f"[VOICE] Failed to start local voice: {type(exc).__name__}: {exc}")
        voice_service = None
        await sio.emit("error", {"msg": f"Local voice could not start: {exc}"}, room=sid)


@sio.event
async def stop_audio(sid):
    global voice_service
    if voice_service:
        await voice_service.stop()
        voice_service = None
    await sio.emit("status", {"msg": "A.D.A Stopped"}, room=sid)


@sio.event
async def pause_audio(sid):
    if voice_service and voice_service.started:
        voice_service.pause()
        await sio.emit("status", {"msg": "Audio Paused"}, room=sid)


@sio.event
async def resume_audio(sid):
    if voice_service and voice_service.started:
        voice_service.resume()
        await sio.emit("status", {"msg": "Audio Resumed"}, room=sid)


@sio.event
async def confirm_tool(sid, data):
    # data: { "id": "...", "confirmed": True/False }
    request_id = data.get('id')
    confirmed = data.get('confirmed', False)
    
    print(f"[SERVER DEBUG] Received confirmation response for {request_id}: {confirmed}")
    
    pending = pending_tool_confirmations.get(request_id)
    if pending and not pending.done():
        pending.set_result(confirmed)
        return
    print("No pending confirmation found for request.")

@sio.event
async def shutdown(sid, data=None):
    """Gracefully shutdown the server when the application closes."""
    global voice_service, authenticator
    
    print("[SERVER] ========================================")
    print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
    print("[SERVER] ========================================")
    
    # Stop local microphone capture and speech output.
    if voice_service:
        await voice_service.stop()
        voice_service = None

    # Close browser resources and stop the managed local inference process.
    if browser_agent:
        await browser_agent.close()
    await model_runtime.stop()
    if unreal_mcp_client:
        await unreal_mcp_client.close()

    # Stop authenticator if running
    if authenticator:
        print("[SERVER] Stopping Authenticator...")
        authenticator.stop()
    
    print("[SERVER] Graceful shutdown complete. Terminating process...")
    
    # Force exit immediately - os._exit bypasses cleanup but ensures termination
    os._exit(0)

@sio.event
async def user_input(sid, data):
    text = (data or {}).get("text", "").strip()
    if not text:
        return
    if not assistant_engine:
        await sio.emit("error", {"msg": "The local assistant engine is not initialized."}, room=sid)
        return

    await sio.emit("assistant_status", {"state": "thinking"}, room=sid)
    try:
        answer = await assistant_engine.respond(text, session_id=sid)
        await sio.emit("transcription", {"sender": "ADA", "text": answer}, room=sid)
        await sio.emit("assistant_status", {"state": "idle"}, room=sid)
    except Exception as exc:
        print(f"[ASSISTANT] Request failed: {type(exc).__name__}: {exc}")
        await sio.emit("error", {"msg": str(exc)}, room=sid)
        await sio.emit("assistant_status", {"state": "error"}, room=sid)

@sio.event
async def video_frame(sid, data):
    global latest_camera_image
    image_data = (data or {}).get("image")
    if not image_data:
        return
    try:
        if isinstance(image_data, dict):
            raw = image_data.get("data", "")
            mime_type = image_data.get("mime_type", "image/jpeg")
            latest_camera_image = (base64.b64decode(raw), mime_type) if isinstance(raw, str) else (bytes(raw), mime_type)
        elif isinstance(image_data, (bytes, bytearray)):
            latest_camera_image = (bytes(image_data), "image/jpeg")
        elif isinstance(image_data, str):
            latest_camera_image = (base64.b64decode(image_data), "image/jpeg")
    except Exception as exc:
        print(f"[VISION] Could not store incoming image frame: {exc}")


@sio.event
async def image_upload(sid, data):
    global latest_uploaded_image, latest_image_name
    payload = data or {}
    encoded = payload.get("data", "")
    mime_type = payload.get("mime_type", "image/jpeg")
    name = payload.get("name", "image")
    supported_image_types = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
    if not isinstance(encoded, str) or mime_type not in supported_image_types:
        await sio.emit("error", {"msg": "Unsupported image attachment. Use JPEG, PNG, WEBP, GIF, or BMP."}, room=sid)
        return
    if len(encoded) > 28 * 1024 * 1024:
        await sio.emit("error", {"msg": "Image attachments must be 20 MB or smaller."}, room=sid)
        return
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
        if len(image_bytes) > 20 * 1024 * 1024:
            raise ValueError("Image attachments must be 20 MB or smaller.")
        latest_uploaded_image = (image_bytes, mime_type)
        latest_image_name = name
        await sio.emit("image_attached", {"name": name, "size": len(image_bytes)}, room=sid)
    except Exception as exc:
        await sio.emit("error", {"msg": f"Could not attach image: {exc}"}, room=sid)


@sio.event
async def save_memory(sid, data):
    try:
        messages = (data or {}).get("messages", [])
        if not messages:
            return
        memory_text = "\n".join(
            f"[{item.get('sender', 'Unknown')}]: {item.get('text', '')}"
            for item in messages
        )
        path = project_manager.save_memory(memory_text)
        await sio.emit("status", {"msg": f"Memory saved to {path.name}."}, room=sid)
    except Exception as exc:
        await sio.emit("error", {"msg": f"Failed to save memory: {exc}"}, room=sid)


@sio.event
async def upload_memory(sid, data):
    memory_text = (data or {}).get("memory", "")
    if not memory_text.strip():
        await sio.emit("error", {"msg": "No memory data provided."}, room=sid)
        return
    try:
        path = project_manager.save_memory(memory_text)
        await sio.emit("status", {"msg": f"Memory loaded from {path.name} into the active workspace."}, room=sid)
    except Exception as exc:
        await sio.emit("error", {"msg": f"Failed to load memory: {exc}"}, room=sid)


@sio.event
async def prompt_web_agent(sid, data):
    prompt = (data or {}).get("prompt", "").strip()
    if not prompt:
        return
    if not assistant_engine:
        await sio.emit("error", {"msg": "Local assistant engine is not initialized."}, room=sid)
        return
    await sio.emit("transcription", {"sender": "You", "text": prompt}, room=sid)
    try:
        answer = await assistant_engine.respond(
            "Use the browser tools to complete this request. Verify each action in the browser and report the result: " + prompt,
            session_id=sid,
        )
        await sio.emit("transcription", {"sender": "ADA", "text": answer}, room=sid)
    except Exception as exc:
        await sio.emit("error", {"msg": f"Browser Error: {exc}"}, room=sid)

@sio.event
async def get_chat_history(sid):
    history = project_manager.get_recent_chat_history(limit=200)
    messages = []
    for entry in history:
        sender = entry.get("sender", "Unknown")
        messages.append({
            "sender": "You" if sender.lower() in {"user", "you"} else sender,
            "text": entry.get("text", ""),
            "time": datetime.fromtimestamp(entry.get("timestamp", 0)).strftime("%H:%M:%S") if entry.get("timestamp") else "",
        })
    await sio.emit("chat_history", {"messages": messages}, room=sid)


@sio.event
async def get_model_status(sid):
    await sio.emit("model_status", model_runtime.status(), room=sid)
    if unreal_mcp_client:
        await sio.emit("unreal_mcp_status", unreal_mcp_client.status(), room=sid)


@sio.event
async def get_unreal_mcp_status(sid):
    await sio.emit("unreal_mcp_status", unreal_mcp_client.status() if unreal_mcp_client else {"connected": False}, room=sid)

@sio.event
async def reconnect_unreal_mcp(sid):
    if not unreal_mcp_client:
        await sio.emit("unreal_mcp_status", {"connected": False, "error": "Unreal MCP client is not initialized."}, room=sid)
        return
    await unreal_mcp_client.close()
    connected = await unreal_mcp_client.connect()
    await sio.emit("unreal_mcp_status", unreal_mcp_client.status(), room=sid)
    if not connected:
        await sio.emit("error", {"msg": "Unreal MCP connection failed: " + str(unreal_mcp_client.last_error)}, room=sid)

@sio.event
async def get_settings(sid):
    await sio.emit('settings', SETTINGS)

@sio.event
async def update_settings(sid, data):
    # Generic update
    print(f"Updating settings: {data}")
    
    # Handle specific keys if needed
    if "tool_permissions" in data:
        SETTINGS["tool_permissions"].update(data["tool_permissions"])

    if "face_auth_enabled" in data:
        SETTINGS["face_auth_enabled"] = data["face_auth_enabled"]
        # If turned OFF, maybe emit auth status true?
        if not data["face_auth_enabled"]:
             await sio.emit('auth_status', {'authenticated': True})
             # Stop auth loop if running?
             if authenticator:
                 authenticator.stop() 

    if "voice" in data and isinstance(data["voice"], dict):
        SETTINGS["voice"] = {**SETTINGS.get("voice", {}), **data["voice"]}

    if "camera_flipped" in data:
        SETTINGS["camera_flipped"] = data["camera_flipped"]
        print(f"[SERVER] Camera flip set to: {data['camera_flipped']}")

    if "workspace_path" in data:
        candidate = str(data["workspace_path"]).strip()
        if candidate:
            try:
                success, message = project_manager.open_workspace(candidate)
                if not success:
                    raise ValueError(message)
            except Exception as exc:
                await sio.emit("error", {"msg": f"Could not open workspace: {exc}"}, room=sid)
                return
        SETTINGS["workspace_path"] = candidate
        await sio.emit("workspace_status", {
            "name": project_manager.current_project,
            "path": str(project_manager.get_current_project_path())
        })

    if "unreal_mcp" in data and isinstance(data["unreal_mcp"], dict) and unreal_mcp_client:
        await unreal_mcp_client.update_config(data["unreal_mcp"])
        if unreal_mcp_client.config.get("enabled", True):
            await unreal_mcp_client.connect()
        SETTINGS["unreal_mcp"] = dict(unreal_mcp_client.config)
        await sio.emit("unreal_mcp_status", unreal_mcp_client.status())

    if "model_runtime" in data and isinstance(data["model_runtime"], dict):
        await model_runtime.update_config(data["model_runtime"])
        SETTINGS["model_runtime"] = model_runtime.config
        await sio.emit("model_status", model_runtime.status())

    if assistant_engine:
        assistant_engine.update_permissions(SETTINGS["tool_permissions"])

    save_settings()
    # Broadcast new full settings
    await sio.emit('settings', SETTINGS)


# Deprecated/Mapped for compatibility if frontend still uses specific events
@sio.event
async def get_tool_permissions(sid):
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

@sio.event
async def update_tool_permissions(sid, data):
    print(f"Updating permissions (legacy event): {data}")
    SETTINGS["tool_permissions"].update(data)
    save_settings()
    
    # Broadcast update to all
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

if __name__ == "__main__":
    uvicorn.run(
        "server:app_socketio", 
        host="127.0.0.1", 
        port=8001, 
        reload=False, # Reload enabled causes spawn of worker which might miss the event loop policy patch
        loop="asyncio",
    )
