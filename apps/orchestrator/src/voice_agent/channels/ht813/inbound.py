"""Trusted-peer HT813 FXO inbound SIP UAS (VOIC-FEAT-001 M6-S1-T5)."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Awaitable
from uuid import uuid4

from voice_agent.channels.ht813.conversation import PhoneMediaConversation, SequencedCallEvents
from voice_agent.channels.ht813.rtp import RTPMedia
from voice_agent.channels.ht813.sip import SIPMessage, parse_sip, request_bytes
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SessionBusy, SessionLease, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, DtmfEvent
from voice_agent.contracts.ports import EventSink, PhoneSessionRunner, RetentionUnavailable
from voice_agent.contracts.session import (
    CallState, CallStatus, Channel, EventEnvelope, SessionContext,
)
from voice_agent.infrastructure.retention import EncryptedRetention


_CALLER_HEADERS = {
    "from": "from",
    "p-asserted-identity": "p-asserted-identity",
    "p-preferred-identity": "p-preferred-identity",
    "disabled": None,
}


def extract_caller_number(headers: dict[str, str], *, source: str,
                          account_id: str) -> str | None:
    """Read only the configured identity header; never infer a number from SIP routing."""
    name = _CALLER_HEADERS[source]
    value = headers.get(name, "") if name is not None else ""
    match = re.search(r"(?:sip:|tel:)(\+?[0-9]{7,15})(?=@|[;>])", value, re.IGNORECASE)
    number = match.group(1) if match else None
    return number if number != account_id else None


class _NullEvents:
    async def publish(self, event: EventEnvelope) -> None:
        pass


class _InboundMedia:
    def __init__(self, media: RTPMedia) -> None:
        self.media = media

    async def receive_audio(self) -> AudioChunk:
        return await self.media.audio.get()

    async def receive_dtmf(self) -> DtmfEvent:
        return await self.media.dtmf.get()

    async def send_audio(self, chunk: AudioChunk) -> None:
        await self.media.send_audio(chunk)


@dataclass(slots=True)
class _Dialog:
    context: SessionContext
    invite: SIPMessage
    lease: SessionLease
    media: RTPMedia
    sink: SequencedCallEvents
    to_header: str
    tag: str
    cancel: CancellationToken
    answer: bytes | None = None
    state: str = "early"
    accept_task: asyncio.Task[None] | None = None
    conversation_task: asyncio.Task[None] | None = None
    media_watch: asyncio.Task[None] | None = None
    normal_end: bool = False
    ack: asyncio.Event | None = None

    @property
    def call_id(self) -> str:
        return self.invite.headers["call-id"]


class InboundSIPService:
    """One directly peered PSTN-to-VoIP call, independent of outbound allowlist."""

    def __init__(
        self, *, peer_host: str, peer_port: int, local_host: str,
        sip_port: int, rtp_port: int, user_id: str,
        runner: PhoneSessionRunner, gate: SingleSessionGate, boundary: TurnBoundary,
        events: EventSink | None = None,
        retention: EncryptedRetention | None = None,
        caller_id_header: str = "from",
        media_factory: Callable[..., RTPMedia] = RTPMedia,
        send_packet: Callable[[bytes, tuple[str, int]], Awaitable[None]] | None = None,
    ) -> None:
        for address in (peer_host, local_host):
            parsed = ipaddress.ip_address(address)
            if not isinstance(parsed, ipaddress.IPv4Address) or parsed.is_unspecified:
                raise ValueError("inbound SIP requires concrete IPv4 peers")
        if any(not 1 <= value <= 65535 for value in (peer_port, sip_port, rtp_port)):
            raise ValueError("inbound SIP/RTP port is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user_id):
            raise ValueError("invalid inbound SIP user ID")
        if caller_id_header not in _CALLER_HEADERS:
            raise ValueError("invalid caller ID header")
        self.peer = (peer_host, peer_port)
        self.local_host, self.sip_port, self.rtp_port = local_host, sip_port, rtp_port
        self.user_id, self.runner, self.gate, self.boundary = user_id, runner, gate, boundary
        self.events = events or _NullEvents()
        self.retention = retention
        self.caller_id_header = caller_id_header
        self._media_factory, self._send_packet = media_factory, send_packet
        self._socket: socket.socket | None = None
        self._reader: asyncio.Task[None] | None = None
        self._packets: set[asyncio.Task[None]] = set()
        self._dialog: _Dialog | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._reader is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.bind((self.local_host, self.sip_port))
        except Exception:
            sock.close()
            raise
        self._socket = sock
        self._reader = asyncio.create_task(self._receive())

    async def _send(self, data: bytes) -> None:
        if self._send_packet is not None:
            await self._send_packet(data, self.peer)
        elif self._socket is not None:
            await asyncio.get_running_loop().sock_sendto(self._socket, data, self.peer)
        else:
            raise RuntimeError("inbound SIP listener is not started")

    async def _receive(self) -> None:
        assert self._socket is not None
        try:
            while True:
                packet, source = await asyncio.get_running_loop().sock_recvfrom(
                    self._socket, 65535,
                )
                task = asyncio.create_task(self._dispatch_packet(packet, source))
                self._packets.add(task)
                task.add_done_callback(self._packets.discard)
        except asyncio.CancelledError:
            raise

    async def _dispatch_packet(self, packet: bytes, source: tuple[str, int]) -> None:
        try:
            await self.handle_packet(packet, source)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._dialog is not None:
                await self._terminate(self._dialog, normal=False)

    def _response(self, invite: SIPMessage, code: int, reason: str,
                  to_header: str | None = None, body: bytes = b"") -> bytes:
        headers = invite.headers
        fields = {
            "Via": headers.get("via", ""),
            "From": headers.get("from", ""),
            "To": to_header or headers.get("to", ""),
            "Call-ID": headers.get("call-id", ""),
            "CSeq": headers.get("cseq", ""),
        }
        if 200 <= code < 300 and headers.get("cseq", "").endswith(" INVITE"):
            fields["Contact"] = f"<sip:{self.user_id}@{self.local_host}:{self.sip_port}>"
        lines = [f"SIP/2.0 {code} {reason}"]
        lines += [f"{key}: {value}" for key, value in fields.items() if value]
        if body:
            lines.append("Content-Type: application/sdp")
        lines.append(f"Content-Length: {len(body)}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode() + body

    def _parse_offer(self, invite: SIPMessage) -> tuple[int, int, int | None]:
        if invite.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/sdp":
            raise ValueError("missing SDP offer")
        body = invite.body.decode("ascii")
        host = re.search(r"^c=IN IP4 ([0-9.]+)\r?$", body, re.MULTILINE)
        audio = re.search(r"^m=audio (\d+) RTP/AVP ([\d ]+)\r?$", body, re.MULTILINE)
        if not host or not audio or host.group(1) != self.peer[0]:
            raise ValueError("untrusted SDP destination")
        port = int(audio.group(1))
        if not 1 <= port <= 65535:
            raise ValueError("invalid media port")
        offered = [int(number) for number in audio.group(2).split()]
        codec = next((number for number in offered if number in (0, 8)), None)
        if codec is None:
            raise ValueError("unsupported G.711 offer")
        dtmf = re.search(r"^a=rtpmap:(\d+) telephone-event/8000\r?$", body,
                         re.MULTILINE | re.IGNORECASE)
        telephone = int(dtmf.group(1)) if dtmf and int(dtmf.group(1)) in offered else None
        return port, codec, telephone

    def _answer_sdp(self, media: RTPMedia, codec: int,
                    telephone: int | None) -> bytes:
        payloads = str(codec) + (f" {telephone}" if telephone is not None else "")
        codec_name = "PCMU" if codec == 0 else "PCMA"
        parts = [
            "v=0", f"o=- 1 1 IN IP4 {self.local_host}", "s=voice-agent",
            f"c=IN IP4 {self.local_host}", "t=0 0",
            f"m=audio {media.local_port} RTP/AVP {payloads}",
            f"a=rtpmap:{codec} {codec_name}/8000",
        ]
        if telephone is not None:
            parts += [f"a=rtpmap:{telephone} telephone-event/8000",
                      f"a=fmtp:{telephone} 0-15"]
        return ("\r\n".join(parts) + "\r\n").encode()

    async def handle_packet(self, raw: bytes, source: tuple[str, int]) -> None:
        """Dispatch one datagram. Untrusted peers are ignored before parsing or models."""
        if source != self.peer:
            return
        try:
            message = parse_sip(raw)
        except (ValueError, UnicodeError, IndexError):
            await self._send(b"SIP/2.0 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        method = message.start.split(" ", 1)[0]
        if message.status:
            return
        if method == "INVITE":
            await self._invite(message)
        elif method == "ACK":
            await self._ack(message)
        elif method == "CANCEL":
            await self._cancel(message)
        elif method == "BYE":
            await self._bye(message)
        else:
            await self._send(self._response(message, 405, "Method Not Allowed"))

    async def _invite(self, invite: SIPMessage) -> None:
        headers = invite.headers
        if (not invite.start.endswith(" SIP/2.0")
                or not all(headers.get(key) for key in ("via", "from", "to", "call-id", "cseq"))
                or not re.fullmatch(r"[1-9]\d* INVITE", headers["cseq"])
                or len(headers["call-id"]) > 128):
            await self._send(self._response(invite, 400, "Bad Request"))
            return
        try:
            media_port, codec, telephone = self._parse_offer(invite)
        except (ValueError, UnicodeError):
            await self._send(self._response(invite, 488, "Not Acceptable Here"))
            return
        async with self._lock:
            if self._dialog is not None:
                dialog = self._dialog
                if dialog.call_id == headers["call-id"]:
                    await self._send(dialog.answer or self._response(invite, 100, "Trying"))
                else:
                    await self._send(self._response(invite, 486, "Busy Here"))
                return
            context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
            try:
                lease = await self.gate.acquire(context.session_id)
            except SessionBusy:
                await self._send(self._response(invite, 486, "Busy Here"))
                return
            try:
                media = self._media_factory(context.session_id, local_host=self.local_host,
                                            local_port=self.rtp_port)
                media.start(self.peer[0], media_port, codec, telephone)
            except Exception:
                await lease.release()
                await self._send(self._response(invite, 503, "Service Unavailable"))
                return
            if self.retention is not None:
                try:
                    await self.retention.record_call_start(
                        context, extract_caller_number(
                            headers, source=self.caller_id_header, account_id=self.user_id,
                        ),
                    )
                except RetentionUnavailable:
                    await media.close()
                    await lease.release()
                    await self._send(self._response(invite, 503, "Service Unavailable"))
                    return
            tag = secrets.token_hex(8)
            to_header = headers["to"] + f";tag={tag}"
            dialog = _Dialog(context, invite, lease, media,
                             SequencedCallEvents(context.session_id, self.events),
                             to_header, tag, CancellationToken(), ack=asyncio.Event())
            self._dialog = dialog
            await self._send(self._response(invite, 100, "Trying"))
            dialog.accept_task = asyncio.create_task(self._accept(dialog, codec, telephone))

    async def _accept(self, dialog: _Dialog, codec: int,
                      telephone: int | None) -> None:
        try:
            await asyncio.sleep(.05)  # allow an early CANCEL before answering
            async with self._lock:
                if self._dialog is not dialog or dialog.state != "early":
                    return
                sdp = self._answer_sdp(dialog.media, codec, telephone)
                dialog.answer = self._response(dialog.invite, 200, "OK", dialog.to_header, sdp)
                dialog.state = "answered"
                await self._send(dialog.answer)
            deadline = asyncio.get_running_loop().time() + 5.0
            interval = .5
            while not dialog.ack.is_set():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    await self._terminate(dialog, normal=False)
                    break
                try:
                    await asyncio.wait_for(dialog.ack.wait(), min(interval, remaining))
                except TimeoutError:
                    async with self._lock:
                        if self._dialog is not dialog or dialog.state != "answered":
                            return
                        await self._send(dialog.answer)
                    interval = min(interval * 2, 2.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._terminate(dialog, normal=False)

    async def _ack(self, message: SIPMessage) -> None:
        async with self._lock:
            dialog = self._dialog
            if (dialog is None or message.headers.get("call-id") != dialog.call_id
                    or dialog.state != "answered"):
                return
            dialog.state = "active"
            dialog.ack.set()
            await dialog.sink.publish(EventEnvelope(
                dialog.context.session_id, 0, CallState(CallStatus.ACTIVE),
            ))
            bridge = PhoneMediaConversation(_InboundMedia(dialog.media), self.runner,
                                            self.boundary)
            dialog.conversation_task = asyncio.create_task(self._conversation(dialog, bridge))
            dialog.media_watch = asyncio.create_task(self._watch_media(dialog))

    async def _conversation(self, dialog: _Dialog, bridge: PhoneMediaConversation) -> None:
        try:
            await bridge.run(dialog.context, dialog.sink, dialog.cancel,
                             dialog.lease, lambda: dialog.normal_end)
        except asyncio.CancelledError:
            raise
        except Exception:
            dialog.cancel.cancel()
        finally:
            if self._dialog is dialog and not dialog.normal_end:
                try:
                    await self._local_bye(dialog)
                finally:
                    await self._terminate(dialog, normal=False)

    async def _watch_media(self, dialog: _Dialog) -> None:
        try:
            await dialog.media.failed.wait()
            if self._dialog is dialog:
                try:
                    await self._local_bye(dialog)
                finally:
                    await self._terminate(dialog, normal=False)
        except asyncio.CancelledError:
            raise

    async def _local_bye(self, dialog: _Dialog) -> None:
        target = f"sip:{self.user_id}@{self.peer[0]}:{self.peer[1]}"
        headers = {
            "Via": f"SIP/2.0/UDP {self.local_host}:{self.sip_port};branch=z9hG4bK{secrets.token_hex(8)}",
            "From": dialog.to_header,
            "To": dialog.invite.headers["from"],
            "Call-ID": dialog.call_id,
            "CSeq": "1 BYE",
            "Contact": f"<sip:{self.user_id}@{self.local_host}:{self.sip_port}>",
        }
        await self._send(request_bytes("BYE", target, headers))

    async def _cancel(self, message: SIPMessage) -> None:
        async with self._lock:
            dialog = self._dialog
            if dialog is None or dialog.call_id != message.headers.get("call-id"):
                await self._send(self._response(message, 481, "Call Does Not Exist"))
                return
            await self._send(self._response(message, 200, "OK", dialog.to_header))
            if dialog.state == "early":
                await self._send(self._response(dialog.invite, 487, "Request Terminated",
                                                dialog.to_header))
                asyncio.create_task(self._terminate(dialog, normal=True))

    async def _bye(self, message: SIPMessage) -> None:
        async with self._lock:
            dialog = self._dialog
            if dialog is None or dialog.call_id != message.headers.get("call-id"):
                await self._send(self._response(message, 481, "Call Does Not Exist"))
                return
            await self._send(self._response(message, 200, "OK", dialog.to_header))
            asyncio.create_task(self._terminate(dialog, normal=True))

    async def _terminate(self, dialog: _Dialog, *, normal: bool) -> None:
        async with self._lock:
            if self._dialog is not dialog:
                return
            self._dialog = None
            dialog.normal_end = normal
            dialog.cancel.cancel()
        if dialog.accept_task is not None and dialog.accept_task is not asyncio.current_task():
            dialog.accept_task.cancel()
            await asyncio.gather(dialog.accept_task, return_exceptions=True)
        if dialog.conversation_task is not None and dialog.conversation_task is not asyncio.current_task():
            try:
                await asyncio.wait_for(dialog.conversation_task, 3.0)
            except TimeoutError:
                dialog.conversation_task.cancel()
                await asyncio.gather(dialog.conversation_task, return_exceptions=True)
        if dialog.media_watch is not None and dialog.media_watch is not asyncio.current_task():
            dialog.media_watch.cancel()
            await asyncio.gather(dialog.media_watch, return_exceptions=True)
        try:
            await dialog.media.close()
            await dialog.sink.publish(EventEnvelope(
                dialog.context.session_id, 0,
                CallState(CallStatus.ENDED if normal else CallStatus.FAILED),
            ))
        finally:
            try:
                if self.retention is not None:
                    await self.retention.record_call_end(
                        dialog.context, "ended" if normal else "failed",
                    )
            except RetentionUnavailable:
                pass
            finally:
                await dialog.lease.release()

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)
            self._reader = None
        for task in tuple(self._packets):
            task.cancel()
        await asyncio.gather(*self._packets, return_exceptions=True)
        try:
            dialog = self._dialog
            if dialog is not None:
                try:
                    if dialog.state == "active":
                        await self._local_bye(dialog)
                except Exception:
                    # Shutdown is best effort: a failed send must not retain resources.
                    pass
                finally:
                    await self._terminate(dialog, normal=False)
        finally:
            if self._socket is not None:
                self._socket.close()
                self._socket = None
