"""Local AES-GCM artifacts and 30-day deletion for VOIC-FEAT-001 ADR-008."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
import struct
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from voice_agent.contracts.ports import RetentionUnavailable
from voice_agent.contracts.session import SessionContext

_MAGIC = b"VA1\0"
_HEADER_LENGTH = 24
_RETENTION_US = 30 * 24 * 60 * 60 * 1_000_000
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class EncryptedRetention:
    def __init__(
        self, *, recordings_dir: Path, transcripts_dir: Path, audit_path: Path,
        key: bytes, calls_dir: Path | None = None, sweep_interval_s: int = 3600,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("VOICE_AGENT_DATA_ENCRYPTION_KEY must decode to 32 bytes")
        if not 60 <= sweep_interval_s <= 86_400:
            raise ValueError("retention sweep interval must be 60..86400 seconds")
        self.recordings_dir = Path(recordings_dir)
        self.transcripts_dir = Path(transcripts_dir)
        self.calls_dir = Path(calls_dir) if calls_dir is not None else self.transcripts_dir.parent / "calls"
        self.audit_path = Path(audit_path)
        self._aes = AESGCM(key)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.sweep_interval_s = sweep_interval_s
        self._sleep = sleep
        self.ready = False
        self.last_error_code: str | None = None
        self._sweeper: asyncio.Task[None] | None = None

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(None):
            raise RetentionUnavailable("retention clock is not UTC")
        return now

    @staticmethod
    def _utc_us(value: datetime) -> int:
        delta = value - _EPOCH
        return ((delta.days * 86_400 + delta.seconds) * 1_000_000
                + delta.microseconds)

    @staticmethod
    def _private_dir(path: Path) -> None:
        if path.is_symlink():
            raise RetentionUnavailable("retention directory is a symlink")
        if not path.exists():
            missing: list[Path] = []
            current = path
            while not current.exists():
                missing.append(current)
                current = current.parent
            if current.is_symlink() or not current.is_dir():
                raise RetentionUnavailable("retention parent is unavailable")
            for directory in reversed(missing):
                directory.mkdir(mode=0o700)
        if not path.is_dir() or path.stat().st_mode & 0o077:
            raise RetentionUnavailable("retention directory permissions are too broad")

    def _prepare(self) -> None:
        for path in (self.recordings_dir, self.transcripts_dir, self.calls_dir,
                     self.audit_path.parent):
            self._private_dir(path)
        if self.audit_path.is_symlink():
            raise RetentionUnavailable("deletion audit is a symlink")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.audit_path, flags, 0o600)
        try:
            if os.fstat(fd).st_mode & 0o077:
                raise RetentionUnavailable("deletion audit permissions are too broad")
        finally:
            os.close(fd)

    async def start(self) -> None:
        if self._sweeper is not None:
            return
        try:
            await asyncio.to_thread(self._prepare)
            await self.sweep()
        except Exception:
            self.ready = False
            self.last_error_code = "startup_failed"
            raise RetentionUnavailable("retention startup failed") from None
        self.ready = True
        self._sweeper = asyncio.create_task(self._periodic())

    async def close(self) -> None:
        self.ready = False
        if self._sweeper is not None:
            self._sweeper.cancel()
            await asyncio.gather(self._sweeper, return_exceptions=True)
            self._sweeper = None

    async def _periodic(self) -> None:
        while True:
            try:
                await self._sleep(self.sweep_interval_s)
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.ready = False
                self.last_error_code = "sweep_failed"

    def encode_artifact(self, payload: dict[str, object], created: datetime) -> bytes:
        if created.tzinfo is None or created.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("artifact creation time must be UTC")
        created_us = self._utc_us(created)
        nonce = os.urandom(12)
        header = _MAGIC + struct.pack("!Q", created_us) + nonce
        clear = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return header + self._aes.encrypt(nonce, clear, header)

    def decode_artifact(self, blob: bytes) -> tuple[datetime, dict[str, object]]:
        if len(blob) < _HEADER_LENGTH + 16 or blob[:4] != _MAGIC:
            raise RetentionUnavailable("invalid retention artifact")
        header = blob[:_HEADER_LENGTH]
        created_us = struct.unpack("!Q", header[4:12])[0]
        try:
            clear = self._aes.decrypt(header[12:24], blob[_HEADER_LENGTH:], header)
            value = json.loads(clear)
            if not isinstance(value, dict):
                raise ValueError
            return _EPOCH + timedelta(microseconds=created_us), value
        except (InvalidTag, ValueError, OverflowError):
            raise RetentionUnavailable("invalid retention artifact") from None

    def _write(self, directory: Path, payload: dict[str, object]) -> Path:
        blob = self.encode_artifact(payload, self._now())
        identifier = uuid4().hex
        target = directory / f"{identifier}.va1"
        temporary = directory / f".{identifier}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(temporary, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    async def _record(self, directory: Path, payload: dict[str, object]) -> Path:
        if not self.ready:
            raise RetentionUnavailable("retention is unavailable")
        try:
            return await asyncio.to_thread(self._write, directory, payload)
        except Exception:
            self.ready = False
            self.last_error_code = "write_failed"
            raise RetentionUnavailable("retention write failed") from None

    async def record_audio(
        self, context: SessionContext, turn_index: int,
        direction: str, pcm: bytes,
    ) -> Path:
        if direction not in ("input", "output") or turn_index < 0 or not pcm or len(pcm) % 2:
            raise ValueError("invalid audio artifact")
        return await self._record(self.recordings_dir, {
            "session_id": str(context.session_id), "channel": context.channel.value,
            "turn_index": turn_index, "kind": "audio", "direction": direction,
            "format": {"encoding": "pcm_s16le", "sample_rate_hz": 16000, "channels": 1},
            "data_b64": base64.b64encode(pcm).decode("ascii"),
        })

    async def record_text(
        self, context: SessionContext, turn_index: int,
        kind: str, value: str,
    ) -> Path:
        if kind not in ("transcript", "response") or turn_index < 0 or not value.strip():
            raise ValueError("invalid text artifact")
        return await self._record(self.transcripts_dir, {
            "session_id": str(context.session_id), "channel": context.channel.value,
            "turn_index": turn_index, "kind": kind, "text": value,
        })

    def read_artifact(self, path: Path) -> tuple[datetime, dict[str, object]]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                mode = os.fstat(stream.fileno()).st_mode
                if not stat.S_ISREG(mode) or mode & 0o077:
                    raise RetentionUnavailable("invalid retention artifact")
                return self.decode_artifact(stream.read())
        except OSError:
            raise RetentionUnavailable("invalid retention artifact") from None

    async def record_call_start(self, context: SessionContext,
                                caller_number: str | None) -> Path:
        """Record an accepted inbound call even when no speech turn occurs."""
        return await self._record(self.calls_dir, {
            "kind": "call_event", "event": "started",
            "session_id": str(context.session_id), "caller_number": caller_number,
        })

    async def record_call_end(self, context: SessionContext, status: str) -> Path:
        if status not in ("ended", "failed"):
            raise ValueError("invalid call status")
        return await self._record(self.calls_dir, {
            "kind": "call_event", "event": status,
            "session_id": str(context.session_id),
        })

    def list_inbound_calls(self, *, limit: int = 50, offset: int = 0) -> dict[str, object]:
        """Return bounded newest-first call metadata without exposing file paths."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid call history page")
        if not self.ready:
            raise RetentionUnavailable("retention is unavailable")
        starts: dict[str, tuple[datetime, str | None]] = {}
        ends: dict[str, tuple[datetime, str]] = {}
        now = self._now()
        for path in self.calls_dir.glob("*.va1"):
            created, payload = self.read_artifact(path)
            if self.expired(created, now):
                continue
            try:
                if payload.get("kind") != "call_event":
                    raise ValueError
                session_id = str(UUID(str(payload["session_id"])))
                event = payload["event"]
                if event == "started":
                    caller_number = payload["caller_number"]
                    if caller_number is not None and not isinstance(caller_number, str):
                        raise ValueError
                    if session_id not in starts or starts[session_id][0] < created:
                        starts[session_id] = (created, caller_number)
                elif event in ("ended", "failed"):
                    if session_id not in ends or ends[session_id][0] < created:
                        ends[session_id] = (created, event)
                else:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise RetentionUnavailable("invalid call history artifact") from None
        rows = []
        for session_id, (started, caller_number) in starts.items():
            end = ends.get(session_id)
            rows.append({
                "session_id": session_id, "started_at": started.isoformat(),
                "ended_at": end[0].isoformat() if end else None,
                "status": end[1] if end else "incomplete",
                "caller_number": caller_number,
            })
        rows.sort(key=lambda item: (item["started_at"], item["session_id"]), reverse=True)
        page = rows[offset:offset + limit]
        next_offset = offset + limit if offset + limit < len(rows) else None
        return {"items": page, "next_offset": next_offset}

    @staticmethod
    def expired(created: datetime, now: datetime) -> bool:
        return (EncryptedRetention._utc_us(created) + _RETENTION_US
                <= EncryptedRetention._utc_us(now))

    def _audit(self, *, identifier: str, kind: str, created: datetime | None,
               result: str, reason_code: str | None) -> None:
        event = {
            "artifact_id": identifier, "kind": kind,
            "created_at_utc": created.isoformat() if created else None,
            "deleted_at_utc": self._now().isoformat(),
            "result": result, "reason_code": reason_code,
        }
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.audit_path, flags)
        with os.fdopen(fd, "wb") as stream:
            stream.write((json.dumps(event, separators=(",", ":")) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())

    def _sweep(self) -> int:
        deleted = 0
        failed = False
        for directory, kind in ((self.recordings_dir, "audio"),
                                (self.transcripts_dir, "text"),
                                (self.calls_dir, "call")):
            for path in directory.glob("*.va1"):
                identifier = path.stem
                try:
                    created, _ = self.read_artifact(path)
                except (OSError, RetentionUnavailable):
                    self._audit(identifier=identifier, kind=kind, created=None,
                                result="failed", reason_code="invalid_record")
                    failed = True
                    continue
                if not self.expired(created, self._now()):
                    continue
                try:
                    path.unlink()
                except OSError:
                    self._audit(identifier=identifier, kind=kind, created=created,
                                result="failed", reason_code="unlink_failed")
                    failed = True
                    continue
                self._audit(identifier=identifier, kind=kind, created=created,
                            result="deleted", reason_code=None)
                deleted += 1
        # An interrupted atomic write can leave ciphertext in a hidden temporary file.
        # Never remove a possibly active writer's file during the first hour.
        for directory in (self.recordings_dir, self.transcripts_dir, self.calls_dir):
            for path in directory.glob(".*.tmp"):
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                    if self._now() - modified < timedelta(hours=1):
                        continue
                    path.unlink()
                    self._audit(identifier=path.stem.lstrip("."), kind="temporary",
                                created=modified, result="deleted", reason_code="orphan_temp")
                    deleted += 1
                except OSError:
                    self._audit(identifier=path.stem.lstrip("."), kind="temporary",
                                created=None, result="failed", reason_code="temp_cleanup_failed")
                    failed = True
        if failed:
            raise RetentionUnavailable("retention deletion failed")
        return deleted

    async def sweep(self) -> int:
        try:
            deleted = await asyncio.to_thread(self._sweep)
            self.last_error_code = None
            self.ready = True
            return deleted
        except Exception:
            self.ready = False
            self.last_error_code = "sweep_failed"
            raise RetentionUnavailable("retention sweep failed") from None
