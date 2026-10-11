"""VOIC-FEAT-004 M7: PRD-07 / SRS-I06 synthetic SIP-to-encrypted-file-to-HTTP boundary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.channels.ht813.sip import request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import SingleSessionGate
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
    """Given two synthetic calls, when queried, then only authorized encrypted recent metadata is returned."""
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
    try:
        for index, caller in enumerate(("01012345678", "anonymous")):
            call_id = f"synthetic-{index}"
            await inbound.handle_packet(packet("INVITE", call_id, caller), PEER)
            await inbound.handle_packet(packet("CANCEL", call_id, caller), PEER)
            async def wait_for_release():
                while gate.active_session_id is not None:
                    await asyncio.sleep(.01)

            await asyncio.wait_for(wait_for_release(), timeout=4)
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
