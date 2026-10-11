"""VOIC-FEAT-001 M6-S2: PRD-06 / SRS-O01 encrypted file boundary."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import pytest

from voice_agent.contracts.ports import RetentionUnavailable
from voice_agent.contracts.session import Channel, SessionContext
from voice_agent.infrastructure.retention import EncryptedRetention


CREATED = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
TEST_KEY = bytes(range(32))  # Synthetic test key, never an operational secret.
TEST_CONTEXT = SessionContext(UUID("00000000-0000-4000-8000-000000000001"), Channel.WEB, CREATED)


def storage(root: Path, clock, *, sleep=asyncio.sleep) -> EncryptedRetention:
    return EncryptedRetention(
        recordings_dir=root / "private" / "recordings",
        transcripts_dir=root / "private" / "transcripts",
        audit_path=root / "private" / "deletion-audit.jsonl",
        key=TEST_KEY, clock=clock, sleep=sleep,
    )


def private_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_private_files_encrypt_audio_and_final_text():
    """PRD-06/SRS-O01: given synthetic artifacts, when saved, then files stay private and authenticated."""
    with TemporaryDirectory(prefix="voic-m6-retention-", dir="/tmp") as folder:
        root = Path(folder)
        store = storage(root, lambda: CREATED)
        await store.start()
        try:
            assert private_mode(root / "private") == 0o700
            assert private_mode(store.recordings_dir) == 0o700
            assert private_mode(store.transcripts_dir) == 0o700
            assert private_mode(store.audit_path) == 0o600

            pcm = b"ABCD" * 16
            files = [
                await store.record_audio(TEST_CONTEXT, 0, "input", pcm),
                await store.record_audio(TEST_CONTEXT, 0, "output", pcm),
                await store.record_text(TEST_CONTEXT, 0, "transcript", "합성 최종 전사"),
                await store.record_text(TEST_CONTEXT, 0, "response", "합성 응답"),
            ]
            assert len(set(files)) == 4
            assert not list(store.recordings_dir.glob(".*.tmp"))
            assert not list(store.transcripts_dir.glob(".*.tmp"))
            for path in files:
                assert private_mode(path) == 0o600
                assert path.suffix == ".va1"
                raw = path.read_bytes()
                assert b"ABCD" not in raw
                assert "합성 최종 전사".encode() not in raw
                assert "합성 응답".encode() not in raw
                created, payload = store.read_artifact(path)
                assert created == CREATED
                assert payload["session_id"] == str(TEST_CONTEXT.session_id)
                assert payload["turn_index"] == 0
                if payload["kind"] == "audio":
                    assert payload["direction"] in ("input", "output")
                else:
                    assert payload["text"] in ("합성 최종 전사", "합성 응답")

            damaged = bytearray(files[2].read_bytes())
            damaged[4] ^= 1
            with pytest.raises(RetentionUnavailable):
                store.decode_artifact(bytes(damaged))
        finally:
            await store.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_startup_sweep_deletes_at_exact_day_30():
    """PRD-06/SRS-O01: given a real file, when restarting at day 30, then expiry and audit are exact."""
    with TemporaryDirectory(prefix="voic-m6-retention-", dir="/tmp") as folder:
        root = Path(folder)
        first = storage(root, lambda: CREATED)
        await first.start()
        path = await first.record_text(TEST_CONTEXT, 0, "transcript", "합성 최종 전사")
        await first.close()

        before = storage(root, lambda: CREATED + timedelta(days=30, microseconds=-1))
        await before.start()
        assert path.exists()
        await before.close()

        boundary = storage(root, lambda: CREATED + timedelta(days=30))
        await boundary.start()
        try:
            assert not path.exists()
            events = [json.loads(line) for line in boundary.audit_path.read_text().splitlines()]
            assert len(events) == 1
            assert events[0]["result"] == "deleted"
            assert events[0]["kind"] == "text"
            assert set(events[0]) == {
                "artifact_id", "kind", "created_at_utc", "deleted_at_utc",
                "result", "reason_code",
            }
            assert "합성" not in boundary.audit_path.read_text()
        finally:
            await boundary.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_periodic_sweep_deletes_real_file():
    """PRD-06/SRS-O01: given a live store, when its scheduled tick arrives, then an expired file goes."""
    with TemporaryDirectory(prefix="voic-m6-retention-", dir="/tmp") as folder:
        instant = [CREATED]
        tick = asyncio.Event()
        swept = asyncio.Event()

        async def controlled_sleep(_: float) -> None:
            await tick.wait()
            tick.clear()

        store = storage(Path(folder), lambda: instant[0], sleep=controlled_sleep)
        actual_sweep = store.sweep
        calls = 0

        async def measured_sweep() -> int:
            nonlocal calls
            calls += 1
            result = await actual_sweep()
            if calls == 2:
                swept.set()
            return result

        store.sweep = measured_sweep
        await store.start()
        try:
            path = await store.record_text(TEST_CONTEXT, 0, "response", "합성 응답")
            instant[0] = CREATED + timedelta(days=30)
            tick.set()
            await asyncio.wait_for(swept.wait(), timeout=2)
            assert not path.exists()
            assert store.ready
            assert json.loads(store.audit_path.read_text().splitlines()[0])["result"] == "deleted"
        finally:
            await store.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_rejects_broad_permissions_and_symlink():
    """PRD-06/SRS-O01: given unsafe storage paths, when starting, then readiness is denied."""
    with TemporaryDirectory(prefix="voic-m6-retention-", dir="/tmp") as folder:
        root = Path(folder)
        broad = storage(root, lambda: CREATED)
        broad.recordings_dir.mkdir(parents=True)
        broad.recordings_dir.chmod(0o755)
        with pytest.raises(RetentionUnavailable):
            await broad.start()
        assert not broad.ready

        target = root / "real"
        target.mkdir(mode=0o700)
        link = root / "link"
        link.symlink_to(target, target_is_directory=True)
        linked = EncryptedRetention(
            recordings_dir=link, transcripts_dir=root / "text",
            audit_path=root / "audit.jsonl", key=TEST_KEY, clock=lambda: CREATED,
        )
        with pytest.raises(RetentionUnavailable):
            await linked.start()
        assert not linked.ready


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_delete_failure_retries_and_cleans_orphan(monkeypatch):
    """PRD-06/SRS-O01: given a failed unlink and old temp, when retried, then both are audited."""
    with TemporaryDirectory(prefix="voic-m6-retention-", dir="/tmp") as folder:
        instant = [CREATED]
        store = storage(Path(folder), lambda: instant[0])
        await store.start()
        try:
            path = await store.record_text(TEST_CONTEXT, 0, "transcript", "합성 최종 전사")
            instant[0] = CREATED + timedelta(days=30)
            original_unlink = Path.unlink
            failures = [0]

            def fail_once(candidate: Path, *args, **kwargs):
                if candidate == path and failures[0] == 0:
                    failures[0] += 1
                    raise OSError("synthetic unlink failure")
                return original_unlink(candidate, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(Path, "unlink", fail_once)
                with pytest.raises(RetentionUnavailable):
                    await store.sweep()
            assert path.exists() and not store.ready
            assert store.last_error_code == "sweep_failed"
            await store.sweep()
            assert not path.exists() and store.ready

            orphan = store.recordings_dir / ".orphan.tmp"
            descriptor = os.open(orphan, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(store.encode_artifact({"text": "합성 임시 내용"}, CREATED))
            old = (instant[0] - timedelta(hours=2)).timestamp()
            os.utime(orphan, (old, old))
            assert await store.sweep() == 1
            assert not orphan.exists()

            audit = store.audit_path.read_text()
            events = [json.loads(line) for line in audit.splitlines()]
            assert [event["result"] for event in events] == ["failed", "deleted", "deleted"]
            assert events[0]["reason_code"] == "unlink_failed"
            assert events[2]["reason_code"] == "orphan_temp"
            assert "합성" not in audit and "synthetic unlink failure" not in audit
            assert all(set(event) == {
                "artifact_id", "kind", "created_at_utc", "deleted_at_utc",
                "result", "reason_code",
            } for event in events)
        finally:
            await store.close()
