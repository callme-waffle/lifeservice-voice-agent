"""VOIC-FEAT-001 M6-S1-T6: pure AES-GCM and fake storage policy cases."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from voice_agent.contracts.ports import RetentionUnavailable
from voice_agent.contracts.session import Channel, SessionContext
from voice_agent.infrastructure.retention import EncryptedRetention

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


def retention(clock=lambda: NOW):
    return EncryptedRetention(recordings_dir=Path("unused-audio"),
                              transcripts_dir=Path("unused-text"),
                              audit_path=Path("unused-audit.jsonl"),
                              key=b"K" * 32, clock=clock)


def test_voic_feat_001_m6_s1_t6_aes_gcm_hides_and_authenticates_content():
    """Given a final text artifact, when encoded, then content hides and tampering fails."""
    store = retention()
    plain = {"kind": "transcript", "text": "비밀 최종 전사"}
    blob = store.encode_artifact(plain, NOW)
    assert "비밀 최종 전사".encode() not in blob
    created, recovered = store.decode_artifact(blob)
    assert created == NOW and recovered == plain
    for offset in (4, 12, len(blob) - 1):
        tampered = bytearray(blob)
        tampered[offset] ^= 1
        with pytest.raises(RetentionUnavailable):
            store.decode_artifact(bytes(tampered))


def test_voic_feat_001_m6_s1_t6_expiry_is_exact_creation_plus_30_days():
    """Given UTC creation, when just before and at day 30, then only boundary expires."""
    store = retention()
    created = NOW - timedelta(days=30)
    assert not store.expired(created, NOW - timedelta(microseconds=1))
    assert store.expired(created, NOW)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_records_only_defined_artifact_kinds():
    """Given fake storage, when recording, then audio metadata and final text are constrained."""
    store = retention()
    store.ready = True
    captured = []
    def fake_write(directory, payload):
        captured.append((directory, payload))
        return Path("fake-artifact")
    store._write = fake_write
    context = SessionContext(uuid4(), Channel.HT813_FXO, NOW)
    await store.record_audio(context, 2, "input", b"\0\0")
    await store.record_text(context, 2, "transcript", "최종")
    assert captured[0][1]["format"] == {"encoding": "pcm_s16le", "sample_rate_hz": 16000,
                                         "channels": 1}
    assert captured[0][1]["direction"] == "input"
    assert captured[1][1]["kind"] == "transcript"
    assert captured[1][1]["text"] == "최종"
    with pytest.raises(ValueError):
        await store.record_text(context, 2, "partial", "부분")


def test_voic_feat_001_m6_s1_t6_failed_delete_is_audited_and_retried():
    """Given a fake unlink failure, when swept twice, then no content enters audit and retry works."""
    store = retention()
    created = NOW - timedelta(days=31)
    audit = []

    class File:
        stem = "opaque-id"
        deleted = False
        attempts = 0
        def unlink(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("private path")
            self.deleted = True

    class Directory:
        def __init__(self, files):
            self.files = files
        def glob(self, pattern):
            return [file for file in self.files if not file.deleted] if pattern == "*.va1" else []

    item = File()
    store.recordings_dir = Directory([item])
    store.transcripts_dir = Directory([])
    store.read_artifact = lambda path: (created, {"text": "private value"})
    store._audit = lambda **event: audit.append(event)
    with pytest.raises(RetentionUnavailable):
        store._sweep()
    assert audit[0]["result"] == "failed"
    assert audit[0]["reason_code"] == "unlink_failed"
    assert "private value" not in str(audit)
    assert store._sweep() == 1
    assert item.deleted
    assert audit[1]["result"] == "deleted"


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_start_and_close_scheduler_without_files():
    """Given fake storage preparation, when started and closed, then sweep precedes readiness."""
    store = retention()
    calls = []
    store._prepare = lambda: calls.append("prepare")
    store._sweep = lambda: calls.append("sweep") or 0
    await store.start()
    assert store.ready and calls == ["prepare", "sweep"]
    await store.close()
    assert not store.ready


def test_voic_feat_001_m6_s1_t6_rejects_missing_or_short_key():
    """Given no valid 256-bit key, when configured, then storage cannot start."""
    for key in (b"", b"short"):
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptedRetention(recordings_dir=Path("a"), transcripts_dir=Path("b"),
                               audit_path=Path("c"), key=key)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_write_failure_disables_storage_without_content():
    """Given a fake disk failure, when recording, then readiness fails without data leakage."""
    store = retention()
    store.ready = True
    def fail_write(directory, payload):
        raise OSError("private payload and path")
    store._write = fail_write
    context = SessionContext(uuid4(), Channel.WEB, NOW)
    with pytest.raises(RetentionUnavailable) as raised:
        await store.record_text(context, 0, "transcript", "비밀 원문")
    assert not store.ready
    assert store.last_error_code == "write_failed"
    assert "비밀 원문" not in str(raised.value)
    assert "private payload" not in str(raised.value)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_periodic_sweep_runs_after_startup():
    """Given fake scheduler, when a tick arrives, then another sweep runs without disk I/O."""
    ticked = asyncio.Event()
    sleep_calls = 0
    async def fake_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            return
        await asyncio.Event().wait()

    store = EncryptedRetention(
        recordings_dir=Path("unused-audio"), transcripts_dir=Path("unused-text"),
        audit_path=Path("unused-audit.jsonl"), key=b"K" * 32,
        clock=lambda: NOW, sleep=fake_sleep,
    )
    store._prepare = lambda: None
    sweeps = []
    def fake_sweep():
        sweeps.append(1)
        if len(sweeps) == 2:
            ticked.set()
        return 0
    store._sweep = fake_sweep
    await store.start()
    await asyncio.wait_for(ticked.wait(), 1)
    assert len(sweeps) == 2 and store.ready
    await store.close()


def test_voic_feat_001_m6_s1_t6_old_temporary_ciphertext_is_cleaned():
    """Given an orphan temporary write, when older than one hour, then delete and audit it."""
    store = retention()
    audit = []

    class Stat:
        st_mtime = (NOW - timedelta(hours=2)).timestamp()

    class Temporary:
        stem = ".opaque-id"
        deleted = False
        def stat(self):
            return Stat()
        def unlink(self):
            self.deleted = True

    class Directory:
        def __init__(self, temporary):
            self.temporary = temporary
        def glob(self, pattern):
            return [self.temporary] if pattern == ".*.tmp" and not self.temporary.deleted else []

    temp = Temporary()
    store.recordings_dir = Directory(temp)
    store.transcripts_dir = Directory(Temporary())
    store._audit = lambda **event: audit.append(event)
    assert store._sweep() == 2
    assert temp.deleted
    assert all(event["kind"] == "temporary" and event["reason_code"] == "orphan_temp"
               for event in audit)


def test_voic_feat_005_m8_s2_t1_orders_only_matching_final_text():
    """Given mixed retained turns, when looked up, then only matching final text stays ordered."""
    session_id, other_id = uuid4(), uuid4()
    store = retention()
    store.ready = True

    class Directory:
        def glob(self, pattern):
            assert pattern == "*.va1"
            return [Path(str(index)) for index in range(4)]

    store.transcripts_dir = Directory()
    entries = [
        (NOW + timedelta(seconds=3), {"session_id": str(session_id), "kind": "response",
                                     "turn_index": 1, "text": "답변"}),
        (NOW + timedelta(seconds=1), {"session_id": str(session_id), "kind": "transcript",
                                     "turn_index": 0, "text": "질문"}),
        (NOW + timedelta(seconds=2), {"session_id": str(other_id), "kind": "transcript",
                                     "turn_index": 0, "text": "다른 통화"}),
        (NOW + timedelta(seconds=3), {"session_id": str(session_id), "kind": "transcript",
                                     "turn_index": 1, "text": "후속 질문"}),
    ]
    store.read_artifact = lambda path: entries[int(path.name)]
    result = store.list_conversation(session_id)
    assert result["session_id"] == str(session_id)
    assert [(turn["turn_index"], turn["speaker"], turn["text"]) for turn in result["turns"]] == [
        (0, "user", "질문"), (1, "user", "후속 질문"), (1, "assistant", "답변"),
    ]


def test_voic_feat_005_m8_s2_t1_rejects_corrupt_text_without_leaking():
    """Given a malformed retained file, when queried, then it fails without original text."""
    store = retention()
    store.ready = True
    store.transcripts_dir = type("Directory", (), {"glob": lambda self, _: [Path("0")]})()
    store.read_artifact = lambda path: (NOW, {"session_id": str(uuid4()),
                                                    "kind": "response", "turn_index": -1,
                                                    "text": "비밀 원문"})
    with pytest.raises(RetentionUnavailable) as raised:
        store.list_conversation(uuid4())
    assert "비밀 원문" not in str(raised.value)
