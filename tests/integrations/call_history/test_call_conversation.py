"""VOIC-FEAT-005 M8: PRD-08 / SRS-O04 encrypted-text-to-HTTP boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import Channel, SessionContext
from voice_agent.infrastructure.retention import EncryptedRetention

START = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)
TOKEN = "synthetic-operator-token"


@pytest.mark.asyncio
async def test_voic_feat_005_m8_s3_prd08_srs_o04_conversation_boundary(tmp_path: Path):
    """Given two synthetic calls, when queried, then authorized turns retain order and expire."""
    instant = [START]
    store = EncryptedRetention(
        recordings_dir=tmp_path / "private" / "recordings",
        transcripts_dir=tmp_path / "private" / "transcripts",
        audit_path=tmp_path / "private" / "deletion-audit.jsonl",
        key=bytes(range(32)), clock=lambda: instant[0],
    )
    await store.start()
    call = SessionContext(uuid4(), Channel.HT813_FXO, START)
    other = SessionContext(uuid4(), Channel.WEB, START)
    web_same_id = SessionContext(call.session_id, Channel.WEB, START)
    app = FastAPI()
    app.include_router(operator_router(OperatorCalls(None, SingleSessionGate(), TOKEN, store)))
    path = f"/operator/calls/{call.session_id}/conversation"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        await store.record_text(call, 0, "transcript", "합성 첫 질문")
        instant[0] += timedelta(seconds=1)
        await store.record_text(call, 0, "response", "합성 첫 답변")
        instant[0] += timedelta(seconds=1)
        await store.record_text(call, 1, "transcript", "합성 후속 질문")
        await store.record_text(other, 0, "transcript", "다른 통화의 비공개 질문")
        await store.record_text(web_same_id, 0, "transcript", "같은 ID의 웹 전사")
        files = list(store.transcripts_dir.glob("*.va1"))
        assert len(files) == 5
        assert all("합성".encode() not in item.read_bytes() for item in files)
        assert all("합성" not in item.name for item in files)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://localhost",
        ) as client:
            assert (await client.get(path)).status_code == 401
            response = await client.get(path, headers=headers)
            assert response.status_code == 200
            result = response.json()
            assert result["session_id"] == str(call.session_id)
            assert [(item["turn_index"], item["speaker"], item["text"])
                    for item in result["turns"]] == [
                        (0, "user", "합성 첫 질문"),
                        (0, "assistant", "합성 첫 답변"),
                        (1, "user", "합성 후속 질문"),
                    ]
            assert all("created_at" in item for item in result["turns"])
            assert (await client.get(f"/operator/calls/{uuid4()}/conversation",
                                     headers=headers)).status_code == 404
            instant[0] = START + timedelta(days=30, seconds=3)
            await store.sweep()
            assert (await client.get(path, headers=headers)).status_code == 404

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("192.0.2.4", 1234)),
            base_url="http://localhost",
        ) as remote:
            assert (await remote.get(path, headers=headers)).status_code == 403
    finally:
        await store.close()
