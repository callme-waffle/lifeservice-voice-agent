"""VOIC-FEAT-001 M5-S5: fake SIP/RTP peer tests outbound-only call control."""

import asyncio
from uuid import uuid4

import pytest

from voice_agent.channels.ht813.outbound import HT813Outbound
from voice_agent.channels.ht813.sip import SIPMessage, parse_sip
from voice_agent.contracts.flow import CancellationToken
from voice_agent.contracts.session import (
    AllowedNumberPolicy, CallState, CallStatus, DialNumber, OutboundCallRequest,
)


class Sink:
    def __init__(self, token=None):
        self.events = []
        self.token = token

    async def publish(self, event):
        self.events.append(event)
        if self.token and event.payload == CallState(CallStatus.ACTIVE):
            self.token.cancel()


class FakeMedia:
    instances = []
    def __init__(self, session_id, **kwargs):
        self.local_port = 12000
        self.failed = asyncio.Event()
        self.audio = asyncio.Queue()
        self.dtmf = asyncio.Queue()
        self.closed = False
        self.destination = None
        self.instances.append(self)

    def start(self, *destination):
        self.destination = destination

    async def close(self):
        self.closed = True


class FakePeer:
    instances = []
    response_status = 200
    def __init__(self, host, port, local_host, local_port):
        self.local_port = 19000
        self.sent = []
        self.responses = asyncio.Queue()
        self.closed = False
        self.instances.append(self)

    async def send(self, raw):
        message = parse_sip(raw)
        self.sent.append(message)
        if message.start.startswith("INVITE "):
            headers = {"call-id": message.headers["call-id"],
                       "to": message.headers["to"] + ";tag=peer"}
            if self.response_status == 200:
                await self.responses.put(SIPMessage("SIP/2.0 180 Ringing", headers, b""))
                body = ("v=0\r\nc=IN IP4 192.0.2.17\r\n"
                        "m=audio 22000 RTP/AVP 0 101\r\n"
                        "a=rtpmap:101 telephone-event/8000\r\n").encode()
            else:
                body = b""
            await self.responses.put(SIPMessage(
                f"SIP/2.0 {self.response_status} Result", headers, body))

    async def receive(self, timeout_s):
        return await asyncio.wait_for(self.responses.get(), timeout_s)

    async def close(self):
        self.closed = True


def dialer(policy=None):
    return HT813Outbound(host="192.0.2.17", port=5062,
                         local_host="192.0.2.20", user_id="agent",
                         policy=policy or AllowedNumberPolicy(exact=frozenset({"12345"})),
                         peer_factory=FakePeer, media_factory=FakeMedia)


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_rejects_number_without_sip_packet():
    """Given an unlisted number, when dialing, then no SIP peer is created."""
    before = len(FakePeer.instances)
    request = OutboundCallRequest(uuid4(), DialNumber("99999"), 1)
    with pytest.raises(PermissionError):
        await dialer().dial(request, Sink(), CancellationToken())
    assert len(FakePeer.instances) == before


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_invite_ack_bye_and_cleanup():
    """Given 180/200, when cancelled after active, then ACK/BYE and cleanup occur."""
    FakePeer.response_status = 200
    request = OutboundCallRequest(uuid4(), DialNumber("12345"), 1)
    token = CancellationToken()
    sink = Sink(token)
    channel = dialer()
    await channel.dial(request, sink, token)
    peer, media = FakePeer.instances[-1], FakeMedia.instances[-1]
    statuses = [item.payload.status for item in sink.events]
    assert statuses == [
        CallStatus.DIALING, CallStatus.RINGING, CallStatus.ACTIVE, CallStatus.ENDED], sink.events
    assert [item.sequence for item in sink.events] == list(range(4))
    assert [item.start.split()[0] for item in peer.sent] == ["INVITE", "ACK", "BYE"]
    assert "12345@192.0.2.17" in peer.sent[0].start
    assert media.destination == ("192.0.2.17", 22000, 0, 101)
    assert peer.closed and media.closed


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_busy_response_and_release():
    """Given SIP 486, when dialed, then busy state and resource cleanup occur."""
    FakePeer.response_status = 486
    request = OutboundCallRequest(uuid4(), DialNumber("12345"), 1)
    sink = Sink()
    await dialer().dial(request, sink, CancellationToken())
    assert [item.payload.status for item in sink.events] == [CallStatus.DIALING, CallStatus.BUSY]
    assert [item.start.split()[0] for item in FakePeer.instances[-1].sent] == ["INVITE", "ACK"]
    assert FakePeer.instances[-1].closed and FakeMedia.instances[-1].closed
    FakePeer.response_status = 200


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_second_call_reports_busy():
    """Given occupied call lock, when another request arrives, then it emits busy without SIP."""
    channel = dialer()
    request = OutboundCallRequest(uuid4(), DialNumber("12345"), 1)
    before = len(FakePeer.instances)
    await channel._lock.acquire()
    try:
        sink = Sink()
        await channel.dial(request, sink, CancellationToken())
        assert sink.events[0].payload == CallState(CallStatus.BUSY)
        assert len(FakePeer.instances) == before
    finally:
        channel._lock.release()


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_rtp_failure_sends_bye_and_fails():
    """Given RTP failure after answer, when signaled, then BYE and failed state follow."""
    class FailingSink(Sink):
        async def publish(self, event):
            self.events.append(event)
            if event.payload == CallState(CallStatus.ACTIVE):
                FakeMedia.instances[-1].failed.set()

    FakePeer.response_status = 200
    sink = FailingSink()
    await dialer().dial(OutboundCallRequest(uuid4(), DialNumber("12345"), 1),
                       sink, CancellationToken())
    assert [event.payload.status for event in sink.events][-2:] == [
        CallStatus.ACTIVE, CallStatus.FAILED]
    assert FakePeer.instances[-1].sent[-1].start.startswith("BYE ")
    assert FakeMedia.instances[-1].closed


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_remote_bye_ends_call():
    """Given peer BYE, when active, then local side acknowledges and releases."""
    class RemoteHangupSink(Sink):
        async def publish(self, event):
            self.events.append(event)
            if event.payload == CallState(CallStatus.ACTIVE):
                peer = FakePeer.instances[-1]
                headers = {"call-id": peer.sent[0].headers["call-id"],
                           "via": "SIP/2.0/UDP 192.0.2.17:5062",
                           "from": "<sip:peer@192.0.2.17>;tag=peer",
                           "to": peer.sent[0].headers["from"], "cseq": "2 BYE"}
                await peer.responses.put(SIPMessage(
                    "BYE sip:agent@192.0.2.20 SIP/2.0", headers, b""))

    FakePeer.response_status = 200
    sink = RemoteHangupSink()
    await dialer().dial(OutboundCallRequest(uuid4(), DialNumber("12345"), 1),
                       sink, CancellationToken())
    assert sink.events[-1].payload == CallState(CallStatus.ENDED)
    assert FakePeer.instances[-1].sent[-1].start == "SIP/2.0 200 OK"


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_digest_challenge_retries_without_plain_secret():
    """Given 401, when configured, then one authenticated INVITE is retried."""
    class AuthPeer(FakePeer):
        async def send(self, raw):
            message = parse_sip(raw)
            self.sent.append(message)
            if not message.start.startswith("INVITE "):
                return
            headers = {"call-id": message.headers["call-id"],
                       "to": message.headers["to"] + ";tag=peer"}
            if "authorization" not in message.headers:
                headers["www-authenticate"] = 'Digest realm="fxo", nonce="abc", qop="auth"'
                await self.responses.put(SIPMessage("SIP/2.0 401 Unauthorized", headers, b""))
            else:
                body = ("v=0\r\nc=IN IP4 192.0.2.17\r\n"
                        "m=audio 22000 RTP/AVP 0\r\n").encode()
                await self.responses.put(SIPMessage("SIP/2.0 200 OK", headers, body))

    token = CancellationToken()
    channel = HT813Outbound(host="192.0.2.17", port=5062,
                            local_host="192.0.2.20", user_id="agent", password="private-pass",
                            policy=AllowedNumberPolicy(exact=frozenset({"12345"})),
                            peer_factory=AuthPeer, media_factory=FakeMedia)
    await channel.dial(OutboundCallRequest(uuid4(), DialNumber("12345"), 1), Sink(token), token)
    peer = AuthPeer.instances[-1]
    assert [item.start.split()[0] for item in peer.sent] == [
        "INVITE", "ACK", "INVITE", "ACK", "BYE"]
    assert "authorization" in peer.sent[2].headers
    assert "private-pass" not in peer.sent[2].headers["authorization"]


@pytest.mark.asyncio
@pytest.mark.parametrize("final_status,methods", [
    (487, ["INVITE", "CANCEL", "ACK"]),
    (200, ["INVITE", "CANCEL", "ACK", "BYE"]),
])
async def test_voic_feat_001_m5_s5_cancel_pending_invite_acks_final_response(final_status, methods):
    """Given cancellation, when 487 or late 200 arrives, then ACK/BYE closes the call."""
    class PendingPeer(FakePeer):
        async def send(self, raw):
            message = parse_sip(raw)
            self.sent.append(message)
            if message.start.startswith("INVITE "):
                token.cancel()
            if message.start.startswith("CANCEL "):
                headers = {"call-id": message.headers["call-id"],
                           "to": message.headers["to"] + ";tag=peer",
                           "cseq": "1 INVITE"}
                await self.responses.put(SIPMessage(
                    f"SIP/2.0 {final_status} Result", headers, b""))

    token = CancellationToken()
    channel = HT813Outbound(host="192.0.2.17", port=5062,
                            local_host="192.0.2.20", user_id="agent",
                            policy=AllowedNumberPolicy(exact=frozenset({"12345"})),
                            peer_factory=PendingPeer, media_factory=FakeMedia)
    sink = Sink()
    await channel.dial(OutboundCallRequest(uuid4(), DialNumber("12345"), 1), sink, token)
    assert [item.start.split()[0] for item in PendingPeer.instances[-1].sent] == methods
    assert sink.events[-1].payload == CallState(CallStatus.ENDED)
