"""Fully local speech pipeline for A.D.A.

Accepts mono signed-16-bit PCM at 16 kHz, segments utterances using a bounded
energy VAD, transcribes with a project-local faster-whisper model, sends the
transcript through A.D.A's existing conversation orchestrator, and synthesizes
the response with a project-local Piper voice. No hosted speech API is used.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import wave
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

Emit = Callable[[str, dict[str, Any], str], Awaitable[None]]
LocalQuery = Callable[[str, str], Awaitable[str]]


@dataclass
class LocalVoiceSession:
    sid: str
    pcm: bytearray = field(default_factory=bytearray)
    silence_ms: int = 0
    speech_ms: int = 0
    processing: bool = False
    closed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class LocalVoiceService:
    """Local Whisper + Piper voice adapter compatible with A.D.A Socket.IO events."""

    SAMPLE_RATE = 16000
    FRAME_MS = 128
    SILENCE_END_MS = 720
    MIN_SPEECH_MS = 240
    MAX_UTTERANCE_MS = 18000
    ENERGY_THRESHOLD = 420

    def __init__(
        self,
        emit: Emit,
        local_query: LocalQuery,
        project_root: str | Path,
        config: dict[str, Any] | None = None,
        tts_callback: Callable[[str], bytes] | None = None,
    ):
        self.emit = emit
        self.local_query = local_query
        self.project_root = Path(project_root).resolve()
        self.config = config or {}
        self.tts_callback = tts_callback
        self.sessions: dict[str, LocalVoiceSession] = {}
        self._whisper: Any | None = None
        self._whisper_wake: Any | None = None
        self._piper: Any | None = None
        self._load_lock = asyncio.Lock()

    def _model_path(self, key: str, default: str) -> Path:
        value = Path(str(self.config.get(key) or default)).expanduser()
        resolved = value if value.is_absolute() else self.project_root / value
        resolved = resolved.resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise RuntimeError(f"Local voice model path must remain inside the A.D.A project: {resolved}") from exc
        return resolved

    async def _load_models(self) -> None:
        if self._whisper is not None and self._piper is not None:
            return
        async with self._load_lock:
            if self._whisper is not None and self._piper is not None:
                return

            whisper_path = self._model_path("whisper_model_path", "models/voice/whisper-large-v3-turbo")
            piper_path = self._model_path("piper_model_path", "models/voice/piper/en_US-lessac-medium.onnx")
            piper_config = Path(str(piper_path) + ".json")
            if not whisper_path.exists():
                raise RuntimeError(f"Local Whisper model is missing: {whisper_path}")
            if not piper_path.is_file() or not piper_config.is_file():
                raise RuntimeError(
                    "Local Piper voice is missing. Expected both "
                    f"{piper_path} and {piper_config}."
                )

            def load():
                from faster_whisper import WhisperModel
                from piper import PiperVoice
                device = str(self.config.get("whisper_device", "cuda"))
                compute_type = str(self.config.get("whisper_compute_type", "float16" if device == "cuda" else "int8"))
                try:
                    whisper = WhisperModel(str(whisper_path), device=device, compute_type=compute_type)
                except Exception:
                    if device != "cpu":
                        whisper = WhisperModel(str(whisper_path), device="cpu", compute_type="int8")
                    else:
                        raise
                piper = PiperVoice.load(str(piper_path), config_path=str(piper_config))
                return whisper, piper

            self._whisper, self._piper = await asyncio.to_thread(load)

    async def _load_piper_only(self) -> None:
        """Load only the local Piper fallback for speech synthesis."""
        if self._piper is not None:
            return
        async with self._load_lock:
            if self._piper is not None:
                return
            piper_path = self._model_path("piper_model_path", "models/voice/piper/en_US-lessac-medium.onnx")
            piper_config = Path(str(piper_path) + ".json")
            if not piper_path.is_file() or not piper_config.is_file():
                raise RuntimeError(f"Local Piper voice is missing: {piper_path} and its JSON config.")

            def load():
                from piper import PiperVoice
                return PiperVoice.load(str(piper_path), config_path=str(piper_config))

            self._piper = await asyncio.to_thread(load)

    async def _load_whisper_only(self) -> None:
        """Load only the local Whisper model for HTTP transcription requests."""
        if self._whisper is not None:
            return
        async with self._load_lock:
            if self._whisper is not None:
                return
            whisper_path = self._model_path("whisper_model_path", "models/voice/whisper-large-v3-turbo")
            if not whisper_path.exists():
                raise RuntimeError(f"Local Whisper model is missing: {whisper_path}")

            def load():
                from faster_whisper import WhisperModel
                device = str(self.config.get("whisper_device", "cuda"))
                compute_type = str(self.config.get("whisper_compute_type", "float16" if device == "cuda" else "int8"))
                try:
                    return WhisperModel(str(whisper_path), device=device, compute_type=compute_type)
                except Exception:
                    if device != "cpu":
                        return WhisperModel(str(whisper_path), device="cpu", compute_type="int8")
                    raise

            self._whisper = await asyncio.to_thread(load)

    async def _load_wake_whisper(self) -> None:
        """Load the small, project-local Whisper model used only for wake detection."""
        if self._whisper_wake is not None:
            return
        async with self._load_lock:
            if self._whisper_wake is not None:
                return
            wake_path = self._model_path("wake_model_path", "models/voice/whisper-small")
            if not wake_path.exists():
                raise RuntimeError(f"Local wake-word model is missing: {wake_path}")

            def load():
                from faster_whisper import WhisperModel
                device = str(self.config.get("whisper_device", "cuda"))
                compute_type = str(self.config.get("whisper_compute_type", "float16" if device == "cuda" else "int8"))
                try:
                    return WhisperModel(str(wake_path), device=device, compute_type=compute_type)
                except Exception:
                    if device != "cpu":
                        return WhisperModel(str(wake_path), device="cpu", compute_type="int8")
                    raise

            self._whisper_wake = await asyncio.to_thread(load)

    async def start(self, sid: str, model_name: str | None = None) -> None:
        await self._load_models()
        self.sessions[sid] = LocalVoiceSession(sid=sid)
        await self.emit("voice_ready", {"provider": "local", "model": "Whisper + Piper"}, sid)

    async def send_audio(self, sid: str, payload: bytes) -> None:
        session = self.sessions.get(sid)
        if not session or session.closed or not payload:
            return
        if len(payload) % 2:
            payload = payload[:-1]
        if not payload:
            return
        async with session.lock:
            if session.processing:
                return
            samples = array("h")
            samples.frombytes(payload)
            if os.sys.byteorder != "little":
                samples.byteswap()
            rms = math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
            duration_ms = int(len(samples) * 1000 / self.SAMPLE_RATE)
            if rms >= self.ENERGY_THRESHOLD:
                session.speech_ms += duration_ms
                session.silence_ms = 0
                session.pcm.extend(payload)
            elif session.speech_ms:
                session.silence_ms += duration_ms
                session.pcm.extend(payload)

            utterance_complete = (
                session.speech_ms >= self.MIN_SPEECH_MS
                and session.silence_ms >= self.SILENCE_END_MS
            )
            utterance_too_long = session.speech_ms >= self.MAX_UTTERANCE_MS
            if utterance_complete or utterance_too_long:
                audio = bytes(session.pcm)
                session.pcm.clear()
                session.speech_ms = 0
                session.silence_ms = 0
                session.processing = True
                asyncio.create_task(self._process_utterance(session, audio))

    async def _process_utterance(self, session: LocalVoiceSession, audio: bytes) -> None:
        try:
            if session.closed:
                return
            await self.emit("assistant_status", {"state": "transcribing"}, session.sid)
            transcript = await asyncio.to_thread(self._transcribe, audio)
            if not transcript:
                return
            await self.emit("voice_transcript", {"text": transcript, "final": True}, session.sid)
            await self.emit("assistant_status", {"state": "thinking"}, session.sid)
            answer = await self.local_query(session.sid, transcript)
            if session.closed or not answer:
                return
            await self.emit("assistant_status", {"state": "speaking"}, session.sid)
            pcm = await asyncio.to_thread(self._synthesize, answer)
            if pcm and not session.closed:
                await self.emit("voice_audio", {"audio": pcm, "sample_rate": 24000, "format": "pcm_s16le"}, session.sid)
        except Exception as exc:
            await self.emit("voice_error", {"message": f"Local voice failed: {type(exc).__name__}: {exc}"}, session.sid)
        finally:
            session.processing = False
            if not session.closed:
                await self.emit("assistant_status", {"state": "idle"}, session.sid)

    def _transcribe(self, audio: bytes, model_role: str = "command") -> str:
        import numpy as np
        model = self._whisper_wake if model_role == "wake" else self._whisper
        model = model or self._whisper
        if model is None:
            raise RuntimeError("The requested local Whisper model has not been loaded.")
        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
        segments, _info = model.transcribe(
            samples,
            language=self.config.get("language") or None,
            vad_filter=True,
            beam_size=3,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

    def _synthesize(self, text: str) -> bytes:
        if self.tts_callback is not None:
            try:
                return self.tts_callback(text)
            except Exception as exc:
                print(f"[VOICE] VoiceStudio synthesis failed; using Piper: {type(exc).__name__}: {exc}")
        output = io.BytesIO()
        self._piper.synthesize_wav(text, output)
        output.seek(0)
        with wave.open(output, "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        if sample_width != 2:
            raise RuntimeError(f"Unsupported Piper sample width: {sample_width * 8}-bit")
        samples = array("h")
        samples.frombytes(frames)
        if os.sys.byteorder != "little":
            samples.byteswap()
        if channels > 1:
            samples = array("h", (sum(samples[i:i + channels]) // channels for i in range(0, len(samples), channels)))
        if sample_rate != 24000:
            import audioop
            converted, _state = audioop.ratecv(samples.tobytes(), 2, 1, sample_rate, 24000, None)
            return converted
        return samples.tobytes()

    async def stop(self, sid: str) -> None:
        session = self.sessions.pop(sid, None)
        if session:
            session.closed = True
            session.pcm.clear()
            await self.emit("voice_closed", {}, sid)

    async def stop_all(self) -> None:
        for sid in list(self.sessions):
            await self.stop(sid)
