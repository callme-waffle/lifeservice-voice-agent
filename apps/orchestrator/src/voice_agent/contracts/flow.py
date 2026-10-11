"""Single-session admission and bounded audio flow for VOIC-FEAT-001."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from .media import AudioChunk

T = TypeVar("T")


class OperationCancelled(Exception):
    """Raised when an in-flight contract operation is cancelled."""


class SessionBusy(Exception):
    """Raised when another web or telephone session owns the sole slot."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled()


class BoundedAudioBuffer:
    """One producer/consumer FIFO; put awaits room and cancellation wakes waiters."""

    def __init__(self, session_id: UUID, capacity: int, cancel: CancellationToken) -> None:
        if capacity < 1:
            raise ValueError("audio buffer capacity must be positive")
        self.session_id = session_id
        self._queue: asyncio.Queue[AudioChunk | None] = asyncio.Queue(maxsize=capacity)
        self._cancel = cancel
        self._next_sequence = 0
        self._finished = False
        self._eof_seen = False

    async def _wait_or_cancel(self, operation_factory: Callable[[], Awaitable[T]]) -> T:
        self._cancel.raise_if_cancelled()
        operation = asyncio.create_task(operation_factory())
        cancelled = asyncio.create_task(self._cancel.wait())
        try:
            await asyncio.wait({operation, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            self._cancel.raise_if_cancelled()
            return await operation
        finally:
            for task in (operation, cancelled):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)

    async def send(self, chunk: AudioChunk) -> None:
        if self._finished:
            raise RuntimeError("audio buffer is finished")
        if chunk.session_id != self.session_id:
            raise ValueError("audio session does not match buffer")
        if chunk.sequence != self._next_sequence:
            raise ValueError("audio sequence must be contiguous from zero")
        await self._wait_or_cancel(lambda: self._queue.put(chunk))
        self._next_sequence += 1

    async def receive(self) -> AudioChunk | None:
        self._cancel.raise_if_cancelled()
        if self._eof_seen:
            return None
        item = await self._wait_or_cancel(self._queue.get)
        if item is None:
            self._eof_seen = True
        return item

    async def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        await self._wait_or_cancel(lambda: self._queue.put(None))

    def cancel(self) -> None:
        self._cancel.cancel()
        while not self._queue.empty():
            self._queue.get_nowait()


@dataclass(slots=True)
class SessionLease:
    _gate: SingleSessionGate
    session_id: UUID
    _released: bool = False

    async def __aenter__(self) -> SessionLease:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        await self._gate.release(self.session_id)
        self._released = True


class SingleSessionGate:
    """One active session across web and telephone channels."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: UUID | None = None

    @property
    def active_session_id(self) -> UUID | None:
        return self._active

    async def acquire(self, session_id: UUID) -> SessionLease:
        async with self._lock:
            if self._active is not None:
                raise SessionBusy("another session is active")
            self._active = session_id
        return SessionLease(self, session_id)

    async def release(self, session_id: UUID) -> None:
        async with self._lock:
            if self._active != session_id:
                raise ValueError("session does not own the gate")
            self._active = None
