"""Channel independent single-session and multi-turn voice flow (VOIC-FEAT-001)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Awaitable, Callable
from opentelemetry import trace

from voice_agent.contracts.flow import (
    BoundedAudioBuffer, CancellationToken, OperationCancelled, SessionLease, SingleSessionGate,
)
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.ports import (
    ArtifactRetention, EventSink, RetentionUnavailable, SpeechToText, TaskProcessor, TextToSpeech,
)
from voice_agent.contracts.session import (
    ConversationTurn, ErrorCode, EventEnvelope, PublicError, SessionContext,
    SessionState, SessionStatus, StepTimeouts, TaskResult, Transcript,
)
from voice_agent.infrastructure.telemetry import stage


class VoiceOrchestrator:
    def __init__(
        self, stt: SpeechToText, task: TaskProcessor, tts: TextToSpeech,
        gate: SingleSessionGate, timeouts: StepTimeouts, buffer_capacity: int = 4,
        retention: ArtifactRetention | None = None,
    ) -> None:
        if buffer_capacity < 1:
            raise ValueError("audio buffer capacity must be positive")
        self._stt, self._task, self._tts = stt, task, tts
        self._gate, self._timeouts = gate, timeouts
        self._capacity = buffer_capacity
        self._retention = retention

    async def _guarded(
        self, awaitable: Awaitable[object], seconds: float, cancel: CancellationToken,
    ) -> object:
        work = asyncio.create_task(awaitable)
        cancelled = asyncio.create_task(cancel.wait())
        try:
            async with asyncio.timeout(seconds):
                done, _ = await asyncio.wait(
                    {work, cancelled}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancelled in done:
                    raise OperationCancelled()
                return await work
        finally:
            for pending in (work, cancelled):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(work, cancelled, return_exceptions=True)

    async def _turn(
        self, context: SessionContext, incoming: AsyncIterator[AudioChunk],
        emit: Callable[[object], Awaitable[None]],
        send_audio: Callable[[AudioChunk], Awaitable[None]], cancel: CancellationToken,
        output_sequence: list[int], history: tuple[ConversationTurn, ...] | None,
        turn_index: int,
    ) -> ConversationTurn:
        with trace.get_tracer("voice-agent").start_as_current_span("voice.turn") as span:
            span.set_attribute("voice.channel", context.channel.value)
            span.set_attribute("voice.turn_index", turn_index)
            return await self._turn_impl(context, incoming, emit, send_audio, cancel,
                                         output_sequence, history, turn_index)

    async def _turn_impl(
        self, context: SessionContext, incoming: AsyncIterator[AudioChunk],
        emit: Callable[[object], Awaitable[None]],
        send_audio: Callable[[AudioChunk], Awaitable[None]], cancel: CancellationToken,
        output_sequence: list[int], history: tuple[ConversationTurn, ...] | None,
        turn_index: int,
    ) -> ConversationTurn:
        buffer = BoundedAudioBuffer(context.session_id, self._capacity, cancel)
        pump: asyncio.Task[None] | None = None
        input_audio = bytearray()
        output_audio = bytearray()

        async def feed() -> None:
            async for chunk in incoming:
                cancel.raise_if_cancelled()
                if chunk.format != INTERNAL_AUDIO_FORMAT:
                    raise ValueError("incoming audio must use internal format")
                await buffer.send(chunk)
                input_audio.extend(chunk.data)
            await buffer.finish()

        async def read_audio() -> AsyncIterator[AudioChunk]:
            while (chunk := await buffer.receive()) is not None:
                yield chunk

        async def recognize() -> str:
            final: str | None = None
            async for transcript in self._stt.transcribe(read_audio(), context, cancel):
                if transcript.is_final:
                    final = transcript.text
                    if self._retention is not None:
                        await self._retention.record_text(context, turn_index, "transcript", final)
                    await emit(Transcript(final, True))
            if final is None:
                raise ValueError("no final transcript")
            return final

        async def speak(text: str) -> None:
            expected = 0
            async for chunk in self._tts.synthesize(text, context, cancel):
                cancel.raise_if_cancelled()
                if (chunk.session_id != context.session_id or chunk.sequence != expected
                        or chunk.format != INTERNAL_AUDIO_FORMAT):
                    raise ValueError("invalid synthesized audio stream")
                output_audio.extend(chunk.data)
                await send_audio(AudioChunk(
                    context.session_id, output_sequence[0], chunk.data, chunk.format,
                ))
                output_sequence[0] += 1
                expected += 1

        try:
            await emit(SessionState(SessionStatus.LISTENING))
            pump = asyncio.create_task(feed())

            async def stt_stage() -> str:
                recognition = asyncio.create_task(recognize())
                try:
                    done, _ = await asyncio.wait(
                        {recognition, pump}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if pump in done:
                        await pump
                    return await recognition
                finally:
                    if not recognition.done():
                        recognition.cancel()
                    await asyncio.gather(recognition, return_exceptions=True)

            with stage("stt"):
                text = await self._guarded(stt_stage(), self._timeouts.stt_s, cancel)
            await emit(SessionState(SessionStatus.PROCESSING))
            if history is None:
                task_call = self._task.process(text, context, cancel)
            else:
                task_call = self._task.process(text, context, cancel, history=history)
            with stage("task_api"):
                result = await self._guarded(task_call, self._timeouts.task_s, cancel)
            if not isinstance(result, TaskResult):
                raise TypeError("task processor returned an invalid result")
            if self._retention is not None:
                await self._retention.record_text(context, turn_index, "response", result.text)
            await emit(result)
            await emit(SessionState(SessionStatus.SPEAKING))
            with stage("tts"):
                await self._guarded(speak(result.text), self._timeouts.tts_s, cancel)
            return ConversationTurn(text, result.text)
        finally:
            if pump is not None:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            if self._retention is not None:
                if input_audio:
                    await self._retention.record_audio(context, turn_index, "input", bytes(input_audio))
                if output_audio:
                    await self._retention.record_audio(context, turn_index, "output", bytes(output_audio))

    async def _next_utterance(
        self, iterator: AsyncIterator[AsyncIterator[AudioChunk]],
        cancel: CancellationToken,
    ) -> AsyncIterator[AudioChunk]:
        cancel.raise_if_cancelled()
        next_turn = asyncio.create_task(iterator.__anext__())
        cancelled = asyncio.create_task(cancel.wait())
        try:
            done, _ = await asyncio.wait(
                {next_turn, cancelled}, return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled in done:
                raise OperationCancelled()
            return await next_turn
        finally:
            for pending in (next_turn, cancelled):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(next_turn, cancelled, return_exceptions=True)

    async def _report_failure(
        self, error: Exception, emit: Callable[[object], Awaitable[None]],
    ) -> None:
        if isinstance(error, TimeoutError):
            public = PublicError(ErrorCode.TIMEOUT, "처리 시간이 초과되었습니다.")
        elif isinstance(error, ValueError):
            public = PublicError(ErrorCode.INVALID_INPUT, "음성 입력 또는 출력 형식이 올바르지 않습니다.")
        else:
            public = PublicError(ErrorCode.UNAVAILABLE, "음성 작업을 처리할 수 없습니다.")
        await emit(public)
        await emit(SessionState(SessionStatus.FAILED))

    async def run(
        self, context: SessionContext, incoming: AsyncIterator[AudioChunk],
        events: EventSink, send_audio: Callable[[AudioChunk], Awaitable[None]],
        cancel: CancellationToken,
    ) -> None:
        """Run the existing web request with one utterance and one gate lease."""
        async with await self._gate.acquire(context.session_id):
            sequence = 0

            async def emit(payload: object) -> None:
                nonlocal sequence
                await events.publish(EventEnvelope(context.session_id, sequence, payload))
                sequence += 1

            try:
                await emit(SessionState(SessionStatus.STARTING))
                await self._turn(context, incoming, emit, send_audio, cancel, [0], None, 0)
                await emit(SessionState(SessionStatus.COMPLETED))
            except (OperationCancelled, asyncio.CancelledError):
                cancel.cancel()
                await emit(SessionState(SessionStatus.CANCELLED))
            except Exception as error:
                await self._report_failure(error, emit)

    @asynccontextmanager
    async def _call_lease(self, context: SessionContext, lease: SessionLease | None):
        if lease is None:
            async with await self._gate.acquire(context.session_id):
                yield
        else:
            if (lease._gate is not self._gate or lease.session_id != context.session_id
                    or lease._released or self._gate.active_session_id != context.session_id):
                raise ValueError("invalid phone session lease")
            yield

    async def run_call(
        self, context: SessionContext,
        utterances: AsyncIterator[AsyncIterator[AudioChunk]], events: EventSink,
        send_audio: Callable[[AudioChunk], Awaitable[None]], cancel: CancellationToken,
        *, lease: SessionLease | None = None,
        ended_normally: Callable[[], bool] | None = None,
    ) -> None:
        """Hold one lease through every phone utterance; the channel ends the call."""
        async with self._call_lease(context, lease):
            sequence = 0
            output_sequence = [0]
            history: list[ConversationTurn] = []
            turn_index = 0
            retention_failed = False

            async def emit(payload: object) -> None:
                nonlocal sequence
                await events.publish(EventEnvelope(context.session_id, sequence, payload))
                sequence += 1

            try:
                await emit(SessionState(SessionStatus.STARTING))
                iterator = utterances.__aiter__()
                while True:
                    try:
                        incoming = await self._next_utterance(iterator, cancel)
                    except StopAsyncIteration:
                        break
                    try:
                        turn = await self._turn(
                            context, incoming, emit, send_audio, cancel,
                            output_sequence, tuple(history), turn_index,
                        )
                        history.append(turn)
                    except (OperationCancelled, asyncio.CancelledError):
                        raise
                    except RetentionUnavailable as error:
                        await self._report_failure(error, emit)
                        cancel.cancel()
                        retention_failed = True
                        break
                    except Exception as error:
                        await self._report_failure(error, emit)
                    finally:
                        turn_index += 1
                if not retention_failed:
                    await emit(SessionState(SessionStatus.COMPLETED))
            except (OperationCancelled, asyncio.CancelledError):
                if ended_normally is not None and ended_normally():
                    await emit(SessionState(SessionStatus.COMPLETED))
                else:
                    cancel.cancel()
                    await emit(SessionState(SessionStatus.CANCELLED))
            except Exception as error:
                await self._report_failure(error, emit)
            finally:
                history.clear()
