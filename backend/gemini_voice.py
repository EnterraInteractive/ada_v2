"""Gemini Live API voice sessions for A.D.A.

Audio is streamed to Google's hosted Live API; no local STT/TTS models are
loaded. The API key is read only from the process environment.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from google import genai
from google.genai import types


Emit = Callable[[str, dict[str, Any], str], Awaitable[None]]


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@dataclass
class VoiceSession:
    sid: str
    client: Any
    stack: AsyncExitStack
    session: Any
    audio_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=48))
    sender_task: asyncio.Task | None = None
    receiver_task: asyncio.Task | None = None
    closed: bool = False


class GeminiVoiceService:
    def __init__(self, emit: Emit):
        self.emit = emit
        self.sessions: dict[str, VoiceSession] = {}

    @staticmethod
    def model_name() -> str:
        return os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()

    async def start(self, sid: str, model_name: str | None = None) -> None:
        if sid in self.sessions:
            return
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Add your Gemini API key to the A.D.A project .env file."
            )

        client = genai.Client(api_key=api_key)
        stack = AsyncExitStack()
        try:
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=(
                    "You are the voice interface for A.D.A, a personal local AI assistant. "
                    "Be concise, natural, and helpful. The user primarily works on Unreal Engine "
                    "and software development. Do not claim to have changed files, run commands, "
                    "or operated applications. For requests requiring A.D.A's local project tools, "
                    "tell the user to use the text assistant interface."
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            )
            session = await stack.enter_async_context(
                client.aio.live.connect(model=(model_name or self.model_name()), config=config)
            )
            voice_session = VoiceSession(
                sid=sid, client=client, stack=stack, session=session
            )
            self.sessions[sid] = voice_session
            voice_session.sender_task = asyncio.create_task(self._send_audio(voice_session))
            voice_session.receiver_task = asyncio.create_task(self._receive(voice_session))
            await self.emit("voice_ready", {"model": model_name or self.model_name()}, sid)
        except Exception:
            await stack.aclose()
            raise

    async def send_audio(self, sid: str, payload: bytes) -> None:
        voice_session = self.sessions.get(sid)
        if not voice_session or voice_session.closed or not payload:
            return
        # Bound queued audio so a slow network never causes unbounded RAM growth.
        if voice_session.audio_queue.full():
            try:
                voice_session.audio_queue.get_nowait()
                voice_session.audio_queue.task_done()
            except asyncio.QueueEmpty:
                pass
        await voice_session.audio_queue.put(payload)

    async def _send_audio(self, voice_session: VoiceSession) -> None:
        try:
            while not voice_session.closed:
                chunk = await voice_session.audio_queue.get()
                try:
                    await voice_session.session.send_realtime_input(
                        audio=types.Blob(
                            data=chunk,
                            mime_type="audio/pcm;rate=16000",
                        )
                    )
                finally:
                    voice_session.audio_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.emit("voice_error", {"message": f"Gemini audio upload failed: {exc}"}, voice_session.sid)

    async def _receive(self, voice_session: VoiceSession) -> None:
        try:
            async for response in voice_session.session.receive():
                server_content = _value(response, "server_content")
                if server_content is None:
                    continue

                input_transcription = _value(server_content, "input_transcription")
                input_text = _value(input_transcription, "text", "")
                if input_text:
                    await self.emit("transcription", {
                        "sender": "You", "text": input_text, "final": True
                    }, voice_session.sid)

                output_transcription = _value(server_content, "output_transcription")
                output_text = _value(output_transcription, "text", "")
                if output_text:
                    await self.emit("transcription", {
                        "sender": "ADA", "text": output_text, "final": True
                    }, voice_session.sid)

                if _value(server_content, "interrupted", False):
                    await self.emit("voice_interrupted", {}, voice_session.sid)

                model_turn = _value(server_content, "model_turn")
                parts = _value(model_turn, "parts", []) or []
                for part in parts:
                    inline_data = _value(part, "inline_data")
                    audio_data = _value(inline_data, "data") if inline_data else None
                    if audio_data:
                        await self.emit("voice_audio", {
                            "audio": bytes(audio_data),
                            "sample_rate": 24000,
                        }, voice_session.sid)

                if _value(server_content, "turn_complete", False):
                    await self.emit("voice_turn_complete", {}, voice_session.sid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not voice_session.closed:
                await self.emit("voice_error", {"message": f"Gemini voice session failed: {exc}"}, voice_session.sid)

    async def stop(self, sid: str) -> None:
        voice_session = self.sessions.pop(sid, None)
        if not voice_session:
            return
        voice_session.closed = True
        for task in (voice_session.sender_task, voice_session.receiver_task):
            if task and not task.done():
                task.cancel()
        tasks = [task for task in (voice_session.sender_task, voice_session.receiver_task) if task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await voice_session.stack.aclose()
        await self.emit("voice_closed", {}, sid)

    async def stop_all(self) -> None:
        for sid in list(self.sessions):
            await self.stop(sid)
