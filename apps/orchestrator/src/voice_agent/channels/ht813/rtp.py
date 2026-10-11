"""G.711 RTP media and RFC 4733 telephone events for HT813 outbound calls."""

from __future__ import annotations

import asyncio
import audioop
import secrets
import socket
import struct
from uuid import UUID

from voice_agent.contracts.media import AudioChunk, DtmfEvent, INTERNAL_AUDIO_FORMAT


class RTPMedia:
    def __init__(self, session_id: UUID, *, local_host: str = "0.0.0.0",
                 local_port: int = 0) -> None:
        self.session_id = session_id
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind((local_host, local_port))
        self.local_port = self._socket.getsockname()[1]
        self._peer: tuple[str, int] | None = None
        self._payload_type: int | None = None
        self._telephone_type: int | None = None
        self._sequence = secrets.randbits(16)
        self._timestamp = secrets.randbits(32)
        self._ssrc = secrets.randbits(32)
        self._next_audio = 0
        self._incoming_audio = 0
        self._send_rate_state = None
        self._receive_rate_state = None
        self._last_dtmf: tuple[int, int] | None = None
        self.audio: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=8)
        self.dtmf: asyncio.Queue[DtmfEvent] = asyncio.Queue(maxsize=8)
        self.failed = asyncio.Event()
        self._receiver: asyncio.Task[None] | None = None

    def start(self, host: str, port: int, payload_type: int, telephone_type: int | None) -> None:
        if not 1 <= port <= 65535 or payload_type not in (0, 8):
            raise ValueError("unsupported RTP destination or codec")
        self._peer = (host, port)
        self._payload_type = payload_type
        self._telephone_type = telephone_type
        self._receiver = asyncio.create_task(self._receive())

    def _header(self, payload_type: int, timestamp: int, marker: bool = False) -> bytes:
        header = struct.pack("!BBHII", 0x80, payload_type | (0x80 if marker else 0),
                             self._sequence, timestamp, self._ssrc)
        self._sequence = (self._sequence + 1) & 0xFFFF
        return header

    async def send_audio(self, chunk: AudioChunk) -> None:
        if (self._peer is None or chunk.session_id != self.session_id
                or chunk.sequence != self._next_audio or chunk.format != INTERNAL_AUDIO_FORMAT):
            raise ValueError("invalid outgoing RTP audio")
        self._next_audio += 1
        reduced, self._send_rate_state = audioop.ratecv(
            chunk.data, 2, 1, 16_000, 8_000, self._send_rate_state,
        )
        encoder = audioop.lin2ulaw if self._payload_type == 0 else audioop.lin2alaw
        loop = asyncio.get_running_loop()
        send_at = loop.time()
        for offset in range(0, len(reduced), 320):
            await asyncio.sleep(max(0.0, send_at - loop.time()))
            frame = reduced[offset:offset + 320]
            if len(frame) < 320:
                frame = frame.ljust(320, b"\0")
            payload = encoder(frame, 2)
            packet = self._header(self._payload_type, self._timestamp) + payload
            await loop.sock_sendto(self._socket, packet, self._peer)
            self._timestamp = (self._timestamp + 160) & 0xFFFFFFFF
            send_at += .02

    async def send_dtmf(self, event: DtmfEvent) -> None:
        if self._peer is None or event.session_id != self.session_id or self._telephone_type is None:
            raise ValueError("RTP telephone-event was not negotiated")
        number = "0123456789*#ABCD".index(event.digit)
        duration = event.duration_ms * 8
        loop = asyncio.get_running_loop()
        started = struct.pack("!BBH", number, 0x0A, 160)
        await loop.sock_sendto(
            self._socket, self._header(self._telephone_type, self._timestamp, True) + started,
            self._peer,
        )
        payload = struct.pack("!BBH", number, 0x8A, duration)
        for _ in range(3):
            packet = self._header(self._telephone_type, self._timestamp) + payload
            await loop.sock_sendto(self._socket, packet, self._peer)
        self._timestamp = (self._timestamp + duration) & 0xFFFFFFFF

    async def _receive(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            while True:
                packet, source = await asyncio.wait_for(
                    loop.sock_recvfrom(self._socket, 2048), timeout=30.0,
                )
                if source != self._peer or len(packet) < 12 or packet[0] >> 6 != 2:
                    continue
                payload_type = packet[1] & 0x7F
                csrc_count = packet[0] & 0x0F
                offset = 12 + 4 * csrc_count
                if packet[0] & 0x10:  # RTP extension
                    if len(packet) < offset + 4:
                        continue
                    offset += 4 + 4 * int.from_bytes(packet[offset + 2:offset + 4], "big")
                if len(packet) <= offset:
                    continue
                payload = packet[offset:]
                if payload_type == self._payload_type:
                    decoder = audioop.ulaw2lin if payload_type == 0 else audioop.alaw2lin
                    linear = decoder(payload, 2)
                    internal, self._receive_rate_state = audioop.ratecv(
                        linear, 2, 1, 8_000, 16_000, self._receive_rate_state,
                    )
                    await self.audio.put(AudioChunk(self.session_id, self._incoming_audio,
                                                    internal, INTERNAL_AUDIO_FORMAT))
                    self._incoming_audio += 1
                elif payload_type == self._telephone_type and len(payload) >= 4 and payload[1] & 0x80:
                    digit = payload[0]
                    event_key = (int.from_bytes(packet[4:8], "big"), digit)
                    if digit < 16 and event_key != self._last_dtmf:
                        duration = int.from_bytes(payload[2:4], "big") // 8
                        await self.dtmf.put(DtmfEvent(self.session_id,
                                                      "0123456789*#ABCD"[digit], duration))
                        self._last_dtmf = event_key
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failed.set()

    async def close(self) -> None:
        if self._receiver is not None:
            self._receiver.cancel()
            await asyncio.gather(self._receiver, return_exceptions=True)
        self._socket.close()
