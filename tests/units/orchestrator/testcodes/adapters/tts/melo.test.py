"""VOIC-FEAT-001 M5-S2: fake MeloTTS validates speed, conversion and cancellation."""

import wave
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from voice_agent.adapters.tts.melo import MeloTTSAdapter
from voice_agent.contracts.flow import CancellationToken, OperationCancelled
from voice_agent.contracts.media import INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import Channel, SessionContext


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_tts_converts_wav_at_selected_speed():
    """Given fake 44.1 kHz WAV, when synthesized, then output is 16 kHz PCM at 1.25x."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    observed = []

    class FakeModel:
        hps = SimpleNamespace(data=SimpleNamespace(spk2id={"KR": 0}))

        def __init__(self, **options):
            observed.append(options)

        def tts_to_file(self, text, speaker, path, **options):
            observed.append((text, speaker, options))
            with wave.open(path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44_100)
                wav.writeframes(b"\0\0" * 44_100)

    chunks = [chunk async for chunk in MeloTTSAdapter(model_factory=FakeModel).synthesize(
        "반갑습니다", context, CancellationToken())]
    assert observed == [{"language": "KR", "device": "cuda:0"},
                        ("반갑습니다", 0, {"speed": 1.25})]
    assert len(chunks) == 1
    assert chunks[0].format == INTERNAL_AUDIO_FORMAT
    assert chunks[0].sequence == 0
    assert len(chunks[0].data) == 32_000


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_tts_rejects_empty_and_cancelled():
    """Given blank text or cancelled token, when synthesized, then model is not loaded."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    def forbidden(**kwargs):
        raise AssertionError("native model must not load")

    with pytest.raises(ValueError):
        async for _ in MeloTTSAdapter(model_factory=forbidden).synthesize(
            " ", context, CancellationToken()):
            pass
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        async for _ in MeloTTSAdapter(model_factory=forbidden).synthesize("안녕", context, token):
            pass


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_tts_propagates_native_error():
    """Given native synthesis failure, when synthesized, then error reaches core."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    class BrokenModel:
        hps = SimpleNamespace(data=SimpleNamespace(spk2id={"KR": 0}))
        def __init__(self, **kwargs):
            pass
        def tts_to_file(self, *args, **kwargs):
            raise RuntimeError("synthesis unavailable")
    with pytest.raises(RuntimeError, match="synthesis unavailable"):
        async for _ in MeloTTSAdapter(model_factory=BrokenModel).synthesize(
            "안녕", context, CancellationToken()):
            pass
