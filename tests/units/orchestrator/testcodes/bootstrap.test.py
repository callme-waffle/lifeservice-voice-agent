"""VOIC-FEAT-001 M6-S1-T1 application assembly cases."""

import asyncio

from voice_agent.bootstrap import create_app
from voice_agent.config import Settings


def valid_env():
    return {
        "VOICE_AGENT_WEB_ACCESS_TOKEN": "test-only-token",
        "VOICE_AGENT_STT_MODEL_ID": "small",
        "VOICE_AGENT_TASK_MODEL": "test-model",
        "VOICE_AGENT_TASK_API_KEY": "test-only-key",
        "VOICE_AGENT_TASK_API_BASE_URL": "https://llm.example.test",
        "VOICE_AGENT_TASK_APPROVED_HOST": "llm.example.test",
        "VOICE_AGENT_DATA_ENCRYPTION_KEY": "S0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0s=",
    }


def test_app_assembles_web_and_gracefully_releases_state():
    """Given valid web settings, when lifespan ends, then health and resources reset."""
    app = create_app(Settings.from_env(valid_env()))
    assert app.state.outbound is None
    assert app.state.runner._retention is app.state.retention
    assert any(
        nested.path == "/voice"
        for route in app.routes if hasattr(route, "original_router")
        for nested in route.original_router.routes
    )

    async def fake_start():
        app.state.retention.ready = True

    async def fake_close():
        app.state.retention.ready = False

    app.state.retention.start = fake_start
    app.state.retention.close = fake_close

    async def run():
        async with app.router.lifespan_context(app):
            assert app.state.ready is True
            health = next(route for route in app.routes if getattr(route, "path", None) == "/health")
            assert await health.endpoint() == {"status": "ready"}
            app.state.retention.ready = False
            assert await health.endpoint() == {"status": "degraded"}
            app.state.retention.ready = True
        assert app.state.ready is False
        assert app.state.runner is None

    asyncio.run(run())


def test_app_assembles_outbound_only_with_explicit_policy():
    """Given explicit allowed numbers, when assembling, then outbound is selectable."""
    env = valid_env() | {
        "VOICE_AGENT_HT813_ALLOWED_EXACT": "1234567",
        "VOICE_AGENT_HT813_HOST": "192.0.2.17",
        "VOICE_AGENT_HT813_LOCAL_IPV4": "192.0.2.50",
        "VOICE_AGENT_HT813_SIP_USER_ID": "test-user",
    }
    app = create_app(Settings.from_env(env))
    assert app.state.outbound is not None
    assert app.state.outbound.policy.exact == frozenset({"1234567"})


def test_app_assembles_inbound_without_outbound_dialer():
    """Given trusted inbound settings and no destinations, when assembled, then no dialer exists."""
    env = valid_env() | {
        "VOICE_AGENT_HT813_INBOUND_ENABLED": "true",
        "VOICE_AGENT_HT813_HOST": "192.0.2.17",
        "VOICE_AGENT_HT813_LOCAL_IPV4": "192.0.2.50",
        "VOICE_AGENT_HT813_SIP_USER_ID": "agent",
    }
    app = create_app(Settings.from_env(env))
    assert app.state.outbound is None
    assert app.state.inbound is not None
    assert app.state.inbound.peer == ("192.0.2.17", 5062)
    assert app.state.inbound.sip_port != app.state.inbound.rtp_port


def test_voic_feat_001_m6_s3_backend_health_checks_both_model_endpoints():
    """Given separate endpoints, when TTS becomes unavailable, then backend health degrades."""
    from unittest.mock import AsyncMock

    env = valid_env() | {
        "VOICE_AGENT_STT_ENDPOINT": "http://127.0.0.1:8101",
        "VOICE_AGENT_TTS_ENDPOINT": "http://127.0.0.1:8102",
    }
    app = create_app(Settings.from_env(env))
    stt = app.state.runner._stt
    tts = app.state.runner._tts
    stt.ready = AsyncMock(return_value=True)
    tts.ready = AsyncMock(return_value=True)

    async def fake_start():
        app.state.retention.ready = True

    async def fake_close():
        app.state.retention.ready = False

    app.state.retention.start = fake_start
    app.state.retention.close = fake_close

    async def run():
        async with app.router.lifespan_context(app):
            health = next(route for route in app.routes if getattr(route, "path", None) == "/health")
            assert (await health.endpoint())["status"] == "ready"
            tts.ready.return_value = False
            result = await health.endpoint()
            assert result == {"status": "degraded", "stt": "ready", "tts": "unavailable"}

    asyncio.run(run())
