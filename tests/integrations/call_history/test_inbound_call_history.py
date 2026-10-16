"""VOIC-FEAT-004 M7: PRD-07 / SRS-I06 synthetic SIP-to-encrypted-file-to-HTTP boundary."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.channels.ht813.sip import request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import Channel, SessionContext
from voice_agent.infrastructure.retention import EncryptedRetention

PEER = ("192.0.2.17", 5062)
LOCAL = "192.0.2.50"
TOKEN = "synthetic-operator-token"
START = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)


class FakeMedia:
    def __init__(self, session_id, *, local_host, local_port):
        self.local_port = local_port

    def start(self, host, port, codec, telephone):
        pass

    async def close(self):
        pass


def packet(method: str, call_id: str, caller: str) -> bytes:
    headers = {
        "Via": "SIP/2.0/UDP 192.0.2.17:5062;branch=z9hG4bKsynthetic",
        "From": f"<sip:{caller}@192.0.2.17>;tag=synthetic",
        "To": f"<sip:agent@{LOCAL}:5061>",
        "Call-ID": call_id,
        "CSeq": f"1 {method}",
    }
    body = b""
    if method == "INVITE":
        headers["Content-Type"] = "application/sdp"
        body = ("v=0\r\no=- 1 1 IN IP4 192.0.2.17\r\ns=test\r\n"
                "c=IN IP4 192.0.2.17\r\nt=0 0\r\n"
                "m=audio 3000 RTP/AVP 0\r\n").encode()
    return request_bytes(method, f"sip:agent@{LOCAL}:5061", headers, body)


@pytest.mark.asyncio
async def test_voic_feat_004_m7_s3_prd07_srs_i06_inbound_history(tmp_path: Path):
    """VOIC-OPS-008 M10-S2; PRD-07/08, SRS-I06/O04.

    Given two silent synthetic calls, when queried before and after cancellation,
    then start-only metadata is incomplete, ended metadata persists without an
    invented conversation, and authorized pages retain order and expire.
    """
    instant = [START]
    store = EncryptedRetention(
        recordings_dir=tmp_path / "private" / "recordings",
        transcripts_dir=tmp_path / "private" / "transcripts",
        calls_dir=tmp_path / "private" / "calls",
        audit_path=tmp_path / "private" / "deletion-audit.jsonl",
        key=bytes(range(32)), clock=lambda: instant[0],
    )
    await store.start()
    sent: list[bytes] = []

    async def send(data, destination):
        assert destination == PEER
        sent.append(data)

    gate = SingleSessionGate()
    inbound = InboundSIPService(
        peer_host=PEER[0], peer_port=PEER[1], local_host=LOCAL,
        sip_port=5061, rtp_port=4002, user_id="agent",
        runner=object(), gate=gate, boundary=TurnBoundary(400, 100, 2000),
        retention=store, media_factory=FakeMedia, send_packet=send,
    )
    app = FastAPI()
    app.include_router(operator_router(OperatorCalls(None, gate, TOKEN, store)))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        for index, caller in enumerate(("01012345678", "anonymous")):
            call_id = f"synthetic-{index}"
            await inbound.handle_packet(packet("INVITE", call_id, caller), PEER)
            session_id = gate.active_session_id
            assert session_id is not None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
                base_url="http://localhost",
            ) as client:
                started = await client.get("/operator/inbound-calls", headers=headers)
                assert started.status_code == 200
                assert started.json()["items"][0] == {
                    "session_id": str(session_id), "started_at": instant[0].isoformat(),
                    "ended_at": None, "status": "incomplete",
                    "caller_number": caller if index == 0 else None,
                }
            await inbound.handle_packet(packet("CANCEL", call_id, caller), PEER)
            async def wait_for_release():
                while gate.active_session_id is not None:
                    await asyncio.sleep(.01)

            await asyncio.wait_for(wait_for_release(), timeout=4)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
                base_url="http://localhost",
            ) as client:
                ended = await client.get("/operator/inbound-calls", headers=headers)
                assert ended.status_code == 200
                assert ended.json()["items"][0] == {
                    "session_id": str(session_id), "started_at": instant[0].isoformat(),
                    "ended_at": instant[0].isoformat(), "status": "ended",
                    "caller_number": caller if index == 0 else None,
                }
                silent = await client.get(
                    f"/operator/calls/{session_id}/conversation", headers=headers,
                )
                assert silent.status_code == 404
                assert silent.json() == {"detail": "conversation not found"}
                assert not list(store.transcripts_dir.glob("*.va1"))
            instant[0] += timedelta(seconds=1)

        files = list(store.calls_dir.glob("*.va1"))
        assert len(files) == 4
        assert all(b"01012345678" not in path.read_bytes() for path in files)
        assert all("01012345678" not in path.name for path in files)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://localhost",
        ) as client:
            assert (await client.get("/operator/inbound-calls")).status_code == 401
            first = await client.get("/operator/inbound-calls?limit=1", headers=headers)
            assert first.status_code == 200
            assert first.json()["next_offset"] == 1
            assert first.json()["items"][0]["caller_number"] is None
            second = await client.get("/operator/inbound-calls?limit=1&offset=1", headers=headers)
            assert second.status_code == 200
            assert second.json()["items"][0]["caller_number"] == "01012345678"
            assert second.json()["items"][0]["status"] == "ended"
            assert second.json()["next_offset"] is None

            instant[0] = START + timedelta(days=30, seconds=2)
            await store.sweep()
            expired = await client.get("/operator/inbound-calls", headers=headers)
            assert expired.status_code == 200
            assert expired.json() == {"items": [], "next_offset": None}
    finally:
        await inbound.close()
        await store.close()


@pytest.mark.asyncio
async def test_voic_ops_008_m10_s2_corrupt_call_returns_private_503(tmp_path: Path, caplog):
    """PRD-06/07, SRS-O01/I06: given readable encrypted call metadata,
    when its ciphertext is damaged after startup, then HTTP returns generic 503
    without exposing caller number, file path, token, or key in response/logs.
    """
    key = bytes(range(32))
    caller = "01012345678"  # Synthetic test number only.
    store = EncryptedRetention(
        recordings_dir=tmp_path / "private" / "recordings",
        transcripts_dir=tmp_path / "private" / "transcripts",
        calls_dir=tmp_path / "private" / "calls",
        audit_path=tmp_path / "private" / "deletion-audit.jsonl",
        key=key, clock=lambda: START,
    )
    await store.start()
    context = SessionContext(uuid4(), Channel.HT813_FXO, START)
    app = FastAPI()
    app.include_router(operator_router(OperatorCalls(None, SingleSessionGate(), TOKEN, store)))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        path = await store.record_call_start(context, caller)
        await store.record_call_end(context, "ended")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://localhost",
        ) as client:
            before = await client.get("/operator/inbound-calls", headers=headers)
            assert before.status_code == 200
            assert before.json()["items"][0]["caller_number"] == caller
            blob = bytearray(path.read_bytes())
            blob[-1] ^= 1
            path.write_bytes(blob)
            assert path.stat().st_mode & 0o777 == 0o600
            response = await client.get("/operator/inbound-calls", headers=headers)
            assert response.status_code == 503
            assert response.json() == {"detail": "call history unavailable"}
            for secret in (caller, str(tmp_path), path.name, TOKEN, key.hex(),
                           base64.b64encode(key).decode()):
                assert secret not in response.text
                assert secret not in caplog.text
    finally:
        await store.close()
