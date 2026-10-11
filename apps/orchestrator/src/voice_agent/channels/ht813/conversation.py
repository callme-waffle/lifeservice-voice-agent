"""Shared RTP-to-voice conversation for HT813 inbound and outbound calls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Protocol
from uuid import UUID

from voice_agent.channels.ht813.turns import SpeechTurnDetector, TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SessionLease
from voice_agent.contracts.media import AudioChunk, DtmfEvent
from voice_agent.contracts.ports import EventSink, PhoneSessionRunner
from voice_agent.contracts.session import CallState, CallStatus, EventEnvelope, SessionContext


class PhoneMedia(Protocol):
    async def receive_audio(self) -> AudioChunk: ...
    async def receive_dtmf(self) -> DtmfEvent: ...
    async def send_audio(self, chunk: AudioChunk) -> None: ...


class SequencedCallEvents:
    def __init__(self, session_id: UUID, target: EventSink) -> None:
        self.session_id, self.target = session_id, target
        self.active = asyncio.Event()
        self.final_status: CallStatus | None = None
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def publish(self, event: EventEnvelope) -> None:
        if event.session_id != self.session_id:
            raise ValueError("call event belongs to another session")
        async with self._lock:
            await self.target.publish(EventEnvelope(
                self.session_id, self._sequence, event.payload,
            ))
            self._sequence += 1
            if isinstance(event.payload, CallState):
                if event.payload.status is CallStatus.ACTIVE:
                    self.active.set()
                if event.payload.status in (CallStatus.ENDED, CallStatus.FAILED, CallStatus.BUSY):
                    self.final_status = event.payload.status


class PhoneMediaConversation:
    def __init__(self, media: PhoneMedia, runner: PhoneSessionRunner,
                 boundary: TurnBoundary) -> None:
        self.media, self.runner, self.boundary = media, runner, boundary

    async def run(
        self, context: SessionContext, sink: EventSink, cancel: CancellationToken,
        lease: SessionLease, ended_normally: Callable[[], bool],
    ) -> None:
        ready = asyncio.Event()
        ready.set()
        detector = SpeechTurnDetector(self.boundary)
        complete: asyncio.Queue[tuple[AudioChunk, ...]] = asyncio.Queue(maxsize=1)

        async def receive_audio() -> None:
            try:
                while not cancel.cancelled:
                    chunk = await self.media.receive_audio()
                    if ready.is_set():
                        turn = detector.feed(chunk)
                        if turn is not None:
                            ready.clear()
                            complete.put_nowait(turn)
            except asyncio.CancelledError:
                raise
            except Exception:
                cancel.cancel()

        async def receive_dtmf() -> None:
            try:
                while not cancel.cancelled:
                    event = await self.media.receive_dtmf()
                    await sink.publish(EventEnvelope(context.session_id, 0, event))
            except asyncio.CancelledError:
                raise
            except Exception:
                cancel.cancel()

        async def utterances() -> AsyncIterator[AsyncIterator[AudioChunk]]:
            while not cancel.cancelled:
                ready.set()
                waiting = asyncio.create_task(complete.get())
                cancelled = asyncio.create_task(cancel.wait())
                try:
                    done, _ = await asyncio.wait(
                        {waiting, cancelled}, return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancelled in done:
                        return
                    chunks = await waiting
                finally:
                    for task in (waiting, cancelled):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(waiting, cancelled, return_exceptions=True)
                ready.clear()

                async def one_turn() -> AsyncIterator[AudioChunk]:
                    for index, chunk in enumerate(chunks):
                        yield AudioChunk(context.session_id, index,
                                         chunk.data, chunk.format)
                yield one_turn()

        audio_task = asyncio.create_task(receive_audio())
        dtmf_task = asyncio.create_task(receive_dtmf())
        try:
            await self.runner.run_call(
                context, utterances(), sink, self.media.send_audio, cancel,
                lease=lease, ended_normally=ended_normally,
            )
        finally:
            for task in (audio_task, dtmf_task):
                task.cancel()
            await asyncio.gather(audio_task, dtmf_task, return_exceptions=True)
