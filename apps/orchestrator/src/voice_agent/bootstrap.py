"""Concrete application assembly for VOIC-FEAT-001 M6-S1."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, start_http_server
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from voice_agent.adapters.stt.faster_whisper import FasterWhisperSTT
from voice_agent.adapters.task.openai_compatible import OpenAICompatibleTask
from voice_agent.adapters.tts.melo import MeloTTSAdapter
from voice_agent.adapters.remote_models import RemoteSTT, RemoteTTS
from voice_agent.channels.ht813.outbound import HT813Outbound
from voice_agent.channels.ht813.call_manager import OutboundCallManager
from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.channels.web.voice import web_voice_router
from voice_agent.config import Settings
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.core.orchestrator import VoiceOrchestrator
from voice_agent.infrastructure.retention import EncryptedRetention
from voice_agent.infrastructure.telemetry import configure_tracing


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env(os.environ)
    tracer_provider = configure_tracing(settings.otel_endpoint, "voice-agent-orchestrator")
    if tracer_provider is not None:
        HTTPXClientInstrumentor().instrument()
    task = OpenAICompatibleTask(base_url=settings.task_url,
                                approved_host=settings.task_approved_host, model=settings.task_model,
                                api_key=settings.task_key, timeout_s=settings.timeouts.task_s)
    gate = SingleSessionGate()
    retention = EncryptedRetention(
        recordings_dir=settings.recordings_dir,
        transcripts_dir=settings.transcripts_dir,
        audit_path=settings.deletion_audit_path,
        key=settings.data_encryption_key,
        sweep_interval_s=settings.retention_sweep_interval_s,
    )
    stt = RemoteSTT(settings.stt_endpoint, settings.timeouts.stt_s) if settings.stt_endpoint else FasterWhisperSTT(settings.stt_model)
    tts = RemoteTTS(settings.tts_endpoint, settings.timeouts.tts_s) if settings.tts_endpoint else MeloTTSAdapter(settings.tts_speed)
    runner = VoiceOrchestrator(
        stt, task, tts,
        gate, settings.timeouts, settings.buffer_capacity, retention,
    )
    outbound = None
    if settings.allowed_numbers is not None:
        outbound = HT813Outbound(
            host=settings.ht813_host, port=settings.ht813_port,
            local_host=settings.ht813_local_host, user_id=settings.ht813_user,
            password=settings.ht813_password, policy=settings.allowed_numbers,
            local_sip_port=settings.ht813_local_sip_port,
            local_rtp_port=settings.ht813_local_rtp_port,
        )

    inbound = InboundSIPService(
        peer_host=settings.ht813_host, peer_port=settings.ht813_port,
        local_host=settings.ht813_local_host,
        sip_port=settings.ht813_inbound_sip_port,
        rtp_port=settings.ht813_inbound_rtp_port,
        user_id=settings.ht813_user, runner=runner, gate=gate,
        boundary=settings.turn_boundary,
    ) if settings.ht813_inbound_enabled else None

    calls = OperatorCalls(OutboundCallManager(outbound, runner, gate, settings.turn_boundary)
                          if outbound is not None else None, gate, settings.web_token)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await retention.start()
            if settings.stt_endpoint and not await stt.ready():
                raise RuntimeError("STT model endpoint is not ready")
            if settings.tts_endpoint and not await tts.ready():
                raise RuntimeError("TTS model endpoint is not ready")
            if inbound is not None:
                await inbound.start()
            if settings.metrics_host:
                app.state.metrics_server, _ = start_http_server(
                    settings.metrics_port, addr=settings.metrics_host)
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            if app.state.metrics_server is not None:
                app.state.metrics_server.shutdown()
                app.state.metrics_server.server_close()
                app.state.metrics_server = None
            try:
                await calls.close()
            finally:
                try:
                    if inbound is not None:
                        await inbound.close()
                finally:
                    await retention.close()
                    if settings.stt_endpoint:
                        await stt.close()
                        await tts.close()
                    if tracer_provider is not None:
                        tracer_provider.shutdown()
                    app.state.runner = None
                    app.state.outbound = None
                    app.state.operator_calls = None
                    app.state.inbound = None
                    app.state.retention = None

    app = FastAPI(lifespan=lifespan)
    app.state.ready = False
    app.state.metrics_server = None
    app.state.runner = runner
    app.state.outbound = outbound
    app.state.operator_calls = calls
    app.state.inbound = inbound
    app.state.retention = retention
    app.include_router(web_voice_router(runner, settings.web_token))
    app.include_router(operator_router(calls))

    @app.get("/health")
    async def health() -> dict[str, str]:
        if not settings.stt_endpoint:
            return {"status": "ready" if app.state.ready and retention.ready else
                    "degraded" if app.state.ready else "stopping"}
        stt_ready = await stt.ready() if settings.stt_endpoint else True
        tts_ready = await tts.ready() if settings.tts_endpoint else True
        return {"status": "ready" if app.state.ready and retention.ready and stt_ready and tts_ready else
                "degraded" if app.state.ready else "stopping",
                "stt": "ready" if stt_ready else "unavailable",
                "tts": "ready" if tts_ready else "unavailable"}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
