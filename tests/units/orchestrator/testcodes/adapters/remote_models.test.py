"""VOIC-FEAT-001 M6-S3: remote model adapter contract."""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from voice_agent.adapters.remote_models import RemoteSTT, RemoteTTS
from voice_agent.contracts.flow import CancellationToken
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import Channel, SessionContext


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s3_remote_models_preserve_audio_contract():
    """Given private endpoints, when STT and TTS run, then PCM and text cross the right boundary."""
    seen = []

    def handle(request):
        seen.append((request.url.path, request.content, dict(request.headers)))
        if request.url.path == "/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.headers.get("content-type") == "audio/L16":
            return httpx.Response(200, json={"text": "시험"})
        return httpx.Response(200, content=b"\x00\x01" * 100)

    stt = RemoteSTT("http://models", 5)
    tts = RemoteTTS("http://models", 5)
    await stt.client.aclose()
    await tts.client.aclose()
    stt.client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://models")
    tts.client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://models")
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    cancel = CancellationToken()

    async def incoming():
        yield AudioChunk(context.session_id, 0, b"\x01\0" * 100, INTERNAL_AUDIO_FORMAT)

    try:
        assert await stt.ready() and await tts.ready()
        parent = NonRecordingSpan(SpanContext(
            trace_id=0x1234567890ABCDEF1234567890ABCDEF,
            span_id=0x1234567890ABCDEF,
            is_remote=False,
            trace_flags=TraceFlags(1),
        ))
        with trace.use_span(parent):
            transcript = [item async for item in stt.transcribe(incoming(), context, cancel)]
            audio = [item async for item in tts.synthesize(transcript[0].text, context, cancel)]
        assert transcript[0].text == "시험"
        assert b"\x01\0" * 100 in [body for path, body, _ in seen if path == "/infer"]
        assert '"text":"시험"'.encode() in seen[-1][1]
        infer_headers = [headers for path, _, headers in seen if path == "/infer"]
        assert len(infer_headers) == 2
        assert all(headers["traceparent"].startswith("00-1234567890abcdef1234567890abcdef-")
                   for headers in infer_headers)
        assert len(audio) == 1 and audio[0].format == INTERNAL_AUDIO_FORMAT
    finally:
        await stt.close()
        await tts.close()
