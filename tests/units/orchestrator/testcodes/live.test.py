"""VOIC-FEAT-010 M14: isolated duplex, delegation and cleanup contracts (no API)."""
import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from voice_agent.contracts.flow import CancellationToken, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import SessionContext, Channel, TaskResult
from voice_agent.core.live import LiveRunner


class Transport:
    def __init__(self):
        self.started = {"session": {}}
        self.received = asyncio.Queue()
        self.sent = []
        self.opened = self.closed = False

    @asynccontextmanager
    async def open(self):
        self.opened = True
        try:
            yield self
        finally:
            self.closed = True

    async def send(self, event):
        self.sent.append(event)
        if event["type"] == "session.close":
            await self.received.put({"type": "session.closed", "usage": {"seconds": 7}})

    async def receive(self):
        return await self.received.get()


class Retention:
    def __init__(self):
        self.audio, self.text = [], []

    async def record_live_audio(self, *args):
        self.audio.append(args)

    async def record_live_text(self, *args):
        self.text.append(args)


class Task:
    def __init__(self):
        self.requests = []

    async def process(self, text, context, cancel):
        self.requests.append(text)
        return TaskResult("확인했습니다")


class Events:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.001)


def setup():
    context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
    connection, task, gate, retention = Transport(), Task(), SingleSessionGate(), Retention()
    runner = LiveRunner(connection, task, gate, retention, drain_s=.02)
    return context, connection, task, gate, retention, runner


async def test_live_duplex_input_continues_while_output_blocked_and_cancel_releases_gate():
    """Given blocked output, input remains live; cancellation closes socket and all workers."""
    context, connection, task, gate, retention, runner = setup()
    token, inputs, speaking = CancellationToken(), asyncio.Queue(), asyncio.Event()

    async def incoming():
        index = 0
        while True:
            yield AudioChunk(context.session_id, index, await inputs.get(), INTERNAL_AUDIO_FORMAT)
            index += 1

    async def output(chunk):
        speaking.set()
        await asyncio.Future()

    run = asyncio.create_task(runner.run(context, incoming(), Events(), output, token))
    await until(lambda: connection.opened)
    await connection.received.put({"type": "session.output_audio.delta",
                                   "delta": base64.b64encode(b'\0' * 1920).decode()})
    await asyncio.wait_for(speaking.wait(), 2)
    await inputs.put(b'\0' * 640)
    await until(lambda: any(e['type'] == 'session.input_audio.append' for e in connection.sent))
    token.cancel()
    await asyncio.wait_for(run, 2)
    assert connection.closed and gate.active_session_id is None
    assert runner.last_usage_seconds == 7 and runner.last_usage_final
    assert not any(t.get_name().startswith('live-') for t in asyncio.all_tasks())
    assert any(a[1] == 'generated' for a in retention.audio)
    assert not any(a[1] == 'sent' for a in retention.audio)


async def test_live_delegation_deduplicates_and_uses_partial_session_transcript():
    """Given duplicate delegation IDs, task runs once with marked partial transcript."""
    context, connection, task, gate, retention, runner = setup()
    token = CancellationToken()

    async def incoming():
        await asyncio.Future()
        yield

    async def output(chunk):
        pass

    run = asyncio.create_task(runner.run(context, incoming(), Events(), output, token))
    await until(lambda: connection.opened)
    await connection.received.put({"type": "session.input_transcript.delta", "delta": "예약 확인",
                                   "start_ms": 0, "end_ms": 1000})
    event = {"type": "session.delegation.created", "delegation": {"id": "d1", "target": "client"}}
    await connection.received.put(event)
    await connection.received.put(event)
    await until(lambda: any(e['type'] == 'session.commentary.append' for e in connection.sent))
    token.cancel()
    await run
    assert len(task.requests) == 1 and "partial" in task.requests[0]
    assert retention.text[0][2]["partial"] is True
    assert [e for e in connection.sent if e['type'] == 'session.commentary.append'][0]['delegation_id'] == 'd1'


async def test_live_end_drains_and_closes_without_cancelling_other_session():
    """Given finite input, mute/drain/close happen and the session lease is released."""
    context, connection, task, gate, retention, runner = setup()

    async def incoming():
        yield AudioChunk(context.session_id, 0, b'\0' * 640, INTERNAL_AUDIO_FORMAT)

    async def output(chunk):
        pass

    await runner.run(context, incoming(), Events(), output, CancellationToken())
    assert [e['type'] for e in connection.sent] == [
        'session.input_audio.append', 'session.input_audio.mute', 'session.close']
    assert gate.active_session_id is None
    assert retention.audio[0][1:3] == ('input', 0)


async def test_live_overflow_fails_closed_without_silent_audio_drop():
    """Given output exceeding queue budget, session fails and cancellation propagates."""
    context, connection, task, gate, retention, runner = setup()
    token = CancellationToken()

    async def incoming():
        await asyncio.Future()
        yield

    async def output(chunk):
        await asyncio.Future()

    run = asyncio.create_task(runner.run(context, incoming(), Events(), output, token))
    await until(lambda: connection.opened)
    await connection.received.put({"type": "session.output_audio.delta",
                                   "delta": base64.b64encode(b'\0' * 48000).decode()})
    with pytest.raises(asyncio.QueueFull):
        await asyncio.wait_for(run, 2)
    assert token.cancelled and connection.closed and gate.active_session_id is None


async def test_live_cancel_during_connect_releases_lease_without_waiting_for_timeout():
    """Given a stalled handshake, cancellation interrupts connection rather than waiting 10s."""
    context, connection, task, gate, retention, runner = setup()
    entered = asyncio.Event()

    class Connecting:
        @asynccontextmanager
        async def open(self):
            entered.set()
            await asyncio.Future()
            yield

    runner.transport = Connecting()
    token = CancellationToken()

    async def incoming():
        await asyncio.Future()
        yield

    async def output(chunk):
        pass

    run = asyncio.create_task(runner.run(context, incoming(), Events(), output, token))
    await entered.wait()
    token.cancel()
    await asyncio.wait_for(run, .5)
    assert gate.active_session_id is None


async def test_live_segment_recording_is_bounded_to_ten_seconds():
    """Given >10 seconds input, bounded records retain contiguous sample positions."""
    context, connection, task, gate, retention, runner = setup()

    async def incoming():
        for index in range(11):
            yield AudioChunk(context.session_id, index, b'\0' * 32000, INTERNAL_AUDIO_FORMAT)

    async def output(chunk):
        pass

    await runner.run(context, incoming(), Events(), output, CancellationToken())
    records = [a for a in retention.audio if a[1] == 'input']
    assert [len(a[3]) for a in records] == [320000, 32000]
    assert [a[2] for a in records] == [0, 160000]


@pytest.mark.parametrize('event', [
    {'type': 'session.output_audio.delta', 'delta': 'not base64!'},
    {'type': 'session.output_audio.delta', 'delta': base64.b64encode(b'1').decode()},
])
async def test_live_malformed_audio_fails_and_releases_session(event):
    """Given corrupt server audio, fail closed and release resources without forwarding it."""
    context, connection, task, gate, retention, runner = setup()
    token = CancellationToken()
    async def incoming():
        await asyncio.Future()
        yield
    async def output(chunk):
        raise AssertionError('corrupt output must not be sent')
    await connection.received.put(event)
    with pytest.raises(ValueError):
        await runner.run(context, incoming(), Events(), output, token)
    assert token.cancelled and gate.active_session_id is None and connection.closed


async def test_live_delegation_failure_is_reported_as_failure_and_late_work_cancelled():
    """Given failed task work, commentary cannot claim success; session cancellation ends pending work."""
    context, connection, task, gate, retention, runner = setup()
    token = CancellationToken()
    async def fail(*args, **kwargs):
        raise RuntimeError('private backend failure')
    task.process = fail
    async def incoming():
        await asyncio.Future()
        yield
    async def output(chunk):
        pass
    run = asyncio.create_task(runner.run(context, incoming(), Events(), output, token))
    await until(lambda: connection.opened)
    await connection.received.put({'type': 'session.input_transcript.delta', 'delta': '작업 요청', 'start_ms': 0, 'end_ms': 10})
    await connection.received.put({'type': 'session.delegation.created', 'delegation': {'id': 'failed', 'target': 'client'}})
    await until(lambda: any(e['type'] == 'session.commentary.append' for e in connection.sent))
    result = next(e for e in connection.sent if e['type'] == 'session.commentary.append')
    assert '실패' in result['content'] and 'private' not in result['content']
    token.cancel()
    await run


async def test_live_retention_failure_cancels_call_and_does_not_send_unrecorded_input():
    """Given a failed segment write, stop the session instead of continuing unretained audio."""
    context, connection, task, gate, retention, runner = setup()
    token = CancellationToken()
    async def fail(*args):
        raise RuntimeError('storage unavailable')
    retention.record_live_audio = fail
    async def incoming():
        for index in range(10):
            yield AudioChunk(context.session_id, index, b'\0'*32000, INTERNAL_AUDIO_FORMAT)
    async def output(chunk):
        pass
    with pytest.raises(RuntimeError, match='storage unavailable'):
        await runner.run(context, incoming(), Events(), output, token)
    assert token.cancelled and gate.active_session_id is None


async def test_live_remote_close_preserves_final_usage_and_does_not_close_twice():
    """Given server finalization first, retain its usage acknowledgement and release admission."""
    context, connection, task, gate, retention, runner = setup()
    async def incoming():
        await asyncio.Future()
        yield
    async def output(chunk):
        pass
    await connection.received.put({'type': 'session.closed', 'usage': {'seconds': 9}})
    await runner.run(context, incoming(), Events(), output, CancellationToken())
    assert runner.last_usage_final and runner.last_usage_seconds == 9
    assert not any(e['type'] == 'session.close' for e in connection.sent)
    assert gate.active_session_id is None
