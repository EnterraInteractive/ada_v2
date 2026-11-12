"""Local microphone transcription and speech output for A.D.A.

Whisper runs in-process on CPU so it does not compete with the GPU-resident
coding/vision model. Speech output uses the operating system's speech engine.
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections import deque



class LocalVoiceService:
    SAMPLE_RATE = 16000
    FRAME_MS = 20
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
    FRAME_BYTES = FRAME_SAMPLES * 2

    def __init__(self, on_speech, on_status=None, on_error=None, device_name=None,
                 model_size="base.en", vad_aggressiveness=2):
        self.on_speech = on_speech
        self.on_status = on_status
        self.on_error = on_error
        self.device_name = device_name
        self.model_size = model_size
        self.vad_aggressiveness = max(0, min(3, int(vad_aggressiveness)))
        self.loop = None
        self.model = None
        self.audio = None
        self.stream = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.speech_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        self.capture_thread = None
        self.transcribe_thread = None
        self.tts_thread = None
        self.started = False

    async def start(self):
        if self.started:
            return
        self.loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._load_model)
        self.stop_event.clear()
        self.pause_event.clear()
        self.capture_thread = threading.Thread(target=self._capture_loop, name="ADA-Microphone", daemon=True)
        self.transcribe_thread = threading.Thread(target=self._transcribe_loop, name="ADA-Whisper", daemon=True)
        self.tts_thread = threading.Thread(target=self._tts_loop, name="ADA-Speech", daemon=True)
        self.transcribe_thread.start()
        self.tts_thread.start()
        self.capture_thread.start()
        self.started = True
        await self._notify(self.on_status, {"msg": f"Local voice ready ({self.model_size}, CPU)."})
        
    def _load_model(self):
        from faster_whisper import WhisperModel
        if self.model is None:
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def _notify_threadsafe(self, callback, payload):
        if callback and self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._notify(callback, payload), self.loop)

    async def _notify(self, callback, payload):
        if callback:
            result = callback(payload)
            if hasattr(result, "__await__"):
                await result

    def _resolve_input_device(self, audio):
        if not self.device_name:
            return None
        wanted = self.device_name.casefold()
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            name = str(info.get("name", ""))
            if info.get("maxInputChannels", 0) > 0 and (wanted in name.casefold() or name.casefold() in wanted):
                return index
        return None

    def _capture_loop(self):
        import pyaudio
        import webrtcvad
        vad = webrtcvad.Vad(self.vad_aggressiveness)
        ring = deque(maxlen=8)
        speech_frames = []
        triggered = False
        silence_frames = 0
        try:
            self.audio = pyaudio.PyAudio()
            device_index = self._resolve_input_device(self.audio)
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.FRAME_SAMPLES,
            )
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    time.sleep(0.05)
                    continue
                frame = self.stream.read(self.FRAME_SAMPLES, exception_on_overflow=False)
                is_speech = vad.is_speech(frame, self.SAMPLE_RATE)
                if is_speech:
                    if not triggered:
                        triggered = True
                        speech_frames.extend(ring)
                        ring.clear()
                    speech_frames.append(frame)
                    silence_frames = 0
                elif triggered:
                    speech_frames.append(frame)
                    silence_frames += 1
                    if silence_frames >= 32:
                        if len(speech_frames) >= 15:
                            self.speech_queue.put(b"".join(speech_frames))
                        speech_frames = []
                        silence_frames = 0
                        triggered = False
                else:
                    ring.append(frame)
            if triggered and len(speech_frames) >= 15:
                self.speech_queue.put(b"".join(speech_frames))
        except Exception as exc:
            self._notify_threadsafe(self.on_error, {"msg": f"Microphone error: {exc}"})
        finally:
            try:
                if self.stream:
                    self.stream.stop_stream()
                    self.stream.close()
            except Exception:
                pass
            try:
                if self.audio:
                    self.audio.terminate()
            except Exception:
                pass
            self.speech_queue.put(None)

    def _transcribe_loop(self):
        import numpy as np
        while not self.stop_event.is_set() or not self.speech_queue.empty():
            try:
                audio_bytes = self.speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if audio_bytes is None:
                break
            try:
                audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                segments, _info = self.model.transcribe(
                    audio,
                    language="en",
                    beam_size=1,
                    vad_filter=False,
                    condition_on_previous_text=False,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
                if text:
                    self._notify_threadsafe(self.on_speech, text)
            except Exception as exc:
                self._notify_threadsafe(self.on_error, {"msg": f"Speech recognition error: {exc}"})
        self.tts_queue.put(None)

    def _tts_loop(self):
        import pyttsx3
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
        except Exception as exc:
            self._notify_threadsafe(self.on_error, {"msg": f"Speech output unavailable: {exc}"})
            return
        while True:
            text = self.tts_queue.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                self._notify_threadsafe(self.on_error, {"msg": f"Speech output error: {exc}"})
        try:
            engine.stop()
        except Exception:
            pass

    def speak(self, text: str):
        if not self.started or not text:
            return
        clean = text.replace("```", " code ").replace("`", "")
        clean = " ".join(clean.split())
        if clean:
            self.tts_queue.put(clean[:2500])

    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    async def stop(self):
        if not self.started:
            return
        self.stop_event.set()
        self.pause_event.clear()
        if self.capture_thread:
            await asyncio.to_thread(self.capture_thread.join, 3)
        if self.transcribe_thread:
            await asyncio.to_thread(self.transcribe_thread.join, 5)
        if self.tts_thread:
            self.tts_queue.put(None)
            await asyncio.to_thread(self.tts_thread.join, 5)
        self.started = False
        self.capture_thread = self.transcribe_thread = self.tts_thread = None
        self.stream = self.audio = None
        await self._notify(self.on_status, {"msg": "Local voice stopped."})
