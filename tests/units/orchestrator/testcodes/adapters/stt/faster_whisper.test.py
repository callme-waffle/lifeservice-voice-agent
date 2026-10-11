"""VOIC-FEAT-001 M5-S2: fake native STT tests format, text, and cancellation."""

import io
import wave
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from voice_agent.adapters.stt.faster_whisper import FasterWhisperSTT
from voice_agent.contracts.flow import CancellationToken, OperationCancelled
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import Channel, SessionContext, Transcript


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_stt_wraps_pcm_and_returns_final_korean():
    """Given PCM16, when transcribed, then fake model receives 16 kHz WAV and final text."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    observed = []

    class FakeModel:
        def __init__(self, name, **options):
            observed.append((name, options))

        def transcribe(self, source, **options):
            with wave.open(source, "rb") as wav:
                observed.append((wav.getframerate(), wav.getnchannels(), wav.readframes(1)))
            return [SimpleNamespace(text=" 안녕하세요 ")], None

    async def audio():
        yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    result = [item async for item in FasterWhisperSTT(model_factory=FakeModel).transcribe(
        audio(), context, CancellationToken())]
    assert result == [Transcript("안녕하세요", True)]
    assert observed == [("small", {"device": "cuda", "compute_type": "int8"}),
                        (16_000, 1, b"\0\0")]


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_stt_rejects_wrong_session_and_cancel():
    """Given wrong session or cancellation, when reading, then model is never invoked."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    def forbidden(*args, **kwargs):
        raise AssertionError("native model must not load")

    async def wrong():
        yield AudioChunk(uuid4(), 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    with pytest.raises(ValueError):
        async for _ in FasterWhisperSTT(model_factory=forbidden).transcribe(
            wrong(), context, CancellationToken()):
            pass
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        async for _ in FasterWhisperSTT(model_factory=forbidden).transcribe(
            wrong(), context, token):
            pass


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s2_stt_propagates_native_error():
    """Given native inference failure, when transcribed, then error reaches core."""
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    class BrokenModel:
        def __init__(self, *args, **kwargs):
            pass
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("model unavailable")
    async def audio():
        yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
    with pytest.raises(RuntimeError, match="model unavailable"):
        async for _ in FasterWhisperSTT(model_factory=BrokenModel).transcribe(
            audio(), context, CancellationToken()):
            pass
