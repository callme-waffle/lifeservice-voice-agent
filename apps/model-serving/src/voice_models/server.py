"""One warm model per serving process."""

from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, start_http_server
from pydantic import BaseModel

from voice_agent.adapters.stt.faster_whisper import FasterWhisperSTT
from voice_agent.adapters.tts.melo import MeloTTSAdapter
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import Channel, SessionContext
from voice_agent.infrastructure.telemetry import configure_tracing, stage


class _NeverCancelled:
    def raise_if_cancelled(self) -> None:
        return None


class SpeechRequest(BaseModel):
    text: str


def create_app(kind: str, *, model_factory=None) -> FastAPI:
    if kind not in {"stt", "tts"}:
        raise ValueError("MODEL_KIND must be stt or tts")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tracer_provider = configure_tracing(os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"),
                                            f"voice-agent-{kind}")
        metrics_server = None
        if kind == "stt":
            if model_factory is None:
                from faster_whisper import WhisperModel
                model_factory_local = WhisperModel
            else:
                model_factory_local = model_factory
            name = os.getenv("VOICE_AGENT_STT_MODEL_ID", "small")
            app.state.model = model_factory_local(name, device="cuda", compute_type="int8")
            app.state.adapter = FasterWhisperSTT(name, model_factory=lambda *a, **k: app.state.model)
        else:
            if model_factory is None:
                from melo.api import TTS
                model_factory_local = TTS
            else:
                model_factory_local = model_factory
            app.state.model = model_factory_local(language="KR", device="cuda:0")
            app.state.adapter = MeloTTSAdapter(
                float(os.getenv("VOICE_AGENT_TTS_SPEED", "1.25")),
                model_factory=lambda *a, **k: app.state.model,
            )
            warm_context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
            async for _ in app.state.adapter.synthesize("안녕하세요.", warm_context, _NeverCancelled()):
                pass
        app.state.ready = True
        if os.getenv("MODEL_METRICS_HOST"):
            metrics_server, _ = start_http_server(
                int(os.getenv("MODEL_METRICS_PORT", "8103")),
                addr=os.environ["MODEL_METRICS_HOST"],
            )
        try:
            yield
        finally:
            app.state.ready = False
            if metrics_server is not None:
                metrics_server.shutdown()
                metrics_server.server_close()
            app.state.adapter = None
            app.state.model = None
            if tracer_provider is not None:
                tracer_provider.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.ready = False
    app.state.inference_lock = asyncio.Lock()

    @app.get("/ready")
    async def ready():
        if not app.state.ready:
            raise HTTPException(503, "model loading")
        return {"status": "ready", "model": kind}

    @app.post("/infer")
    async def infer(request: Request):
        if not app.state.ready:
            raise HTTPException(503, "model loading")
        context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
        if kind == "stt":
            pcm = await request.body()
            if not pcm or len(pcm) % 2 or len(pcm) > 16_000 * 2 * 60:
                raise HTTPException(422, "invalid audio size")

            async def chunks():
                for sequence, offset in enumerate(range(0, len(pcm), 32_000)):
                    yield AudioChunk(context.session_id, sequence, pcm[offset:offset + 32_000],
                                     INTERNAL_AUDIO_FORMAT)

            async with app.state.inference_lock:
                with stage("model_stt"):
                    try:
                        async for transcript in app.state.adapter.transcribe(chunks(), context, _NeverCancelled()):
                            return {"text": transcript.text}
                    except ValueError as exc:
                        if str(exc) == "no speech was recognized":
                            raise HTTPException(422, "no speech was recognized") from None
                        raise
            raise HTTPException(422, "no transcript")
        payload = SpeechRequest.model_validate(await request.json())
        if not payload.text.strip() or len(payload.text) > 4000:
            raise HTTPException(422, "invalid text size")
        pcm = bytearray()
        async with app.state.inference_lock:
            with stage("model_tts"):
                async for chunk in app.state.adapter.synthesize(payload.text, context, _NeverCancelled()):
                    pcm.extend(chunk.data)
        return Response(bytes(pcm), media_type="audio/L16;rate=16000;channels=1")

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app(os.getenv("MODEL_KIND", "stt"))
