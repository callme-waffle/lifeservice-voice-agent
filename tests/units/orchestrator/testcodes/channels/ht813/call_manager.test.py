"""VOIC-FEAT-001 M6-S1-T4: fake SIP/RTP conversation and gate lifecycle."""

import asyncio
from uuid import uuid4

import pytest

from voice_agent.channels.ht813.call_manager import OutboundCallManager
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SessionBusy, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import (
    AllowedNumberPolicy, CallState, CallStatus, DialNumber, DtmfEvent,
    EventEnvelope, OutboundCallRequest, SessionState, SessionStatus, TaskResult, Transcript,
    StepTimeouts,
)
from voice_agent.core.orchestrator import VoiceOrchestrator


def frame(sid, seq, sample):
    return AudioChunk(sid, seq, sample.to_bytes(2, "little", signed=True) * 320,
                      INTERNAL_AUDIO_FORMAT)


class Events:
    def __init__(self):
        self.items = []

    async def publish(self, event):
        self.items.append(event)


class FakeOutbound:
    def __init__(self):
        self.policy = AllowedNumberPolicy(frozenset({"123456"}))
        self.audio = asyncio.Queue()
        self.dtmf = asyncio.Queue()
        self.ended = asyncio.Event()
        self.sent = []
        self.dials = 0

    async def dial(self, request, sink, cancel):
        self.dials += 1
        await sink.publish(EventEnvelope(request.session_id, 0, CallState(CallStatus.DIALING)))
        await sink.publish(EventEnvelope(request.session_id, 1, CallState(CallStatus.ACTIVE)))
        done = asyncio.create_task(self.ended.wait())
        cancelled = asyncio.create_task(cancel.wait())
        try:
            await asyncio.wait({done, cancelled}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (done, cancelled):
                task.cancel()
            await asyncio.gather(done, cancelled, return_exceptions=True)
        await sink.publish(EventEnvelope(request.session_id, 2, CallState(CallStatus.ENDED)))

    async def receive_audio(self):
        return await self.audio.get()

    async def receive_dtmf(self):
        return await self.dtmf.get()

    async def send_audio(self, chunk):
        self.sent.append(chunk)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_one_dial_two_turns_until_remote_end():
    """Given one allowed call, when two speech turns arrive, then both answer before remote end."""
    fake, gate, events = FakeOutbound(), SingleSessionGate(), Events()
    sid = uuid4()
    histories = []

    class STT:
        index = 0
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            self.index += 1
            yield Transcript(f"질문{self.index}", True)

    class Task:
        async def process(self, text, context, cancel, *, history=()):
            histories.append((text, history))
            return TaskResult(f"답변{len(histories)}")

    class TTS:
        async def synthesize(self, text, context, cancel):
            yield frame(context.session_id, 0, 1000)

    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1))
    manager = OutboundCallManager(fake, core, gate, TurnBoundary(400, 100, 2000))
    request = OutboundCallRequest(sid, DialNumber("123456"), 5)
    running = asyncio.create_task(manager.call(request, events, CancellationToken()))

    async def push_turn(start):
        await fake.audio.put(frame(sid, start, 1000))
        for n in range(5):
            await fake.audio.put(frame(sid, start + n + 1, 0))

    await push_turn(0)
    async def wait_outputs(count):
        while len(fake.sent) < count:
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_outputs(1), 1)
    assert not running.done()
    assert gate.active_session_id == sid
    with pytest.raises(SessionBusy):
        await gate.acquire(uuid4())
    await asyncio.sleep(.01)  # let the core request its next utterance
    await push_turn(6)
    await asyncio.wait_for(wait_outputs(2), 1)
    assert fake.dials == 1
    assert [chunk.sequence for chunk in fake.sent] == [0, 1]
    assert [(item[0], len(item[1])) for item in histories] == [("질문1", 0), ("질문2", 1)]
    assert not running.done()  # the first answer must not trigger SIP BYE
    await fake.dtmf.put(DtmfEvent(sid, "5", 100))
    async def wait_dtmf():
        while not any(isinstance(e.payload, DtmfEvent) for e in events.items):
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_dtmf(), 1)
    fake.ended.set()
    await asyncio.wait_for(running, 1)
    assert gate.active_session_id is None
    assert [e.sequence for e in events.items] == list(range(len(events.items)))
    assert events.items[-1].payload == SessionState(SessionStatus.COMPLETED)
    assert any(e.payload == DtmfEvent(sid, "5", 100) for e in events.items)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_disallowed_number_never_dials():
    """Given a non-exact destination, when requested, then no SIP dial starts."""
    fake, gate = FakeOutbound(), SingleSessionGate()
    manager = OutboundCallManager(fake, object(), gate, TurnBoundary())
    request = OutboundCallRequest(uuid4(), DialNumber("999999"), 5)
    with pytest.raises(PermissionError):
        await manager.call(request, Events(), CancellationToken())
    assert fake.dials == 0
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_remote_end_cancels_pending_task():
    """Given an active call in task processing, when remote ends, then task stops and lease frees."""
    fake, gate, events = FakeOutbound(), SingleSessionGate(), Events()
    sid, entered = uuid4(), asyncio.Event()

    class STT:
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            yield Transcript("질문", True)

    class SlowTask:
        async def process(self, text, context, cancel, *, history=()):
            entered.set()
            await asyncio.Event().wait()

    class TTS:
        async def synthesize(self, text, context, cancel):
            yield frame(context.session_id, 0, 1000)

    core = VoiceOrchestrator(STT(), SlowTask(), TTS(), gate, StepTimeouts(1, 1, 1))
    manager = OutboundCallManager(fake, core, gate, TurnBoundary(400, 100, 2000))
    running = asyncio.create_task(manager.call(
        OutboundCallRequest(sid, DialNumber("123456"), 5), events, CancellationToken(),
    ))
    await fake.audio.put(frame(sid, 0, 1000))
    for i in range(5):
        await fake.audio.put(frame(sid, i + 1, 0))
    await asyncio.wait_for(entered.wait(), 1)
    fake.ended.set()
    await asyncio.wait_for(running, 1)
    assert fake.sent == []
    assert gate.active_session_id is None
    assert events.items[-1].payload == SessionState(SessionStatus.COMPLETED)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_gate_held_while_dialing_and_cancel_releases():
    """Given a pending SIP setup, when cancelled, then competing sessions stay busy until cleanup."""
    gate, events, cancel = SingleSessionGate(), Events(), CancellationToken()
    sid, entered = uuid4(), asyncio.Event()

    class PendingOutbound(FakeOutbound):
        async def dial(self, request, sink, cancel):
            self.dials += 1
            await sink.publish(EventEnvelope(request.session_id, 0, CallState(CallStatus.DIALING)))
            entered.set()
            await cancel.wait()
            await sink.publish(EventEnvelope(request.session_id, 1, CallState(CallStatus.ENDED)))

    fake = PendingOutbound()
    manager = OutboundCallManager(fake, object(), gate, TurnBoundary())
    running = asyncio.create_task(manager.call(
        OutboundCallRequest(sid, DialNumber("123456"), 5), events, cancel,
    ))
    await asyncio.wait_for(entered.wait(), 1)
    assert gate.active_session_id == sid
    with pytest.raises(SessionBusy):
        await gate.acquire(uuid4())
    cancel.cancel()
    await asyncio.wait_for(running, 1)
    assert gate.active_session_id is None
    assert fake.dials == 1


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_task_timeout_keeps_call_until_remote_end():
    """Given a timed-out voice turn, when reported, then call stays up for a later turn."""
    from voice_agent.contracts.session import PublicError, ErrorCode

    fake, gate, events = FakeOutbound(), SingleSessionGate(), Events()
    sid = uuid4()

    class STT:
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            yield Transcript("질문", True)

    class SlowTask:
        async def process(self, text, context, cancel, *, history=()):
            await asyncio.Event().wait()

    core = VoiceOrchestrator(STT(), SlowTask(), object(), gate, StepTimeouts(1, .01, 1))
    manager = OutboundCallManager(fake, core, gate, TurnBoundary(400, 100, 2000))
    running = asyncio.create_task(manager.call(
        OutboundCallRequest(sid, DialNumber("123456"), 5), events, CancellationToken(),
    ))
    await fake.audio.put(frame(sid, 0, 1000))
    for i in range(5):
        await fake.audio.put(frame(sid, i + 1, 0))

    async def wait_timeout():
        while not any(isinstance(e.payload, PublicError) for e in events.items):
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_timeout(), 1)
    assert any(e.payload.code is ErrorCode.TIMEOUT for e in events.items
               if isinstance(e.payload, PublicError))
    assert gate.active_session_id == sid
    assert not running.done()
    fake.ended.set()
    await asyncio.wait_for(running, 1)
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_discards_audio_during_reply():
    """Given speech while the first reply plays, when the next turn starts, then it is not reused."""
    fake, gate, events = FakeOutbound(), SingleSessionGate(), Events()
    sid, speaking, release = uuid4(), asyncio.Event(), asyncio.Event()
    seen = []

    class STT:
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            yield Transcript("질문", True)

    class Task:
        async def process(self, text, context, cancel, *, history=()):
            seen.append(len(history))
            return TaskResult("답변")

    class TTS:
        count = 0
        async def synthesize(self, text, context, cancel):
            self.count += 1
            yield frame(context.session_id, 0, 1000)
            if self.count == 1:
                speaking.set()
                await release.wait()

    core = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1))
    manager = OutboundCallManager(fake, core, gate, TurnBoundary(400, 100, 2000))
    running = asyncio.create_task(manager.call(
        OutboundCallRequest(sid, DialNumber("123456"), 5), events, CancellationToken(),
    ))

    async def push_turn(start):
        await fake.audio.put(frame(sid, start, 1000))
        for i in range(5):
            await fake.audio.put(frame(sid, start + i + 1, 0))

    await push_turn(0)
    await asyncio.wait_for(speaking.wait(), 1)
    await push_turn(6)  # arrives while TTS is still blocked
    async def wait_drained():
        while not fake.audio.empty():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_drained(), 1)
    release.set()
    await asyncio.sleep(.01)
    await push_turn(12)
    async def wait_two():
        while len(fake.sent) < 2:
            await asyncio.sleep(0)
    await asyncio.wait_for(wait_two(), 1)
    fake.ended.set()
    await asyncio.wait_for(running, 1)
    assert seen == [0, 1]
