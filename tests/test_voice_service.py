"""Lightweight local voice service unit tests."""
from voice_service import LocalVoiceService


def test_voice_service_does_not_load_models_until_started():
    service = LocalVoiceService(on_speech=lambda _text: None)
    assert service.model is None
    assert service.started is False


def test_voice_frames_match_webrtcvad_20ms_requirements():
    assert LocalVoiceService.FRAME_SAMPLES == 320
    assert LocalVoiceService.FRAME_BYTES == 640


def test_voice_output_is_queued_only_when_service_is_running():
    service = LocalVoiceService(on_speech=lambda _text: None)
    service.speak("Not started")
    assert service.tts_queue.empty()
    service.started = True
    service.speak("Hello A.D.A")
    assert service.tts_queue.get_nowait() == "Hello A.D.A"
