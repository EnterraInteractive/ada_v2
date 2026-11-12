"""Optional local VoiceStudio TTS adapter with project-local WAV caching.

VoiceStudio is contacted only on loopback. If it is not running or its profile
is unavailable, callers can fall back to A.D.A's bundled local Piper voice.
"""
from __future__ import annotations

import array
import hashlib
import json
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any


class VoiceStudioError(RuntimeError):
    pass


class VoiceStudioClient:
    def __init__(self, project_root: str | Path, config: dict[str, Any] | None = None):
        self.project_root = Path(project_root).resolve()
        self.config = config or {}
        self.base_url = str(self.config.get("url") or "http://127.0.0.1:3900").rstrip("/")
        self.engine = str(self.config.get("engine") or "voxcpm2")
        self.model_id = str(self.config.get("model_id") or "voxcpm2")
        self.profile_name = str(self.config.get("profile") or "Jarvis")
        self.language = str(self.config.get("language") or "en")
        self.cache_dir = self.project_root / ".ada" / "cache" / "voice"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._selected = False
        self._warmed = False
        self._last_warm = 0.0
        self.profile_id: str | None = None

    def _request(self, path: str, payload: dict | None = None, timeout: float = 5.0) -> bytes:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise VoiceStudioError(f"VoiceStudio is unavailable at {self.base_url}: {exc}") from exc

    def _select(self) -> None:
        if self._selected:
            return
        self._request("/health", timeout=1.0)
        profiles_payload = json.loads(self._request("/profiles").decode("utf-8"))
        profiles = profiles_payload if isinstance(profiles_payload, list) else profiles_payload.get("profiles", profiles_payload.get("items", []))
        selected = next(
            (item for item in profiles if str(item.get("name", "")).casefold() == self.profile_name.casefold()),
            None,
        )
        if not selected:
            raise VoiceStudioError(f"VoiceStudio profile '{self.profile_name}' was not found.")
        self.profile_id = str(selected.get("id") or selected.get("profile_id") or "")
        if not self.profile_id:
            raise VoiceStudioError(f"VoiceStudio profile '{self.profile_name}' has no profile id.")
        self._request("/engines/select", {
            "family": "tts",
            "backend_id": self.engine,
            "model_id": self.model_id,
        })
        self._selected = True

    def set_profile(self, profile_name: str) -> None:
        name = (profile_name or "").strip()
        if not name:
            raise ValueError("Voice profile name cannot be empty.")
        self.profile_name = name
        self.profile_id = None
        self._selected = False
        self._warmed = False
        self._last_warm = 0.0

    def warm(self) -> None:
        """Select the configured engine/profile and warm it with a discarded line."""
        self._select()
        self._render_wav("Standing by.")
        self._warmed = True
        self._last_warm = time.monotonic()

    def _wav_to_pcm(self, wav_bytes: bytes, target_rate: int = 24000) -> bytes:
        import io
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        if width != 2:
            raise VoiceStudioError(f"VoiceStudio returned {width * 8}-bit audio; 16-bit PCM is required.")
        samples = array.array("h")
        samples.frombytes(frames)
        if __import__("sys").byteorder != "little":
            samples.byteswap()
        if channels > 1:
            samples = array.array("h", (
                sum(samples[i:i + channels]) // channels
                for i in range(0, len(samples), channels)
            ))
        if rate != target_rate and samples:
            output_count = max(1, round(len(samples) * target_rate / rate))
            resampled = array.array("h")
            for index in range(output_count):
                position = index * rate / target_rate
                left = min(int(position), len(samples) - 1)
                right = min(left + 1, len(samples) - 1)
                fraction = position - left
                resampled.append(int(samples[left] * (1 - fraction) + samples[right] * fraction))
            samples = resampled
        if __import__("sys").byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def _render_wav(self, text: str) -> bytes:
        payload = {
            "model": self.model_id,
            "input": text,
            "voice": self.profile_id,
            "response_format": "wav",
            "language": self.language,
        }
        return self._request("/v1/audio/speech", payload, timeout=120.0)

    def synthesize_pcm16(self, text: str) -> bytes:
        if len(text) > 600:
            raise VoiceStudioError("VoiceStudio requests are limited to 600 characters; send sentence-sized chunks.")
        self._select()
        cache_key = hashlib.sha256(
            (self.profile_id + "\\0" + text).encode("utf-8")
        ).hexdigest()
        cached = self.cache_dir / f"{cache_key}.wav"
        if cached.is_file():
            return self._wav_to_pcm(cached.read_bytes())

        if not self._warmed or time.monotonic() - self._last_warm >= 600:
            self._render_wav("Standing by.")
            self._warmed = True
            self._last_warm = time.monotonic()

        try:
            audio = self._render_wav(text)
        except VoiceStudioError:
            # VoiceStudio may have restarted and lost its selected engine/profile.
            self._selected = False
            self._warmed = False
            self._select()
            self._render_wav("Standing by.")
            self._warmed = True
            self._last_warm = time.monotonic()
            audio = self._render_wav(text)
        temporary = cached.with_suffix(".wav.tmp")
        temporary.write_bytes(audio)
        temporary.replace(cached)
        return self._wav_to_pcm(audio)
