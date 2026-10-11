"""VOIC-FEAT-001 M6-S3: warm model readiness and inference boundaries."""

from types import SimpleNamespace
import wave

from fastapi.testclient import TestClient

from voice_models.server import create_app


def test_voic_feat_001_m6_s3_stt_loads_once_before_ready():
    """Given a model factory, when two utterances arrive, then the loaded model is reused."""
    loads = []

    class Model:
        def transcribe(self, source, **kwargs):
            return [SimpleNamespace(text="안녕하세요")], None

    def factory(*args, **kwargs):
        loads.append(1)
        return Model()

    app = create_app("stt", model_factory=factory)
    with TestClient(app) as client:
        assert client.get("/ready").json()["status"] == "ready"
        for _ in range(2):
            response = client.post("/infer", content=b"\0\0", headers={"content-type": "audio/L16"})
            assert response.status_code == 200
            assert response.json() == {"text": "안녕하세요"}
    assert len(loads) == 1


def test_voic_feat_001_m6_s3_stt_silence_returns_unprocessable():
    """Given no recognized speech, when STT runs, then the client receives 422."""
    class Model:
        def transcribe(self, source, **kwargs):
            return [], None

    app = create_app("stt", model_factory=lambda *args, **kwargs: Model())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/infer", content=b"\0\0" * 16000)
        assert response.status_code == 422


def test_voic_feat_001_m6_s3_tts_loads_once_and_returns_pcm(tmp_path):
    """Given a TTS model, when ready, then one warmup precedes two PCM requests."""
    loads = []
    syntheses = []

    class Model:
        hps = SimpleNamespace(data=SimpleNamespace(spk2id={"KR": 0}))

        def tts_to_file(self, text, speaker, filename, speed):
            syntheses.append(text)
            with wave.open(filename, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(44_100)
                output.writeframes(b"\x01\0" * 4410)

    def factory(*args, **kwargs):
        loads.append(1)
        return Model()

    app = create_app("tts", model_factory=factory)
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert syntheses == ["안녕하세요."]
        for _ in range(2):
            response = client.post("/infer", json={"text": "안녕하세요"})
            assert response.status_code == 200
            assert len(response.content) > 0
            assert len(response.content) % 2 == 0
    assert len(loads) == 1
    assert len(syntheses) == 3
