"""VOIC-FEAT-001 M5-S4: in-process WebSocket tests with a fake core."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_agent.channels.web.voice import web_voice_router
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import EventEnvelope, SessionState, SessionStatus


class FakeRunner:
    def __init__(self):
        self.calls = 0
        self.received = []
        self.cancelled = False

    async def run(self, context, incoming, events, send_audio, cancel):
        self.calls += 1
        async for chunk in incoming:
            self.received.append(chunk)
        self.cancelled = cancel.cancelled
        await events.publish(EventEnvelope(context.session_id, 0,
                                           SessionState(SessionStatus.COMPLETED)))
        if self.received:
            await send_audio(AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT))


def client_with_runner(runner):
    app = FastAPI()
    app.include_router(web_voice_router(runner, "private-token"))
    return TestClient(app)


def test_voic_feat_001_m5_s4_rejects_unauthorized_before_core():
    """Given missing token, when connecting, then WebSocket rejects before core call."""
    runner = FakeRunner()
    with client_with_runner(runner) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/voice", subprotocols=["voice-agent"]):
                pass
    assert runner.calls == 0


def test_voic_feat_001_m5_s4_transfers_ordered_pcm_and_event():
    """Given authorized PCM, when ended, then core gets sequence 0 and returns event/audio."""
    runner = FakeRunner()
    with client_with_runner(runner) as client:
        with client.websocket_connect(
            "/voice", subprotocols=["voice-agent", "token.private-token"]
        ) as ws:
            assert ws.accepted_subprotocol == "voice-agent"
            ws.send_json({"type": "start"})
            started = ws.receive_json()
            ws.send_bytes((0).to_bytes(4, "big") + b"\0\0")
            ws.send_json({"type": "end"})
            event = ws.receive_json()
            audio = ws.receive_bytes()
    assert event["type"] == "event"
    assert event["event"]["session_id"] == started["session_id"]
    assert audio == (0).to_bytes(4, "big") + b"\0\0"
    assert len(runner.received) == 1
    assert runner.received[0].sequence == 0


def test_voic_feat_001_m5_s4_cancel_propagates_and_closes():
    """Given cancel command, when consumed, then core sees cancelled token."""
    runner = FakeRunner()
    with client_with_runner(runner) as client:
        with client.websocket_connect(
            "/voice", subprotocols=["voice-agent", "token.private-token"]
        ) as ws:
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_json({"type": "cancel"})
            ws.receive_json()
    assert runner.cancelled


def test_voic_feat_001_m5_s4_rejects_sequence_gap():
    """Given missing sequence 0, when audio arrives, then the channel reports error."""
    runner = FakeRunner()
    with client_with_runner(runner) as client:
        with client.websocket_connect(
            "/voice", subprotocols=["voice-agent", "token.private-token"]
        ) as ws:
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_bytes((1).to_bytes(4, "big") + b"\0\0")
            error = ws.receive_json()
    assert error == {"type": "error", "code": "invalid_input"}


def test_voic_feat_001_m5_s4_disconnect_cancels_session():
    """Given dropped WebSocket, when input stream closes, then cancellation reaches core."""
    class DisconnectRunner(FakeRunner):
        async def run(self, context, incoming, events, send_audio, cancel):
            async for _ in incoming:
                pass
            self.cancelled = cancel.cancelled

    runner = DisconnectRunner()
    with client_with_runner(runner) as client:
        with client.websocket_connect(
            "/voice", subprotocols=["voice-agent", "token.private-token"]
        ) as ws:
            ws.send_json({"type": "start"})
            ws.receive_json()
    assert runner.cancelled
