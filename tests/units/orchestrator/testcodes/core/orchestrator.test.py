"""VOIC-FEAT-001 M5-S1: given fake ports, verify flow, cancellation and cleanup."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from voice_agent.contracts.flow import CancellationToken, SessionBusy, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import (
    Channel, ErrorCode, PublicError, SessionContext, SessionState, SessionStatus,
    StepTimeouts, TaskResult, Transcript,
)
from voice_agent.core.orchestrator import VoiceOrchestrator


class Events:
    def __init__(self):
        self.items = []

    async def publish(self, event):
        self.items.append(event)


class STT:
    async def transcribe(self, audio, context, cancel):
        async for _ in audio:
            pass
        yield Transcript("안녕", True)


class Task:
    async def process(self, text, context, cancel):
        assert text == "안녕"
        return TaskResult("반갑습니다")


class TTS:
    async def synthesize(self, text, context, cancel):
        assert text == "반갑습니다"
        yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)


def setup():
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    gate = SingleSessionGate()
    events = Events()
    output = []

    async def send(chunk):
        output.append(chunk)

    async def incoming():
        yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    return context, gate, events, output, send, incoming


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s1_success_orders_events_and_releases_gate():
    """Given one valid chunk, when run finishes, then result/audio and ordered events arrive."""
    context, gate, events, output, send, incoming = setup()
    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1))
    await core.run(context, incoming(), events, send, CancellationToken())
    assert [e.sequence for e in events.items] == list(range(len(events.items)))
    assert any(isinstance(e.payload, TaskResult) for e in events.items)
    assert events.items[-1].payload == SessionState(SessionStatus.COMPLETED)
    assert output[0].session_id == context.session_id
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s1_timeout_releases_gate():
    """Given a stalled task, when its deadline expires, then timeout is public and lease ends."""
    context, gate, events, _, send, incoming = setup()

    class SlowTask:
        async def process(self, text, context, cancel):
            await asyncio.Event().wait()

    core = VoiceOrchestrator(STT(), SlowTask(), TTS(), gate, StepTimeouts(1, .01, 1))
    await core.run(context, incoming(), events, send, CancellationToken())
    assert PublicError(ErrorCode.TIMEOUT, "처리 시간이 초과되었습니다.") in [e.payload for e in events.items]
    assert events.items[-1].payload == SessionState(SessionStatus.FAILED)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s1_cancel_and_duplicate_session():
    """Given a blocked STT, when cancelled, then wait ends and a second admission is refused."""
    context, gate, events, _, send, _ = setup()
    token = CancellationToken()

    async def stalled():
        await asyncio.Event().wait()
        yield

    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1))
    running = asyncio.create_task(core.run(context, stalled(), events, send, token))
    await asyncio.sleep(0)
    with pytest.raises(SessionBusy):
        await gate.acquire(uuid4())
    token.cancel()
    await asyncio.wait_for(running, 1)
    assert events.items[-1].payload == SessionState(SessionStatus.CANCELLED)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t3_call_keeps_gate_and_context_for_two_turns():
    """Given two phone utterances, when handled in one call, then context and gate persist."""
    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    gate, events, output = SingleSessionGate(), Events(), []
    first_done, release_second = asyncio.Event(), asyncio.Event()
    histories = []

    class PhoneSTT:
        index = 0
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            self.index += 1
            yield Transcript(f"질문{self.index}", True)

    class PhoneTask:
        async def process(self, text, context, cancel, *, history=()):
            histories.append((text, history))
            return TaskResult(f"답변{len(histories)}")

    class PhoneTTS:
        async def synthesize(self, text, context, cancel):
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    async def utterances():
        for index in range(2):
            if index:
                await release_second.wait()
            async def one():
                yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
            yield one()

    async def send(chunk):
        output.append(chunk)
        if len(output) == 1:
            first_done.set()

    core = VoiceOrchestrator(PhoneSTT(), PhoneTask(), PhoneTTS(), gate, StepTimeouts(1, 1, 1))
    running = asyncio.create_task(core.run_call(context, utterances(), events, send, CancellationToken()))
    await asyncio.wait_for(first_done.wait(), 1)
    assert gate.active_session_id == context.session_id
    with pytest.raises(SessionBusy):
        await gate.acquire(uuid4())
    release_second.set()
    await asyncio.wait_for(running, 1)
    assert histories[0] == ("질문1", ())
    assert histories[1][0] == "질문2"
    assert [(turn.user_text, turn.assistant_text) for turn in histories[1][1]] == [("질문1", "답변1")]
    assert [c.sequence for c in output] == [0, 1]
    assert [e.sequence for e in events.items] == list(range(len(events.items)))
    assert events.items[-1].payload == SessionState(SessionStatus.COMPLETED)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t3_failed_turn_does_not_enter_history():
    """Given a failed first task, when next turn succeeds, then no failed reply enters history."""
    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    histories, events = [], Events()

    class PhoneSTT:
        index = 0
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            self.index += 1
            yield Transcript(f"질문{self.index}", True)

    class PhoneTask:
        async def process(self, text, context, cancel, *, history=()):
            histories.append(history)
            if len(histories) == 1:
                raise RuntimeError("private text")
            return TaskResult("답변")

    class PhoneTTS:
        async def synthesize(self, text, context, cancel):
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    async def utterances():
        for _ in range(2):
            async def one():
                yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
            yield one()

    async def send(_chunk):
        pass

    core = VoiceOrchestrator(PhoneSTT(), PhoneTask(), PhoneTTS(), SingleSessionGate(), StepTimeouts(1, 1, 1))
    await core.run_call(context, utterances(), events, send, CancellationToken())
    assert histories == [(), ()]
    assert any(isinstance(e.payload, PublicError) for e in events.items)
    assert all("private text" not in str(e.payload) for e in events.items)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t3_new_call_starts_without_prior_history():
    """Given two consecutive calls, when the second begins, then prior context is absent."""
    gate = SingleSessionGate()
    received = []

    class PhoneSTT:
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            yield Transcript("질문", True)

    class PhoneTask:
        async def process(self, text, context, cancel, *, history=()):
            received.append(history)
            return TaskResult("답변")

    class PhoneTTS:
        async def synthesize(self, text, context, cancel):
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    core = VoiceOrchestrator(PhoneSTT(), PhoneTask(), PhoneTTS(), gate, StepTimeouts(1, 1, 1))
    async def send(_chunk):
        pass

    for _ in range(2):
        context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
        async def utterances():
            async def one():
                yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
            yield one()
        await core.run_call(context, utterances(), Events(), send, CancellationToken())
    assert received == [(), ()]
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t3_cancel_mid_task_releases_phone_lease():
    """Given a pending phone task, when caller cancels, then no output and gate releases."""
    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    gate, events, cancel = SingleSessionGate(), Events(), CancellationToken()
    entered = asyncio.Event()
    output = []

    class PhoneSTT:
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            yield Transcript("질문", True)

    class SlowTask:
        async def process(self, text, context, cancel, *, history=()):
            entered.set()
            await asyncio.Event().wait()

    async def utterances():
        async def one():
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
        yield one()

    async def send(chunk):
        output.append(chunk)

    core = VoiceOrchestrator(PhoneSTT(), SlowTask(), TTS(), gate, StepTimeouts(1, 1, 1))
    running = asyncio.create_task(core.run_call(context, utterances(), events, send, cancel))
    await asyncio.wait_for(entered.wait(), 1)
    cancel.cancel()
    await asyncio.wait_for(running, 1)
    assert output == []
    assert events.items[-1].payload == SessionState(SessionStatus.CANCELLED)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_core_records_final_text_and_both_audio_directions():
    """Given one completed utterance, when handled, then only final content enters retention."""
    context, gate, events, output, send, incoming = setup()
    stored = []

    class Retention:
        async def record_text(self, context, turn_index, kind, value):
            stored.append(("text", turn_index, kind, value))
        async def record_audio(self, context, turn_index, direction, pcm):
            stored.append(("audio", turn_index, direction, pcm))

    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1),
                             retention=Retention())
    await core.run(context, incoming(), events, send, CancellationToken())
    assert stored == [
        ("text", 0, "transcript", "안녕"),
        ("text", 0, "response", "반갑습니다"),
        ("audio", 0, "input", b"\0\0"),
        ("audio", 0, "output", b"\0\0"),
    ]
    assert events.items[-1].payload == SessionState(SessionStatus.COMPLETED)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_phone_storage_failure_ends_call_without_reply():
    """Given a retention write failure, when STT completes, then no answer and lease remains safe."""
    from voice_agent.contracts.ports import RetentionUnavailable

    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    gate, events, cancel = SingleSessionGate(), Events(), CancellationToken()
    sent = []

    class Retention:
        async def record_text(self, context, turn_index, kind, value):
            raise RetentionUnavailable("storage failed")
        async def record_audio(self, context, turn_index, direction, pcm):
            pass

    async def utterances():
        async def one():
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
        yield one()

    async def send(chunk):
        sent.append(chunk)

    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1),
                             retention=Retention())
    await core.run_call(context, utterances(), events, send, cancel)
    assert cancel.cancelled
    assert sent == []
    assert events.items[-1].payload == SessionState(SessionStatus.FAILED)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t6_phone_records_each_turn_without_partial_text():
    """Given two phone turns and a partial STT result, when processed, then only finals persist."""
    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    gate, events = SingleSessionGate(), Events()
    stored = []

    class STTWithPartial:
        index = 0
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            self.index += 1
            yield Transcript("부분", False)
            yield Transcript(f"최종{self.index}", True)

    class PhoneTask:
        async def process(self, text, context, cancel, *, history=()):
            return TaskResult("응답")

    class PhoneTTS:
        async def synthesize(self, text, context, cancel):
            yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)

    class Retention:
        async def record_text(self, context, turn_index, kind, value):
            stored.append((turn_index, kind, value))
        async def record_audio(self, context, turn_index, direction, pcm):
            stored.append((turn_index, direction, pcm))

    async def utterances():
        for _ in range(2):
            async def one():
                yield AudioChunk(context.session_id, 0, b"\0\0", INTERNAL_AUDIO_FORMAT)
            yield one()

    async def send(_chunk):
        pass

    core = VoiceOrchestrator(STTWithPartial(), PhoneTask(), PhoneTTS(), gate,
                             StepTimeouts(1, 1, 1), retention=Retention())
    await core.run_call(context, utterances(), events, send, CancellationToken())
    assert [row for row in stored if row[1] == "transcript"] == [
        (0, "transcript", "최종1"), (1, "transcript", "최종2"),
    ]
    assert [row[0] for row in stored] == [0] * 4 + [1] * 4
    assert "부분" not in str(stored)
