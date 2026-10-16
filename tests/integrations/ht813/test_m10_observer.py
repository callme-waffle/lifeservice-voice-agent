"""VOIC-OPS-008: PRD-02/03/06, SRS-O07/O11 metadata-only local observer checks."""
import asyncio
import io
import threading
from types import SimpleNamespace
import json
from uuid import uuid4

import pytest

from tests.integrations.ht813.m10_live_app import Metadata, instrument
from voice_agent.bootstrap import create_app
from voice_agent.config import Settings
from voice_agent.contracts.flow import CancellationToken
from voice_agent.contracts.media import AudioChunk, DtmfEvent, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import CallState, CallStatus, EventEnvelope, Transcript, TaskResult


def app():
    return create_app(Settings.from_env({
        'VOICE_AGENT_WEB_ACCESS_TOKEN': 'synthetic-token',
        'VOICE_AGENT_STT_MODEL_ID': 'small',
        'VOICE_AGENT_TASK_MODEL': 'synthetic',
        'VOICE_AGENT_TASK_API_KEY': 'synthetic-key',
        'VOICE_AGENT_TASK_API_BASE_URL': 'https://llm.example.test',
        'VOICE_AGENT_TASK_APPROVED_HOST': 'llm.example.test',
        'VOICE_AGENT_DATA_ENCRYPTION_KEY': 'S0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0s=',
        'VOICE_AGENT_HT813_ALLOWED_EXACT': '1234567',
        'VOICE_AGENT_HT813_HOST': '192.0.2.17',
        'VOICE_AGENT_HT813_LOCAL_IPV4': '192.0.2.50',
        'VOICE_AGENT_HT813_SIP_USER_ID': 'synthetic-agent',
        'VOICE_AGENT_HT813_INBOUND_ENABLED': 'true',
    }))


@pytest.mark.asyncio
async def test_voic_ops_008_observer_preserves_events_and_gate_without_payload_leak(tmp_path):
    """Given sensitive synthetic events, when observed, then originals survive and stdout has metadata only."""
    private = tmp_path/'private'
    private.mkdir(mode=0o700)
    output = io.StringIO()
    metadata = Metadata(output, private/'map.json')
    application = app()
    manager = application.state.operator_calls.manager
    gate = manager.gate
    sid = uuid4()
    values = [CallState(CallStatus.ACTIVE), Transcript('PRIVATE QUESTION', True),
              TaskResult('PRIVATE ANSWER'), DtmfEvent(sid, '5', 160), CallState(CallStatus.ENDED)]
    forwarded = []
    class Sink:
        async def publish(self, event):
            forwarded.append(event)
    original_sink = Sink()
    token = CancellationToken()
    lease = await gate.acquire(sid)
    async def original_call(request, events, cancel, *, lease):
        assert cancel is token and request == 'synthetic-request'
        for index, value in enumerate(values):
            await events.publish(EventEnvelope(sid, index, value))
        await lease.release()
        return 'original-return'
    manager.call = original_call
    instrument(application, metadata)
    assert await manager.call('synthetic-request', original_sink, token, lease=lease) == 'original-return'
    assert [event.payload for event in forwarded] == values
    assert gate.active_session_id is None
    assert metadata.close()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[-1]['event'] == 'gate_released'
    assert rows[-1]['call'] == 'call-1'
    assert next(x for x in rows if x['event']=='dtmf')['test_symbol'] == '5'
    assert all(secret not in output.getvalue() for secret in ['PRIVATE',str(sid),'synthetic-token','synthetic-key'])
    assert json.loads((private/'map.json').read_text()) == {'call-1':str(sid)}
    assert (private/'map.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_voic_ops_008_observer_waits_for_media_close_before_recording_release():
    """Given wrapped media, when output/close finish, then observations follow actual completion."""
    application = app()
    output = io.StringIO()
    metadata = Metadata(output)
    calls = []
    class Media:
        def __init__(self, *args, **kwargs):pass
        async def send_audio(self, chunk):calls.append('sent')
        async def close(self):
            assert 'media_closed' not in output.getvalue()
            calls.append('closed')
    application.state.outbound._media_factory = Media
    instrument(application,metadata)
    sid=uuid4()
    media=application.state.outbound._media_factory(sid,local_host='127.0.0.1',local_port=0)
    await media.send_audio(AudioChunk(sid,0,b'\0'*640,INTERNAL_AUDIO_FORMAT))
    await media.close()
    assert calls == ['sent','closed']
    assert metadata.close()
    rows=[json.loads(x) for x in output.getvalue().splitlines()]
    assert [x['event'] for x in rows]==['output_chunk_started','output_chunk_complete','media_closed']
    assert rows[1]['duration_ms']==20
    assert rows[-1]['output_attempted'] == rows[-1]['output_completed'] == 1
    assert rows[-1]['output_cancelled'] == rows[-1]['output_failed'] == 0


def test_voic_ops_008_observer_sip_metadata_omits_headers_and_rejects_public_map(tmp_path):
    """Given SIP containing synthetic identity/secret fields, when observed, then none reach shared output."""
    output=io.StringIO();metadata=Metadata(output)
    metadata.sip('sip_send',b'INVITE sip:private-destination@example.test SIP/2.0\r\nAuthorization: PRIVATE\r\nContact: <sip:PRIVATE@example.test>\r\nContent-Length: 0\r\n\r\n')
    assert metadata.close()
    row=json.loads(output.getvalue())
    assert row['method']=='INVITE' and row['has_contact'] is True
    assert 'PRIVATE' not in output.getvalue() and 'destination' not in output.getvalue()
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError,match='private mapping'):
        Metadata(io.StringIO(),tmp_path/'map.json')


@pytest.mark.asyncio
async def test_voic_ops_008_observer_output_failure_keeps_original_call_and_release():
    """PRD-06/SRS-C03/T04: given broken output, when a call ends, then it still releases its lease."""
    class BrokenOutput:
        def write(self, value):
            raise OSError('synthetic private sink failure')
        def flush(self):
            pass
    metadata = Metadata(BrokenOutput())
    application = app()
    manager = application.state.operator_calls.manager
    sid = uuid4()
    lease = await manager.gate.acquire(sid)
    class Sink:
        async def publish(self, event):
            pass
    async def original_call(request, events, cancel, *, lease):
        await events.publish(EventEnvelope(sid, 0, CallState(CallStatus.ENDED)))
        await lease.release()
        return 'unchanged'
    manager.call = original_call
    instrument(application, metadata)
    assert await manager.call(None, Sink(), CancellationToken(), lease=lease) == 'unchanged'
    assert manager.gate.active_session_id is None
    assert metadata.close() is False
    assert metadata.evidence_lost


@pytest.mark.asyncio
async def test_voic_ops_008_observer_shutdown_failure_is_not_success(monkeypatch):
    """PRD-06/SRS-O07: given failed lifespan cleanup, when serving ends, then no stopped success is emitted."""
    import asyncio
    from types import SimpleNamespace
    import uvicorn
    from tests.integrations.ht813.m10_live_app import serve
    class Server:
        def __init__(self, config):
            self.started = True
            done = asyncio.Event()
            done.set()
            self.lifespan = SimpleNamespace(startup_failed=False, shutdown_failed=True,
                                            error_occurred=False, shutdown_event=done)
        async def serve(self):
            pass
    monkeypatch.setattr(uvicorn, 'Server', Server)
    output = io.StringIO()
    metadata = Metadata(output)
    assert await serve(None, metadata, 5) == 1
    assert 'stopped' not in output.getvalue()
    assert 'shutdown_failed' in output.getvalue()


@pytest.mark.asyncio
async def test_voic_ops_008_observer_blocked_sink_overflow_and_close_are_bounded():
    """PRD-06/SRS-T04: given blocked output and a full queue, then callbacks and bounded drain still return."""
    entered, release = threading.Event(), threading.Event()
    class BlockedOutput(io.StringIO):
        def write(self, value):
            entered.set()
            release.wait()
            return super().write(value)
    metadata = Metadata(BlockedOutput(), capacity=1)
    try:
        metadata.emit('first')
        assert await asyncio.to_thread(entered.wait, 1)
        metadata.emit('second')
        metadata.emit('overflow')
        assert metadata.evidence_lost
        assert metadata._queue.qsize() == 1
        assert await asyncio.wait_for(asyncio.to_thread(metadata.close, .02), .5) is False
        assert metadata._worker.is_alive() and metadata._worker.daemon
    finally:
        release.set()
        await asyncio.to_thread(metadata.close)


@pytest.mark.asyncio
async def test_voic_ops_008_observer_mapping_failure_does_not_interrupt_gate(tmp_path, monkeypatch):
    """PRD-06/SRS-C03: given mapping I/O failure, then the original gate still releases and evidence fails."""
    private = tmp_path/'private'
    private.mkdir(mode=0o700)
    metadata = Metadata(io.StringIO(), private/'map.json')
    def fail_save():
        raise OSError('synthetic private mapping failure')
    monkeypatch.setattr(metadata, '_save', fail_save)
    application = app()
    instrument(application, metadata)
    gate = application.state.operator_calls.gate
    lease = await gate.acquire(uuid4())
    await lease.release()
    assert gate.active_session_id is None
    assert metadata.close() is False and metadata.evidence_lost


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['cancelled', 'failed'])
async def test_voic_ops_008_observer_media_attempt_does_not_mean_completed(failure):
    """PRD-06/SRS-T04: given interrupted media, then the original exception survives and completion stays zero."""
    output = io.StringIO()
    metadata = Metadata(output)
    application = app()
    error = asyncio.CancelledError() if failure == 'cancelled' else OSError('PRIVATE')
    entered = asyncio.Event()
    class Media:
        def __init__(self, *args, **kwargs):
            pass
        async def send_audio(self, chunk):
            entered.set()
            raise error
        async def close(self):
            pass
    application.state.outbound._media_factory = Media
    instrument(application, metadata)
    sid = uuid4()
    media = application.state.outbound._media_factory(sid)
    with pytest.raises(type(error)) as caught:
        await media.send_audio(AudioChunk(sid, 0, b'\0'*640, INTERNAL_AUDIO_FORMAT))
    assert caught.value is error and entered.is_set()
    await media.close()
    assert metadata.close()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[-1]['output_attempted'] == 1
    assert rows[-1]['output_completed'] == 0
    assert rows[-1]['output_'+failure] == 1
    assert 'PRIVATE' not in output.getvalue()


@pytest.mark.asyncio
async def test_voic_ops_008_observer_matches_dialog_without_logging_call_id():
    """PRD-02/03/SRS-T04/I04: given a competing dialog, then only matching SIP is attributed to the active call."""
    output = io.StringIO()
    metadata = Metadata(output)
    application = app()
    sid = uuid4()
    inbound = application.state.inbound
    inbound._dialog = SimpleNamespace(context=SimpleNamespace(session_id=sid), call_id='PRIVATE-VALID')
    forwarded = []
    async def handle(raw, source):
        forwarded.append((raw, source))
        return 'original-result'
    inbound.handle_packet = handle
    instrument(application, metadata)
    for call_id in ('PRIVATE-VALID', 'PRIVATE-OTHER'):
        raw = (f'BYE sip:PRIVATE@example.test SIP/2.0\r\nCall-ID: {call_id}\r\n'
               'Content-Length: 0\r\n\r\n').encode()
        assert await inbound.handle_packet(raw, inbound.peer) == 'original-result'
    assert len(forwarded) == 2
    assert metadata.close()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]['matched'] and rows[0]['call'] == 'call-1'
    assert rows[1]['matched'] is False and 'call' not in rows[1]
    assert all(row['direction'] == 'inbound' for row in rows)
    assert 'PRIVATE' not in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['normal', 'timeout', 'startup-failed', 'output-failed'])
async def test_voic_ops_008_observer_deadline_and_shutdown_result(monkeypatch, mode):
    """PRD-06/SRS-O07: given server success/failure, then the window always requests exit and only clean shutdown succeeds."""
    import uvicorn
    from tests.integrations.ht813.m10_live_app import serve
    class Server:
        def __init__(self, config):
            assert config.lifespan == 'on'
            self.started = mode != 'startup-failed'
            self.should_exit = False
            self.lifespan = SimpleNamespace(startup_failed=mode == 'startup-failed',
                                            shutdown_failed=False, error_occurred=False,
                                            shutdown_event=asyncio.Event())
        async def serve(self):
            if mode == 'timeout':
                await asyncio.Event().wait()
            while not self.should_exit:
                await asyncio.sleep(0)
            self.lifespan.shutdown_event.set()
    servers = []
    def factory(config):
        server = Server(config)
        servers.append(server)
        return server
    monkeypatch.setattr(uvicorn, 'Server', factory)
    class Output(io.StringIO):
        def write(self, text):
            if mode == 'output-failed':
                raise BrokenPipeError('PRIVATE')
            return super().write(text)
    output = Output()
    metadata = Metadata(output)
    result = await serve(None, metadata, .01, shutdown_grace=.02)
    assert result == (0 if mode == 'normal' else 1)
    assert servers[0].should_exit
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    if mode != 'output-failed':
        assert any(row['event'] == 'window_expired' for row in rows)
        expected = 'stopped' if mode == 'normal' else 'shutdown_failed'
        assert rows[-1]['event'] == expected
    else:
        assert metadata.evidence_lost


@pytest.mark.parametrize('digit,expected', [('5', '5'), ('#', '#'), ('8', 'other')])
def test_voic_ops_008_observer_only_exposes_approved_dtmf_symbols(digit, expected):
    """PRD-02/SRS-T03: given DTMF input, then only the two planned symbols are distinguishable."""
    output = io.StringIO()
    metadata = Metadata(output)
    sid = uuid4()
    metadata.event(EventEnvelope(sid, 0, DtmfEvent(sid, digit, 160)))
    assert metadata.close()
    row = json.loads(output.getvalue())
    assert row['test_symbol'] == expected
    assert set(row) == {'event', 'utc', 'elapsed_s', 'call', 'test_symbol', 'duration_ms'}


@pytest.mark.asyncio
async def test_voic_ops_008_observer_outbound_peer_matches_original_invite():
    """PRD-02/SRS-T04: given a peer with unrelated responses, then only its original Call-ID gets a call alias."""
    from voice_agent.channels.ht813.sip import parse_sip
    output = io.StringIO()
    metadata = Metadata(output)
    application = app()
    gate = application.state.operator_calls.gate
    sid = uuid4()
    lease = await gate.acquire(sid)
    received = parse_sip(b'SIP/2.0 200 OK\r\nCall-ID: PRIVATE-OTHER\r\nCSeq: 1 INVITE\r\n\r\n')
    calls = []
    class Peer:
        async def send(self, raw):
            calls.append(raw)
        async def receive(self, timeout):
            assert timeout == .5
            return received
        async def close(self):
            calls.append('closed')
    application.state.outbound._peer_factory = lambda *args: Peer()
    instrument(application, metadata)
    peer = application.state.outbound._peer_factory()
    raw = b'INVITE sip:PRIVATE@example.test SIP/2.0\r\nCall-ID: PRIVATE-CALL\r\n\r\n'
    await peer.send(raw)
    assert await peer.receive(.5) is received
    await peer.close()
    await lease.release()
    assert calls == [raw, 'closed']
    assert metadata.close()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]['matched'] and rows[0]['direction'] == 'outbound'
    assert rows[1]['matched'] is False and 'call' not in rows[1]
    assert 'PRIVATE' not in output.getvalue()
