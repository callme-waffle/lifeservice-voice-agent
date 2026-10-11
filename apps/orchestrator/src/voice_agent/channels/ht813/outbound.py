"""Outbound-only HT813 FXO SIP call control (VOIC-FEAT-001 M5-S5)."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets
from collections.abc import Callable

from voice_agent.channels.ht813.rtp import RTPMedia
from voice_agent.channels.ht813.sip import UDPSIPPeer, SIPMessage, digest_header, request_bytes
from voice_agent.contracts.flow import OperationCancelled
from voice_agent.contracts.media import AudioChunk, DtmfEvent
from voice_agent.contracts.ports import Cancellation, EventSink
from voice_agent.contracts.session import (
    AllowedNumberPolicy, CallState, CallStatus, EventEnvelope, OutboundCallRequest,
)


class HT813Outbound:
    def __init__(
        self, *, host: str, port: int, local_host: str, user_id: str,
        policy: AllowedNumberPolicy, password: str | None = None,
        local_sip_port: int = 5060, local_rtp_port: int = 4000,
        peer_factory: Callable[..., object] = UDPSIPPeer,
        media_factory: Callable[..., object] = RTPMedia,
    ) -> None:
        if not 1 <= port <= 65535 or not 1 <= local_sip_port <= 65535 or not 1 <= local_rtp_port <= 65535:
            raise ValueError("HT813 SIP address and local address are required")
        for address in (host, local_host):
            parsed = ipaddress.ip_address(address)
            if not isinstance(parsed, ipaddress.IPv4Address) or parsed.is_unspecified:
                raise ValueError("SIP address must be a concrete IPv4 address")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user_id):
            raise ValueError("invalid SIP user ID")
        self.host, self.port, self.local_host = host, port, local_host
        self.local_sip_port, self.local_rtp_port = local_sip_port, local_rtp_port
        self.user_id, self.password, self.policy = user_id, password, policy
        self._peer_factory, self._media_factory = peer_factory, media_factory
        self._lock = asyncio.Lock()
        self._media: RTPMedia | None = None

    async def send_audio(self, chunk: AudioChunk) -> None:
        if self._media is None:
            raise RuntimeError("call is not active")
        await self._media.send_audio(chunk)

    async def receive_audio(self) -> AudioChunk:
        if self._media is None:
            raise RuntimeError("call is not active")
        return await self._media.audio.get()

    async def send_dtmf(self, event: DtmfEvent) -> None:
        if self._media is None:
            raise RuntimeError("call is not active")
        await self._media.send_dtmf(event)

    async def receive_dtmf(self) -> DtmfEvent:
        if self._media is None:
            raise RuntimeError("call is not active")
        return await self._media.dtmf.get()

    async def dial(self, request: OutboundCallRequest, sink: EventSink, cancel: Cancellation) -> None:
        request.authorize(self.policy)  # No socket or SIP packet before authorization.
        cancel.raise_if_cancelled()
        if self._lock.locked():
            await sink.publish(EventEnvelope(request.session_id, 0, CallState(CallStatus.BUSY)))
            return
        async with self._lock:
            peer = self._peer_factory(self.host, self.port, self.local_host,
                                      self.local_sip_port)
            media = self._media_factory(request.session_id, local_host=self.local_host,
                                        local_port=self.local_rtp_port)
            sequence = 0
            active = False
            invite_pending = False
            uri = f"sip:{request.number.value}@{self.host}:{self.port}"
            call_id = secrets.token_hex(16) + "@" + self.local_host
            from_tag = secrets.token_hex(8)
            branch = "z9hG4bK" + secrets.token_hex(8)
            cseq = 1
            to_header = f"<sip:{request.number.value}@{self.host}>"
            authorization: tuple[str, str] | None = None

            async def emit(status: CallStatus, reason: str | None = None) -> None:
                nonlocal sequence
                await sink.publish(EventEnvelope(request.session_id, sequence,
                                                 CallState(status, reason)))
                sequence += 1

            def headers(method: str, branch_value: str, number: int) -> dict[str, str]:
                result = {
                    "Via": f"SIP/2.0/UDP {self.local_host}:{peer.local_port};branch={branch_value};rport",
                    "Max-Forwards": "70",
                    "From": f"<sip:{self.user_id}@{self.local_host}>;tag={from_tag}",
                    "To": to_header,
                    "Call-ID": call_id,
                    "CSeq": f"{number} {method}",
                    "Contact": f"<sip:{self.user_id}@{self.local_host}:{peer.local_port}>",
                }
                if authorization:
                    result[authorization[0]] = authorization[1]
                return result

            async def send_invite() -> None:
                nonlocal invite_pending
                offer = (
                    "v=0\r\n"
                    f"o=- 1 1 IN IP4 {self.local_host}\r\n"
                    "s=voice-agent\r\n"
                    f"c=IN IP4 {self.local_host}\r\n"
                    "t=0 0\r\n"
                    f"m=audio {media.local_port} RTP/AVP 0 8 101\r\n"
                    "a=rtpmap:0 PCMU/8000\r\n"
                    "a=rtpmap:8 PCMA/8000\r\n"
                    "a=rtpmap:101 telephone-event/8000\r\n"
                    "a=fmtp:101 0-15\r\n"
                ).encode()
                h = headers("INVITE", branch, cseq)
                h["Content-Type"] = "application/sdp"
                await peer.send(request_bytes("INVITE", uri, h, offer))
                invite_pending = True

            async def send_control(method: str, response: SIPMessage | None = None) -> None:
                nonlocal cseq
                if response and response.headers.get("to"):
                    nonlocal to_header
                    to_header = response.headers["to"]
                if method == "BYE":
                    cseq += 1
                use_branch = branch if method in ("ACK", "CANCEL") and not active else (
                    "z9hG4bK" + secrets.token_hex(8))
                number = cseq
                await peer.send(request_bytes(method, uri, headers(method, use_branch, number)))

            async def cancel_pending_invite() -> None:
                """Complete the INVITE transaction after CANCEL, including a late 200."""
                nonlocal active, invite_pending
                await send_control("CANCEL")
                end_at = asyncio.get_running_loop().time() + 2.0
                while (remaining := end_at - asyncio.get_running_loop().time()) > 0:
                    try:
                        final = await peer.receive(remaining)
                    except TimeoutError:
                        break
                    if (final.headers.get("call-id") != call_id
                            or not final.headers.get("cseq", "").endswith(" INVITE")
                            or final.status < 200):
                        continue
                    invite_pending = False
                    if final.status == 200:
                        active = True
                        await send_control("ACK", final)
                        await send_control("BYE")
                        active = False
                    else:
                        await send_control("ACK", final)
                    break

            def media_answer(response: SIPMessage) -> tuple[str, int, int, int | None]:
                body = response.body.decode("utf-8", "replace")
                host = re.search(r"^c=IN IP4 ([0-9.]+)\r?$", body, re.MULTILINE)
                audio = re.search(r"^m=audio (\d+) RTP/AVP ([\d ]+)\r?$", body, re.MULTILINE)
                if not host or not audio or host.group(1) != self.host:
                    raise ValueError("invalid or untrusted SDP audio destination")
                offered = [int(part) for part in audio.group(2).split()]
                codec = next((part for part in offered if part in (0, 8)), None)
                if codec is None:
                    raise ValueError("no supported G.711 codec in SDP")
                dtmf = re.search(r"^a=rtpmap:(\d+) telephone-event/8000\r?$", body,
                                 re.MULTILINE | re.IGNORECASE)
                telephone = int(dtmf.group(1)) if dtmf and int(dtmf.group(1)) in offered else None
                return host.group(1), int(audio.group(1)), codec, telephone

            await emit(CallStatus.DIALING)
            try:
                cancel.raise_if_cancelled()
                await send_invite()
                loop = asyncio.get_running_loop()
                deadline = loop.time() + request.timeout_s
                interval = .5
                challenged = False
                provisional = False
                while not active:
                    cancel.raise_if_cancelled()
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError("SIP INVITE timed out")
                    try:
                        response = await peer.receive(min(remaining, interval))
                    except TimeoutError:
                        if not provisional:
                            await send_invite()
                        interval = min(interval * 2, 4.0)
                        continue
                    if response.status == 0:
                        continue  # inbound calls are intentionally unsupported
                    if response.headers.get("call-id") != call_id:
                        continue
                    if 100 <= response.status < 200:
                        provisional = True
                        if response.status >= 180:
                            await emit(CallStatus.RINGING)
                        interval = min(remaining, .5)
                        continue
                    invite_pending = False
                    if response.status in (401, 407) and self.password and not challenged:
                        await send_control("ACK", response)
                        challenge = response.headers.get(
                            "www-authenticate" if response.status == 401 else "proxy-authenticate", "")
                        authorization = (
                            "Authorization" if response.status == 401 else "Proxy-Authorization",
                            digest_header(challenge, username=self.user_id,
                                          password=self.password, method="INVITE", uri=uri),
                        )
                        cseq += 1
                        branch = "z9hG4bK" + secrets.token_hex(8)
                        challenged = True
                        provisional = False
                        await send_invite()
                        continue
                    if response.status >= 300:
                        await send_control("ACK", response)
                        if response.status in (486, 600):
                            await emit(CallStatus.BUSY)
                        else:
                            await emit(CallStatus.FAILED, "SIP call rejected")
                        return
                    if response.status != 200:
                        continue
                    active = True
                    await send_control("ACK", response)
                    destination = media_answer(response)
                    media.start(*destination)
                    self._media = media
                    await emit(CallStatus.ACTIVE)

                while True:
                    sip_event = asyncio.create_task(peer.receive(.5))
                    cancelled = asyncio.create_task(cancel.wait())
                    failed = asyncio.create_task(media.failed.wait())
                    try:
                        done, _ = await asyncio.wait({sip_event, cancelled, failed},
                                                     return_when=asyncio.FIRST_COMPLETED)
                        if cancelled in done or failed in done:
                            break
                        try:
                            incoming = await sip_event
                        except TimeoutError:
                            continue
                        if incoming.start.startswith("BYE ") and incoming.headers.get("call-id") == call_id:
                            response_headers = {key.title(): incoming.headers[key] for key in
                                                ("via", "from", "to", "call-id", "cseq")
                                                if key in incoming.headers}
                            await peer.send(("SIP/2.0 200 OK\r\n" +
                                             "\r\n".join(f"{k}: {v}" for k, v in response_headers.items()) +
                                             "\r\nContent-Length: 0\r\n\r\n").encode())
                            active = False
                            break
                    finally:
                        for item in (sip_event, cancelled, failed):
                            if not item.done():
                                item.cancel()
                        await asyncio.gather(sip_event, cancelled, failed, return_exceptions=True)
                if active:
                    await send_control("BYE")
                await emit(CallStatus.ENDED if not media.failed.is_set() else CallStatus.FAILED)
            except (OperationCancelled, asyncio.CancelledError):
                if invite_pending:
                    await cancel_pending_invite()
                elif active:
                    await send_control("BYE")
                await emit(CallStatus.ENDED)
            except Exception:
                if invite_pending:
                    await cancel_pending_invite()
                elif active:
                    await send_control("BYE")
                await emit(CallStatus.FAILED, "call setup or media failed")
            finally:
                self._media = None
                await media.close()
                await peer.close()
