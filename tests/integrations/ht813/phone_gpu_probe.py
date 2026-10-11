"""VOIC-FEAT-001 M6-S2: PRD-02/05/06, SRS-T02/T03/T05/T06/C02/C05 GPU phone probe."""

from __future__ import annotations

import asyncio
import audioop
import json
import re
import socket
import struct
import time
import wave
from pathlib import Path

from voice_agent.adapters.stt.faster_whisper import FasterWhisperSTT
from voice_agent.adapters.tts.melo import MeloTTSAdapter
from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.sip import parse_sip, request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import CallState, CallStatus, SessionState, SessionStatus, StepTimeouts, TaskResult
from voice_agent.core.orchestrator import VoiceOrchestrator


LOCAL = "127.0.0.1"


def udp_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL, 0))
    sock.setblocking(False)
    return sock


async def receive_sip(sock: socket.socket, timeout: float = 4):
    packet, source = await asyncio.wait_for(asyncio.get_running_loop().sock_recvfrom(sock, 65535), timeout)
    assert source[0] == LOCAL
    return parse_sip(packet)


def sip_request(method: str, *, peer_port: int, app_port: int, media_port: int) -> bytes:
    headers = {
        "Via": f"SIP/2.0/UDP {LOCAL}:{peer_port};branch=z9hG4bKgpu-test",
        "From": f"<sip:synthetic@{LOCAL}>;tag=gpu-test",
        "To": f"<sip:agent@{LOCAL}:{app_port}>",
        "Call-ID": "voic-m6-gpu-test",
        "CSeq": f"{1 if method in ('INVITE', 'ACK') else 2} {method}",
    }
    body = b""
    if method == "INVITE":
        headers["Content-Type"] = "application/sdp"
        body = (
            f"v=0\r\no=- 1 1 IN IP4 {LOCAL}\r\ns=gpu-test\r\n"
            f"c=IN IP4 {LOCAL}\r\nt=0 0\r\n"
            f"m=audio {media_port} RTP/AVP 0 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
        ).encode()
    return request_bytes(method, f"sip:agent@{LOCAL}:{app_port}", headers, body)


def speech_frames(path: Path) -> list[bytes]:
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        pcm = wav.readframes(wav.getnframes())
        rate = wav.getframerate()
    pcm8k, _ = audioop.ratecv(pcm, 2, 1, rate, 8000, None)
    pcm8k += b"\0" * ((320 - len(pcm8k) % 320) % 320)
    frames = [audioop.lin2ulaw(pcm8k[offset:offset + 320], 2)
              for offset in range(0, len(pcm8k), 320)]
    assert frames
    return frames + [b"\xff" * 160] * 55


async def send_turn(sock: socket.socket, app_port: int, frames: list[bytes], sequence: int) -> int:
    loop = asyncio.get_running_loop()
    for payload in frames:
        header = struct.pack("!BBHII", 0x80, 0, sequence & 0xFFFF,
                             (sequence * 160) & 0xFFFFFFFF, 0x01020304)
        await loop.sock_sendto(sock, header + payload, (LOCAL, app_port))
        sequence += 1
        await asyncio.sleep(.02)
    return sequence


class FixedTask:
    def __init__(self) -> None:
        self.history_lengths: list[int] = []

    async def process(self, text, context, cancel, *, history=()):
        assert text.strip()
        self.history_lengths.append(len(history))
        return TaskResult("안녕하세요. 다음 질문도 말씀해 주세요.")


class CountedTTS:
    def __init__(self) -> None:
        self.adapter = MeloTTSAdapter(1.25)
        self.completed = 0
        self.completed_at: list[float] = []

    async def synthesize(self, text, context, cancel):
        async for chunk in self.adapter.synthesize(text, context, cancel):
            yield chunk
        self.completed += 1
        self.completed_at.append(time.monotonic())


class Events:
    def __init__(self) -> None:
        self.items = []

    async def publish(self, item) -> None:
        self.items.append(item)

    def statuses(self, kind) -> list:
        return [item.payload.status for item in self.items if isinstance(item.payload, kind)]


async def until(predicate, timeout: float = 150) -> None:
    async def wait() -> None:
        while not predicate():
            await asyncio.sleep(.05)
    await asyncio.wait_for(wait(), timeout)


async def monitor(stop: asyncio.Event, values: dict[str, int]) -> None:
    while not stop.is_set():
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            if key in {"MemAvailable", "SwapTotal", "SwapFree"}:
                mem[key] = int(rest.split()[0])
        rss = next(int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines()
                   if line.startswith("VmRSS:"))
        values["minimumAvailableKiB"] = min(values["minimumAvailableKiB"], mem["MemAvailable"])
        values["maximumSwapUsedKiB"] = max(values["maximumSwapUsedKiB"],
                                            mem["SwapTotal"] - mem["SwapFree"])
        values["maximumAppRssKiB"] = max(values["maximumAppRssKiB"], rss)
        await asyncio.sleep(.25)


async def drain_rtp(sock: socket.socket, stop: asyncio.Event, counters: dict[str, int]) -> None:
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        try:
            packet, source = await asyncio.wait_for(loop.sock_recvfrom(sock, 2048), .25)
        except asyncio.TimeoutError:
            continue
        if source[0] == LOCAL and len(packet) > 12 and packet[0] >> 6 == 2 and packet[1] & 0x7F == 0:
            counters["outputRtpPackets"] += 1


async def main() -> None:
    """Given synthetic Korean audio, when real GPU models handle two SIP turns, then media, context and lease recover."""
    peer_sip, peer_rtp = udp_socket(), udp_socket()
    app_ports = [udp_socket() for _ in range(2)]
    app_sip = app_ports[0].getsockname()[1]
    app_rtp = app_ports[1].getsockname()[1]
    for sock in app_ports:
        sock.close()
    gate = SingleSessionGate()
    task, tts, events = FixedTask(), CountedTTS(), Events()
    runner = VoiceOrchestrator(FasterWhisperSTT("small"), task, tts, gate,
                               StepTimeouts(120, 60, 120))
    service = InboundSIPService(
        peer_host=LOCAL, peer_port=peer_sip.getsockname()[1], local_host=LOCAL,
        sip_port=app_sip, rtp_port=app_rtp, user_id="agent", runner=runner,
        gate=gate, boundary=TurnBoundary(400, 900, 8000), events=events,
    )
    stop = asyncio.Event()
    values = {"minimumAvailableKiB": 10**15, "maximumSwapUsedKiB": 0,
              "maximumAppRssKiB": 0}
    counters = {"outputRtpPackets": 0}
    monitor_task = asyncio.create_task(monitor(stop, values))
    drain_task = asyncio.create_task(drain_rtp(peer_rtp, stop, counters))
    start = time.monotonic()
    try:
        await service.start()
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(peer_sip, sip_request(
            "INVITE", peer_port=peer_sip.getsockname()[1], app_port=app_sip,
            media_port=peer_rtp.getsockname()[1],
        ), (LOCAL, app_sip))
        assert (await receive_sip(peer_sip)).status == 100
        answer = await receive_sip(peer_sip)
        assert answer.status == 200
        assert re.search(rb"^m=audio \d+ RTP/AVP 0", answer.body, re.MULTILINE)
        await loop.sock_sendto(peer_sip, sip_request(
            "ACK", peer_port=peer_sip.getsockname()[1], app_port=app_sip,
            media_port=peer_rtp.getsockname()[1],
        ), (LOCAL, app_sip))
        await until(lambda: CallStatus.ACTIVE in events.statuses(CallState), 5)
        sequence = 0
        frames = speech_frames(Path(__file__).with_name("synthetic.wav"))
        turn_times = []
        for index in range(2):
            sequence = await send_turn(peer_rtp, app_rtp, frames, sequence)
            input_ended = time.monotonic()
            await until(lambda: tts.completed >= index + 1)
            turn_times.append(round(tts.completed_at[index] - input_ended, 3))
            await asyncio.sleep(.1)
            assert gate.active_session_id is not None
            assert SessionStatus.FAILED not in events.statuses(SessionState)
        assert task.history_lengths == [0, 1]
        assert counters["outputRtpPackets"] > 0
        await loop.sock_sendto(peer_sip, sip_request(
            "BYE", peer_port=peer_sip.getsockname()[1], app_port=app_sip,
            media_port=peer_rtp.getsockname()[1],
        ), (LOCAL, app_sip))
        assert (await receive_sip(peer_sip)).status == 200
        await until(lambda: gate.active_session_id is None, 5)
        assert events.statuses(CallState)[-1] is CallStatus.ENDED
        print(json.dumps({
            "twoTurns": len(task.history_lengths), "historyLengths": task.history_lengths,
            "outputRtpPackets": counters["outputRtpPackets"],
            "turnSecondsAfterInput": turn_times,
            "totalSeconds": round(time.monotonic() - start, 3),
            **values,
        }))
    finally:
        await service.close()
        stop.set()
        await asyncio.gather(monitor_task, drain_task)
        peer_sip.close()
        peer_rtp.close()


if __name__ == "__main__":
    asyncio.run(main())
