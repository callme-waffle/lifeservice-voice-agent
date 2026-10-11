"""VOIC-FEAT-001 M6-S2: PRD-02/03/05/06 and SRS-T01~T06/I01~I05/C02~C05."""

from __future__ import annotations

import asyncio
import audioop
import re
import socket
import struct
from uuid import uuid4

import pytest

from voice_agent.channels.ht813.call_manager import OutboundCallManager
from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.outbound import HT813Outbound
from voice_agent.channels.ht813.sip import SIPMessage, parse_sip, request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, DtmfEvent, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import (
    AllowedNumberPolicy, CallState, CallStatus, DialNumber, OutboundCallRequest,
    SessionState, SessionStatus, StepTimeouts, TaskResult, Transcript,
)
from voice_agent.core.orchestrator import VoiceOrchestrator


LOCAL = "127.0.0.1"
ALLOWED = "12345"  # Synthetic destination only; this test never addresses a real device.


def udp_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL, 0))
    sock.setblocking(False)
    return sock


def available_ports(count: int) -> tuple[int, ...]:
    reservations = [udp_socket() for _ in range(count)]
    try:
        return tuple(sock.getsockname()[1] for sock in reservations)
    finally:
        for sock in reservations:
            sock.close()


async def sip_receive(sock: socket.socket, timeout: float = 2) -> SIPMessage:
    raw, source = await asyncio.wait_for(
        asyncio.get_running_loop().sock_recvfrom(sock, 65535), timeout,
    )
    assert source[0] == LOCAL
    return parse_sip(raw)


async def sip_send(sock: socket.socket, raw: bytes, port: int) -> None:
    await asyncio.get_running_loop().sock_sendto(sock, raw, (LOCAL, port))


def response(invite: SIPMessage, status: int, *, media_port: int = 0) -> bytes:
    body = b""
    if status == 200:
        body = (
            "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=loopback\r\n"
            "c=IN IP4 127.0.0.1\r\nt=0 0\r\n"
            f"m=audio {media_port} RTP/AVP 0 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
        ).encode()
    fields = {
        "Via": invite.headers["via"],
        "From": invite.headers["from"],
        "To": invite.headers["to"] + ";tag=synthetic-peer",
        "Call-ID": invite.headers["call-id"],
        "CSeq": invite.headers["cseq"],
    }
    head = [f"SIP/2.0 {status} {'Ringing' if status == 180 else 'OK'}"]
    head += [f"{key}: {value}" for key, value in fields.items()]
    if body:
        head.append("Content-Type: application/sdp")
    head.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(head) + "\r\n\r\n").encode() + body


def inbound_request(method: str, *, sip_port: int, peer_port: int,
                    media_port: int, call_id: str, caller: str = "other",
                    sdp_host: str = LOCAL) -> bytes:
    headers = {
        "Via": f"SIP/2.0/UDP {LOCAL}:{peer_port};branch=z9hG4bKsynthetic",
        "From": f"<sip:{caller}@{LOCAL}>;tag=synthetic-peer",
        "To": f"<sip:agent@{LOCAL}:{sip_port}>",
        "Call-ID": call_id,
        "CSeq": f"{1 if method in ('INVITE', 'ACK', 'CANCEL') else 2} {method}",
    }
    body = b""
    if method == "INVITE":
        headers["Content-Type"] = "application/sdp"
        body = (
            f"v=0\r\no=- 1 1 IN IP4 {LOCAL}\r\ns=loopback\r\n"
            f"c=IN IP4 {sdp_host}\r\nt=0 0\r\n"
            f"m=audio {media_port} RTP/AVP 0 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
        ).encode()
    return request_bytes(method, f"sip:agent@{LOCAL}:{sip_port}", headers, body)


def media_port_from_sdp(body: bytes) -> int:
    match = re.search(rb"^m=audio (\d+) RTP/AVP", body, re.MULTILINE)
    assert match is not None
    return int(match.group(1))


async def rtp_turn(sock: socket.socket, port: int, start: int) -> int:
    """Send 20 ms PCMU packets with 60 ms synthetic speech and 120 ms silence."""
    audible = audioop.lin2ulaw((1200).to_bytes(2, "little", signed=True) * 160, 2)
    silent = audioop.lin2ulaw(b"\0" * 320, 2)
    loop = asyncio.get_running_loop()
    for offset in range(9):
        packet = struct.pack("!BBHII", 0x80, 0, (start + offset) & 0xFFFF,
                             (start + offset) * 160, 0x10020030)
        await loop.sock_sendto(sock, packet + (audible if offset < 3 else silent),
                               (LOCAL, port))
        await asyncio.sleep(.02)
    return start + 9


async def rtp_output(sock: socket.socket, count: int = 5) -> list[bytes]:
    packets = []
    for _ in range(count):
        packet, source = await asyncio.wait_for(
            asyncio.get_running_loop().sock_recvfrom(sock, 2048), 2,
        )
        assert source[0] == LOCAL and packet[0] >> 6 == 2
        assert packet[1] & 0x7F == 0 and len(packet) > 12
        packets.append(packet)
    sequences = [int.from_bytes(packet[2:4], "big") for packet in packets]
    assert all((right - left) & 0xFFFF == 1 for left, right in zip(sequences, sequences[1:]))
    return packets


async def until(predicate, timeout: float = 2) -> None:
    async def wait() -> None:
        while not predicate():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), timeout)


class Events:
    def __init__(self) -> None:
        self.items = []

    async def publish(self, event) -> None:
        self.items.append(event)

    def call_statuses(self) -> list[CallStatus]:
        return [item.payload.status for item in self.items
                if isinstance(item.payload, CallState)]

    def session_statuses(self) -> list[SessionStatus]:
        return [item.payload.status for item in self.items
                if isinstance(item.payload, SessionState)]


class SyntheticSTT:
    def __init__(self) -> None:
        self.count = 0
        self.bytes_seen = 0

    async def transcribe(self, audio, context, cancel):
        async for chunk in audio:
            self.bytes_seen += len(chunk.data)
        self.count += 1
        yield Transcript(f"synthetic-question-{self.count}", True)


class SyntheticTask:
    def __init__(self) -> None:
        self.calls = []

    async def process(self, text, context, cancel, *, history=()):
        self.calls.append((context.session_id, text, tuple(history)))
        return TaskResult(f"synthetic-answer-{len(self.calls)}")


class SyntheticTTS:
    def __init__(self) -> None:
        self.count = 0

    async def synthesize(self, text, context, cancel):
        self.count += 1
        yield AudioChunk(context.session_id, 0,
                         (900).to_bytes(2, "little", signed=True) * 1600,
                         INTERNAL_AUDIO_FORMAT)


def core(gate: SingleSessionGate):
    stt, task, tts = SyntheticSTT(), SyntheticTask(), SyntheticTTS()
    runner = VoiceOrchestrator(stt, task, tts, gate, StepTimeouts(2, 2, 2))
    return runner, stt, task, tts


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_outbound_udp_rtp_two_turns_dtmf_and_remote_bye():
    """PRD-02/05/06, SRS-T01~T06: given an allowed loopback peer, when two turns and BYE arrive, then RTP, DTMF, context and lease end correctly."""
    peer_sip, peer_rtp = udp_socket(), udp_socket()
    app_sip, app_rtp = available_ports(2)
    gate = SingleSessionGate()
    runner, stt, task, tts = core(gate)
    channel = HT813Outbound(
        host=LOCAL, port=peer_sip.getsockname()[1], local_host=LOCAL,
        local_sip_port=app_sip, local_rtp_port=app_rtp, user_id="agent",
        policy=AllowedNumberPolicy(exact=frozenset({ALLOWED})),
    )
    manager = OutboundCallManager(channel, runner, gate, TurnBoundary(400, 100, 2000))
    events = Events()
    cancel = CancellationToken()
    call = None
    try:
        with pytest.raises(PermissionError):
            await manager.call(
                OutboundCallRequest(uuid4(), DialNumber("99999"), 1), events, cancel,
            )
        with pytest.raises(TimeoutError):
            await sip_receive(peer_sip, .05)
        assert gate.active_session_id is None

        request = OutboundCallRequest(uuid4(), DialNumber(ALLOWED), 2)
        call = asyncio.create_task(manager.call(request, events, cancel))
        invite = await sip_receive(peer_sip)
        assert invite.start.startswith("INVITE ") and ALLOWED in invite.start
        assert media_port_from_sdp(invite.body) == app_rtp
        await sip_send(peer_sip, response(invite, 180), app_sip)
        await sip_send(peer_sip, response(invite, 200,
                                          media_port=peer_rtp.getsockname()[1]), app_sip)
        ack = await sip_receive(peer_sip)
        assert ack.start.startswith("ACK ")
        await until(lambda: CallStatus.ACTIVE in events.call_statuses())
        assert gate.active_session_id == request.session_id

        dtmf = struct.pack("!BBHII", 0x80, 101, 500, 9999, 0x10020030)
        await asyncio.get_running_loop().sock_sendto(
            peer_rtp, dtmf + b"\x01\x8a\x01\x40", (LOCAL, app_rtp),
        )
        await until(lambda: any(isinstance(item.payload, DtmfEvent) for item in events.items))
        digit = next(item.payload for item in events.items
                     if isinstance(item.payload, DtmfEvent))
        assert (digit.digit, digit.duration_ms) == ("1", 40)

        next_sequence = await rtp_turn(peer_rtp, app_rtp, 0)
        await until(lambda: tts.count == 1)
        assert len(await rtp_output(peer_rtp)) == 5
        await asyncio.sleep(.05)  # The next utterance reader resumes after the first reply.
        assert not call.done() and gate.active_session_id == request.session_id
        with pytest.raises(TimeoutError):
            await sip_receive(peer_sip, .05)  # No automatic BYE after the first answer.

        await rtp_turn(peer_rtp, app_rtp, next_sequence)
        await until(lambda: tts.count == 2)
        assert events.session_statuses().count(SessionStatus.LISTENING) == 2
        assert len(await rtp_output(peer_rtp)) == 5
        assert stt.count == 2 and stt.bytes_seen > 0
        assert len(task.calls) == 2
        assert task.calls[0][2] == ()
        assert len(task.calls[1][2]) == 1
        assert task.calls[1][2][0].user_text == task.calls[0][1]
        assert task.calls[0][0] == task.calls[1][0] == request.session_id
        assert not call.done()

        bye = request_bytes("BYE", f"sip:agent@{LOCAL}:{app_sip}", {
            "Via": f"SIP/2.0/UDP {LOCAL}:{peer_sip.getsockname()[1]};branch=z9hG4bKbye",
            "From": response(invite, 180).decode().split("To: ", 1)[1].split("\r\n", 1)[0],
            "To": invite.headers["from"],
            "Call-ID": invite.headers["call-id"], "CSeq": "2 BYE",
        })
        await sip_send(peer_sip, bye, app_sip)
        assert (await sip_receive(peer_sip)).status == 200
        await asyncio.wait_for(call, 2)
        assert events.call_statuses()[-1] is CallStatus.ENDED
        assert gate.active_session_id is None and channel._media is None
    finally:
        cancel.cancel()
        if call is not None and not call.done():
            await asyncio.wait_for(call, 3)
        peer_sip.close()
        peer_rtp.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_inbound_udp_rtp_all_callers_busy_and_remote_bye():
    """PRD-03/06, SRS-I01~I05: given a trusted loopback peer, when caller IDs vary and two turns finish, then RTP and the shared lease follow BYE."""
    peer_sip, peer_rtp, rogue_sip = udp_socket(), udp_socket(), udp_socket()
    app_sip, app_rtp = available_ports(2)
    gate = SingleSessionGate()
    runner, stt, task, tts = core(gate)
    events = Events()
    service = InboundSIPService(
        peer_host=LOCAL, peer_port=peer_sip.getsockname()[1], local_host=LOCAL,
        sip_port=app_sip, rtp_port=app_rtp, user_id="agent", runner=runner,
        gate=gate, boundary=TurnBoundary(400, 100, 2000), events=events,
    )
    async def send(method: str, *, call_id: str, caller: str = "other",
                   sdp_host: str = LOCAL, source: socket.socket = peer_sip) -> None:
        await sip_send(source, inbound_request(
            method, sip_port=app_sip, peer_port=peer_sip.getsockname()[1],
            media_port=peer_rtp.getsockname()[1], call_id=call_id,
            caller=caller, sdp_host=sdp_host,
        ), app_sip)

    try:
        await service.start()
        await send("INVITE", call_id="rogue", source=rogue_sip)
        with pytest.raises(TimeoutError):
            await sip_receive(rogue_sip, .05)
        assert gate.active_session_id is None and stt.count == 0
        await sip_send(peer_sip, b"BROKEN", app_sip)
        assert (await sip_receive(peer_sip)).status == 400
        await send("INVITE", call_id="invalid", sdp_host="127.0.0.2")
        assert (await sip_receive(peer_sip)).status == 488
        assert stt.count == 0

        await send("INVITE", call_id="first", caller="displayed")
        assert (await sip_receive(peer_sip)).status == 100
        answer = await sip_receive(peer_sip)
        assert answer.status == 200
        assert media_port_from_sdp(answer.body) == app_rtp
        await send("ACK", call_id="first", caller="displayed")
        await until(lambda: CallStatus.ACTIVE in events.call_statuses())
        first_session = gate.active_session_id
        assert first_session is not None

        await send("INVITE", call_id="competing", caller="anonymous")
        assert (await sip_receive(peer_sip)).status == 486
        assert gate.active_session_id == first_session

        next_sequence = await rtp_turn(peer_rtp, app_rtp, 0)
        await until(lambda: tts.count == 1)
        assert len(await rtp_output(peer_rtp)) == 5
        await asyncio.sleep(.05)  # The next utterance reader resumes after the first reply.
        assert gate.active_session_id == first_session
        next_sequence = await rtp_turn(peer_rtp, app_rtp, next_sequence)
        await until(lambda: tts.count == 2)
        assert events.session_statuses().count(SessionStatus.LISTENING) == 2
        assert len(await rtp_output(peer_rtp)) == 5
        assert stt.count == 2 and stt.bytes_seen > 0
        assert len(task.calls) == 2 and len(task.calls[1][2]) == 1
        assert task.calls[0][0] == task.calls[1][0] == first_session

        await send("BYE", call_id="first", caller="displayed")
        assert (await sip_receive(peer_sip)).status == 200
        await until(lambda: gate.active_session_id is None)
        assert events.call_statuses()[-1] is CallStatus.ENDED

        await send("INVITE", call_id="second", caller="anonymous")
        assert (await sip_receive(peer_sip)).status == 100
        assert (await sip_receive(peer_sip)).status == 200
        await send("ACK", call_id="second", caller="anonymous")
        await until(lambda: events.call_statuses().count(CallStatus.ACTIVE) == 2)
        assert gate.active_session_id != first_session
        await send("BYE", call_id="second", caller="anonymous")
        assert (await sip_receive(peer_sip)).status == 200
        await until(lambda: gate.active_session_id is None)
        assert stt.count == 2  # No unexpected model call for busy/invalid/unspeaking calls.

        # PRD-03/06, SRS-I04/C03: application shutdown must notify an active peer.
        await send("INVITE", call_id="shutdown", caller="anonymous")
        assert (await sip_receive(peer_sip)).status == 100
        assert (await sip_receive(peer_sip)).status == 200
        await send("ACK", call_id="shutdown", caller="anonymous")
        await until(lambda: events.call_statuses().count(CallStatus.ACTIVE) == 3)
        await service.close()
        bye = await sip_receive(peer_sip)
        assert bye.start.startswith("BYE ")
        assert bye.headers["call-id"] == "shutdown"
        assert gate.active_session_id is None
        for port in (app_sip, app_rtp):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reclaimed:
                reclaimed.bind((LOCAL, port))
    finally:
        await service.close()
        peer_sip.close()
        peer_rtp.close()
        rogue_sip.close()
