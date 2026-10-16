"""VOIC-FEAT-001 M6-S1-T5: fake HT813 SIP and RTP receive boundary."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from voice_agent.channels.ht813.inbound import InboundSIPService, extract_caller_number
from voice_agent.channels.ht813.sip import parse_sip, request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import (
    CallState, CallStatus, SessionState, SessionStatus, StepTimeouts, TaskResult, Transcript,
)
from voice_agent.core.orchestrator import VoiceOrchestrator

PEER = ("192.0.2.17", 5062)
LOCAL = "192.0.2.50"


@pytest.mark.parametrize("source,headers,expected", [
    ("from", {"from": "<sip:+821012345678@example.test>;tag=x"}, "+821012345678"),
    ("p-asserted-identity", {"from": "<sip:agent@example.test>",
                             "p-asserted-identity": "<tel:01012345678>"}, "01012345678"),
    ("p-preferred-identity", {"p-preferred-identity": "<sip:0212345678@example.test>"}, "0212345678"),
    ("disabled", {"from": "<sip:01012345678@example.test>"}, None),
    ("from", {"from": "<sip:12345678@example.test>"}, None),
    ("from", {"from": "<sip:anonymous@example.test>"}, None),
])
def test_voic_feat_004_m7_s2_t1_reads_only_configured_caller_header(source, headers, expected):
    """Given one configured identity header, when parsed, then only a real number is returned."""
    assert extract_caller_number(headers, source=source, account_id="12345678") == expected


def packet(method, call_id="test-call", caller="caller", sdp=True):
    headers = {
        "Via": "SIP/2.0/UDP 192.0.2.17:5062;branch=z9hG4bKtest",
        "From": f"<sip:{caller}@192.0.2.17>;tag=remote",
        "To": f"<sip:agent@{LOCAL}:5061>",
        "Call-ID": call_id,
        "CSeq": f"{1 if method in ('INVITE', 'ACK', 'CANCEL') else 2} {method}",
    }
    body = b""
    if sdp:
        headers["Content-Type"] = "application/sdp"
        body = ("v=0\r\no=- 1 1 IN IP4 192.0.2.17\r\ns=test\r\n"
                "c=IN IP4 192.0.2.17\r\nt=0 0\r\n"
                "m=audio 3000 RTP/AVP 0 8 101\r\n"
                "a=rtpmap:101 telephone-event/8000\r\n").encode()
    return request_bytes(method, f"sip:agent@{LOCAL}:5061", headers, body)


def frame(sid, seq, sample):
    return AudioChunk(sid, seq, sample.to_bytes(2, "little", signed=True) * 320,
                      INTERNAL_AUDIO_FORMAT)


class FakeMedia:
    def __init__(self, sid, *, local_host, local_port):
        self.sid, self.local_host, self.local_port = sid, local_host, local_port
        self.audio, self.dtmf, self.failed = asyncio.Queue(), asyncio.Queue(), asyncio.Event()
        self.sent = []
        self.closed = False
        self.destination = None

    def start(self, host, port, codec, telephone):
        self.destination = (host, port, codec, telephone)

    async def send_audio(self, chunk):
        self.sent.append(chunk)

    async def close(self):
        self.closed = True


class Events:
    def __init__(self):
        self.items = []

    async def publish(self, event):
        self.items.append(event)


async def wait_for(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 1)


def service(runner=None, gate=None, retention=None):
    sent, medias, events = [], [], Events()
    async def send(data, source):
        assert source == PEER
        sent.append(parse_sip(data))
    def media_factory(sid, **kwargs):
        media = FakeMedia(sid, **kwargs)
        medias.append(media)
        return media
    if gate is None:
        gate = SingleSessionGate()
    instance = InboundSIPService(
        peer_host=PEER[0], peer_port=PEER[1], local_host=LOCAL,
        sip_port=5061, rtp_port=4002, user_id="agent",
        runner=runner or object(), gate=gate, boundary=TurnBoundary(400, 100, 2000),
        events=events, retention=retention,
        media_factory=media_factory, send_packet=send,
    )
    return instance, gate, sent, medias, events


@pytest.mark.asyncio
async def test_voic_feat_004_m7_s2_t1_inbound_records_speechless_cancel():
    """Given a trusted incoming call without speech, when cancelled, then start/end are recorded."""
    class FakeRetention:
        def __init__(self):
            self.starts = []
            self.ends = []
        async def record_call_start(self, context, caller_number):
            self.starts.append((context, caller_number))
        async def record_call_end(self, context, status):
            self.ends.append((context, status))

    store = FakeRetention()
    inbound, gate, sent, medias, _ = service(retention=store)
    await inbound.handle_packet(packet("INVITE", caller="01012345678"), PEER)
    assert len(store.starts) == 1
    assert store.starts[0][1] == "01012345678"
    await inbound.handle_packet(packet("CANCEL", sdp=False), PEER)
    await wait_for(lambda: len(store.ends) == 1)
    assert store.ends[0] == (store.starts[0][0], "ended")
    assert gate.active_session_id is None
    assert medias[0].closed


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_inbound_two_turns_until_remote_bye():
    """Given trusted INVITE, when two turns arrive, then one SIP dialog stays active until BYE."""
    gate = SingleSessionGate()
    seen = []

    class STT:
        index = 0
        async def transcribe(self, audio, context, cancel):
            async for _ in audio:
                pass
            self.index += 1
            yield Transcript(f"질문{self.index}", True)

    class Task:
        async def process(self, text, context, cancel, *, history=()):
            seen.append((text, history))
            return TaskResult(f"답변{len(seen)}")

    class TTS:
        async def synthesize(self, text, context, cancel):
            yield frame(context.session_id, 0, 1000)

    runner = VoiceOrchestrator(STT(), Task(), TTS(), gate, StepTimeouts(1, 1, 1))
    inbound, gate, sent, medias, events = service(runner, gate)
    await inbound.handle_packet(packet("INVITE"), PEER)
    await wait_for(lambda: any(m.status == 200 for m in sent))
    answer = next(m for m in sent if m.status == 200)
    assert b"m=audio 4002 RTP/AVP 0 101" in answer.body
    await inbound.handle_packet(packet("ACK", sdp=False), PEER)
    media = medias[0]
    assert media.destination == (PEER[0], 3000, 0, 101)

    async def push_turn(start):
        await media.audio.put(frame(media.sid, start, 1000))
        for index in range(5):
            await media.audio.put(frame(media.sid, start + index + 1, 0))

    await push_turn(0)
    await wait_for(lambda: len(media.sent) == 1)
    assert gate.active_session_id == media.sid
    await asyncio.sleep(.01)
    await push_turn(6)
    await wait_for(lambda: len(media.sent) == 2)
    assert [chunk.sequence for chunk in media.sent] == [0, 1]
    assert len(seen[1][1]) == 1
    assert not media.closed
    await inbound.handle_packet(packet("BYE", sdp=False), PEER)
    await wait_for(lambda: gate.active_session_id is None)
    assert media.closed
    assert [e.sequence for e in events.items] == list(range(len(events.items)))
    assert events.items[-1].payload == CallState(CallStatus.ENDED)
    await inbound.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("caller", ["other-number", "anonymous"])
async def test_voic_feat_001_m6_s1_t5_caller_id_does_not_filter(caller):
    """Given different or hidden Caller ID, when trusted peer calls, then both are accepted."""
    inbound, gate, sent, medias, events = service()
    await inbound.handle_packet(packet("INVITE", caller=caller), PEER)
    await wait_for(lambda: any(m.status == 200 for m in sent))
    assert gate.active_session_id is not None
    await inbound.handle_packet(packet("BYE", sdp=False), PEER)
    await wait_for(lambda: gate.active_session_id is None)
    assert medias[0].closed
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_rejects_untrusted_bad_sdp_and_busy():
    """Given wrong peer, invalid SDP or occupied gate, when invited, then model stays unused."""
    inbound, gate, sent, medias, _ = service()
    await inbound.handle_packet(packet("INVITE"), ("192.0.2.1", 5062))
    assert sent == [] and medias == []
    bad = packet("INVITE").replace(b"c=IN IP4 192.0.2.17", b"c=IN IP4 192.0.2.99")
    await inbound.handle_packet(bad, PEER)
    assert sent[-1].status == 488
    assert medias == []
    lease = await gate.acquire(uuid4())
    await inbound.handle_packet(packet("INVITE"), PEER)
    assert sent[-1].status == 486
    assert medias == []
    await lease.release()
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_early_cancel_returns_487_and_releases():
    """Given early INVITE cancellation, when CANCEL arrives, then 200/487 and lease release."""
    inbound, gate, sent, medias, _ = service()
    await inbound.handle_packet(packet("INVITE"), PEER)
    await inbound.handle_packet(packet("CANCEL", sdp=False), PEER)
    await wait_for(lambda: gate.active_session_id is None)
    assert [message.status for message in sent] == [100, 200, 487]
    assert medias[0].closed
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_media_failure_sends_bye_and_cleans():
    """Given accepted SIP with RTP failure, when media fails, then BYE and lease cleanup."""
    inbound, gate, sent, medias, _ = service()
    await inbound.handle_packet(packet("INVITE"), PEER)
    await wait_for(lambda: any(m.status == 200 for m in sent))
    await inbound.handle_packet(packet("ACK", sdp=False), PEER)
    medias[0].failed.set()
    await wait_for(lambda: gate.active_session_id is None)
    assert any(m.start.startswith("BYE ") for m in sent)
    assert medias[0].closed
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_retransmit_and_competing_invite():
    """Given one pending dialog, when INVITE repeats or another arrives, then retry or busy."""
    inbound, gate, sent, medias, _ = service()
    first = packet("INVITE", call_id="first")
    await inbound.handle_packet(first, PEER)
    await inbound.handle_packet(first, PEER)
    assert [item.status for item in sent] == [100, 100]
    await inbound.handle_packet(packet("INVITE", call_id="second"), PEER)
    assert sent[-1].status == 486
    assert len(medias) == 1
    await inbound.handle_packet(packet("CANCEL", call_id="first", sdp=False), PEER)
    await wait_for(lambda: gate.active_session_id is None)
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t5_malformed_invite_fails_before_media():
    """Given missing SIP fields or unsupported codec, when invited, then reject before media."""
    inbound, gate, sent, medias, _ = service()
    missing = packet("INVITE").replace(b"Call-ID: test-call\r\n", b"")
    await inbound.handle_packet(missing, PEER)
    assert sent[-1].status == 400
    unsupported = packet("INVITE").replace(b"RTP/AVP 0 8 101", b"RTP/AVP 9 101")
    await inbound.handle_packet(unsupported, PEER)
    assert sent[-1].status == 488
    assert medias == []
    assert gate.active_session_id is None
    await inbound.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_invite_answer_advertises_ack_contact():
    """Given a direct peer INVITE, when accepted, then 200 advertises the ACK target (RFC3261 12.1.1)."""
    inbound, gate, sent, medias, events = service()
    try:
        await inbound.handle_packet(packet('INVITE'), PEER)
        await wait_for(lambda: any(m.status == 200 for m in sent))
        answer = next(m for m in sent if m.status == 200)
        assert answer.headers.get('contact') == f'<sip:agent@{LOCAL}:5061>'
        assert f'c=IN IP4 {LOCAL}'.encode() in answer.body
        await inbound.handle_packet(packet('INVITE'), PEER)
        assert sent[-1].headers['contact'] == answer.headers['contact']
    finally:
        await inbound.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('send_failure', [False, True])
async def test_voic_feat_001_m6_s2_shutdown_sends_bye_before_releasing(send_failure):
    """Given an active call, when the app closes, then BYE is attempted and cleanup survives send failure."""
    class WaitingRunner:
        async def run_call(self, context, turns, events, send_audio, cancel, **kwargs):
            await cancel.wait()

    inbound, gate, sent, medias, _ = service(WaitingRunner())
    await inbound.handle_packet(packet('INVITE'), PEER)
    await wait_for(lambda: any(m.status == 200 for m in sent))
    await inbound.handle_packet(packet('ACK', sdp=False), PEER)
    bye_attempts = []
    original_send = inbound._send_packet

    async def observed_send(data, peer):
        message = parse_sip(data)
        if message.start.startswith('BYE '):
            bye_attempts.append(message)
            assert not medias[0].closed
            assert gate.active_session_id is not None
            if send_failure:
                raise OSError('synthetic send failure')
        await original_send(data, peer)

    inbound._send_packet = observed_send
    try:
        await inbound.close()
        assert len(bye_attempts) == 1
        assert bye_attempts[0].headers['call-id'] == 'test-call'
        assert medias[0].closed
        assert gate.active_session_id is None
        await inbound.close()
        assert len(bye_attempts) == 1
    finally:
        await inbound.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ending_method", [
    "BYE", "CANCEL", "MEDIA_FAILURE", "ACK_SEND_FAILURE", "CONVERSATION_END",
])
async def test_voic_bug_009_close_waits_for_pending_termination(ending_method):
    """Given blocked end retention on each termination path, when closing, then wait for cleanup.

    VOIC-BUG-009: media and retention are fakes; Events fix the shutdown race
    without a real socket, filesystem, model, or wall-clock timing assumption.
    """
    entered, release, close_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    ended = []

    class WaitingRunner:
        async def run_call(self, context, turns, events, send_audio, cancel, **kwargs):
            if ending_method != "CONVERSATION_END":
                await cancel.wait()

    class BlockingRetention:
        async def record_call_start(self, context, caller_number):
            pass

        async def record_call_end(self, context, status):
            entered.set()
            await release.wait()
            ended.append((context.session_id, status))

    inbound, gate, sent, medias, _ = service(WaitingRunner(), retention=BlockingRetention())
    closing = None
    expected_status = "ended" if ending_method in ("BYE", "CANCEL") else "failed"
    original_send = inbound._send_packet

    async def send(data, peer):
        if ending_method == "ACK_SEND_FAILURE" and parse_sip(data).status == 200:
            raise OSError("synthetic answer send failure")
        await original_send(data, peer)

    inbound._send_packet = send
    try:
        await inbound.handle_packet(packet("INVITE"), PEER)
        sid = gate.active_session_id
        if ending_method not in ("CANCEL", "ACK_SEND_FAILURE"):
            await wait_for(lambda: any(message.status == 200 for message in sent))
            await inbound.handle_packet(packet("ACK", sdp=False), PEER)
        if ending_method in ("BYE", "CANCEL"):
            await inbound.handle_packet(packet(ending_method, sdp=False), PEER)
        elif ending_method == "MEDIA_FAILURE":
            medias[0].failed.set()
        await asyncio.wait_for(entered.wait(), 1)
        assert gate.active_session_id == sid
        assert medias[0].closed

        async def close_service():
            close_started.set()
            await inbound.close()

        closing = asyncio.create_task(close_service())
        await close_started.wait()
        assert not closing.done(), "close returned before pending termination released its lease"
        release.set()
        await asyncio.wait_for(closing, 1)
        assert ended == [(sid, expected_status)]
        assert gate.active_session_id is None
        await inbound.close()
        assert ended == [(sid, expected_status)]
    finally:
        release.set()
        if closing is not None:
            await asyncio.wait_for(closing, 1)
        await wait_for(lambda: gate.active_session_id is None)
        await inbound.close()


@pytest.mark.asyncio
async def test_voic_bug_009_close_preserves_packet_error_cleanup():
    """Given packet-error cleanup awaiting the runner, when closing, then reclaim resources.

    VOIC-BUG-009: fake dispatch, media and retention use Events to put shutdown
    inside conversation cleanup, without sockets or elapsed-time assumptions.
    """
    running, cleaning, release, close_started = (asyncio.Event() for _ in range(4))
    ended = []

    class WaitingRunner:
        async def run_call(self, context, turns, events, send_audio, cancel, **kwargs):
            running.set()
            await cancel.wait()
            cleaning.set()
            await release.wait()

    class Retention:
        async def record_call_start(self, context, caller_number):
            pass

        async def record_call_end(self, context, status):
            ended.append((context.session_id, status))

    inbound, gate, sent, medias, _ = service(WaitingRunner(), retention=Retention())
    dispatch = closing = dialog = None
    try:
        await inbound.handle_packet(packet("INVITE"), PEER)
        await wait_for(lambda: any(message.status == 200 for message in sent))
        await inbound.handle_packet(packet("ACK", sdp=False), PEER)
        await asyncio.wait_for(running.wait(), 1)
        dialog = inbound._dialog
        sid = gate.active_session_id

        async def fail_packet(data, source):
            raise RuntimeError("synthetic packet handler failure")

        inbound.handle_packet = fail_packet
        dispatch = asyncio.create_task(inbound._dispatch_packet(b"synthetic", PEER))
        inbound._packets.add(dispatch)
        dispatch.add_done_callback(inbound._packets.discard)
        await asyncio.wait_for(cleaning.wait(), 1)
        assert gate.active_session_id == sid
        assert not medias[0].closed

        async def close_service():
            close_started.set()
            await inbound.close()

        closing = asyncio.create_task(close_service())
        await close_started.wait()
        release.set()
        await asyncio.wait_for(closing, 1)
        assert medias[0].closed, "close cancelled packet-error cleanup before media close"
        assert gate.active_session_id is None
        assert ended == [(sid, "failed")]
        await inbound.close()
        assert ended == [(sid, "failed")]
    finally:
        release.set()
        await asyncio.gather(*(task for task in (closing, dispatch) if task is not None),
                             return_exceptions=True)
        # Reclaim fake resources even when the pre-fix assertion exposes the leak.
        if dialog is not None:
            if dialog.media_watch is not None:
                dialog.media_watch.cancel()
                await asyncio.gather(dialog.media_watch, return_exceptions=True)
            await dialog.media.close()
            await dialog.lease.release()
        await inbound.close()
