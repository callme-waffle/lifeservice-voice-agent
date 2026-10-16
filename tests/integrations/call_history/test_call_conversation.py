"""VOIC-FEAT-005 M8: PRD-08 / SRS-O04 encrypted-text-to-HTTP boundary."""

from __future__ import annotations

import base64
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
    """VOIC-OPS-008 M10-S2; PRD-08/SRS-O04.

    Given two phone sessions and web records, when both phone IDs are queried,
    then final turns stay isolated, ordered, authorized, and expire.
    """
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
    other_call = SessionContext(uuid4(), Channel.HT813_FXO, START)
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
        await store.record_text(other_call, 0, "transcript", "별도 전화 질문")
        await store.record_text(other_call, 0, "response", "별도 전화 답변")
        files = list(store.transcripts_dir.glob("*.va1"))
        assert len(files) == 7
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
            assert [item["created_at"] for item in result["turns"]] == [
                START.isoformat(), (START + timedelta(seconds=1)).isoformat(),
                (START + timedelta(seconds=2)).isoformat(),
            ]
            second = await client.get(
                f"/operator/calls/{other_call.session_id}/conversation", headers=headers,
            )
            assert second.status_code == 200
            assert second.json() == {
                "session_id": str(other_call.session_id),
                "turns": [
                    {"turn_index": 0, "speaker": "user", "text": "별도 전화 질문",
                     "created_at": instant[0].isoformat()},
                    {"turn_index": 0, "speaker": "assistant", "text": "별도 전화 답변",
                     "created_at": instant[0].isoformat()},
                ],
            }
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


@pytest.mark.asyncio
@pytest.mark.parametrize("damaged_session", ["requested", "other"])
async def test_voic_ops_008_m10_s2_corrupt_text_returns_private_503(
    tmp_path: Path, caplog, damaged_session: str,
):
    """PRD-06/08, SRS-O01/O04: given two readable encrypted phone sessions,
    when either session's ciphertext is damaged, then HTTP fails with a generic
    503 and neither response nor logs expose text, paths, token, or key.
    """
    key = bytes(range(32))
    store = EncryptedRetention(
        recordings_dir=tmp_path / "private" / "recordings",
        transcripts_dir=tmp_path / "private" / "transcripts",
        audit_path=tmp_path / "private" / "deletion-audit.jsonl",
        key=key, clock=lambda: START,
    )
    await store.start()
    contexts = {name: SessionContext(uuid4(), Channel.HT813_FXO, START)
                for name in ("requested", "other")}
    texts = {name: f"합성 비공개 전사 {name}" for name in contexts}
    app = FastAPI()
    app.include_router(operator_router(OperatorCalls(None, SingleSessionGate(), TOKEN, store)))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        paths = {name: await store.record_text(context, 0, "transcript", texts[name])
                 for name, context in contexts.items()}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://localhost",
        ) as client:
            for name, context in contexts.items():
                response = await client.get(
                    f"/operator/calls/{context.session_id}/conversation", headers=headers,
                )
                assert response.status_code == 200
                assert response.json()["turns"][0]["text"] == texts[name]
            damaged = paths[damaged_session]
            blob = bytearray(damaged.read_bytes())
            blob[-1] ^= 1  # Corrupt the authentication tag after successful startup/read.
            damaged.write_bytes(blob)
            assert damaged.stat().st_mode & 0o777 == 0o600
            response = await client.get(
                f"/operator/calls/{contexts['requested'].session_id}/conversation",
                headers=headers,
            )
            assert response.status_code == 503
            assert response.json() == {"detail": "conversation history unavailable"}
            for secret in (*texts.values(), str(tmp_path), damaged.name, TOKEN,
                           key.hex(), base64.b64encode(key).decode()):
                assert secret not in response.text
                assert secret not in caplog.text
    finally:
        await store.close()
