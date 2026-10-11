"""Ports shared by the core and adapters (VOIC-FEAT-001, M4-S2-T2)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from .flow import CancellationToken, SessionLease
from .media import AudioChunk
from .session import ConversationTurn, EventEnvelope, OutboundCallRequest, SessionContext, TaskResult, Transcript


class Cancellation(Protocol):
    @property
    def cancelled(self) -> bool: ...

    async def wait(self) -> None: ...

    def raise_if_cancelled(self) -> None: ...


class SpeechToText(Protocol):
    def transcribe(
        self, audio: AsyncIterator[AudioChunk], context: SessionContext, cancel: Cancellation
    ) -> AsyncIterator[Transcript]: ...


class TaskProcessor(Protocol):
    async def process(
        self, text: str, context: SessionContext, cancel: Cancellation,
        *, history: tuple[ConversationTurn, ...] = (),
    ) -> TaskResult: ...


class TextToSpeech(Protocol):
    def synthesize(
        self, text: str, context: SessionContext, cancel: Cancellation
    ) -> AsyncIterator[AudioChunk]: ...


class EventSink(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


class VoiceSessionRunner(Protocol):
    async def run(
        self, context: SessionContext, incoming: AsyncIterator[AudioChunk],
        events: EventSink, send_audio: Callable[[AudioChunk], Awaitable[None]],
        cancel: Cancellation,
    ) -> None: ...


class OutboundDialer(Protocol):
    async def dial(
        self, request: OutboundCallRequest, sink: EventSink, cancel: Cancellation
    ) -> None: ...


class PhoneSessionRunner(Protocol):
    async def run_call(
        self, context: SessionContext,
        utterances: AsyncIterator[AsyncIterator[AudioChunk]], events: EventSink,
        send_audio: Callable[[AudioChunk], Awaitable[None]], cancel: CancellationToken,
        *, lease: SessionLease | None = None,
        ended_normally: Callable[[], bool] | None = None,
    ) -> None: ...


class RetentionUnavailable(Exception):
    """Recording or expiry failed without exposing content or secret details."""


class ArtifactRetention(Protocol):
    async def record_audio(
        self, context: SessionContext, turn_index: int, direction: str, pcm: bytes,
    ) -> object: ...

    async def record_text(
        self, context: SessionContext, turn_index: int, kind: str, value: str,
    ) -> object: ...
