"""Minimal outbound SIP/UDP client with Digest challenge handling."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import socket
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SIPMessage:
    start: str
    headers: dict[str, str]
    body: bytes

    @property
    def status(self) -> int:
        return int(self.start.split(" ", 2)[1]) if self.start.startswith("SIP/2.0 ") else 0


def parse_sip(raw: bytes) -> SIPMessage:
    head, marker, body = raw.partition(b"\r\n\r\n")
    if not marker:
        raise ValueError("invalid SIP message")
    lines = head.decode("utf-8", "replace").split("\r\n")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", len(body)))
    return SIPMessage(lines[0], headers, body[:length])


def digest_header(challenge: str, *, username: str, password: str,
                  method: str, uri: str) -> str:
    """RFC 3261 MD5 Digest, qop=auth only; caller never logs credentials."""
    # Regex triples are normalized so quoted and token values both work.
    parameters = {key: quoted or token for key, quoted, token in
                  re.findall(r'([\w-]+)=(?:"([^"]*)"|([^,\s]+))', challenge)}
    realm, nonce = parameters["realm"], parameters["nonce"]
    algorithm = parameters.get("algorithm", "MD5").upper()
    if algorithm != "MD5":
        raise ValueError("unsupported SIP Digest algorithm")
    qop = parameters.get("qop", "")
    if qop and "auth" not in qop.split(","):
        raise ValueError("unsupported SIP Digest qop")
    md5 = lambda value: hashlib.md5(value.encode("utf-8")).hexdigest()
    ha1 = md5(f"{username}:{realm}:{password}")
    ha2 = md5(f"{method}:{uri}")
    fields = [f'username="{username}"', f'realm="{realm}"',
              f'nonce="{nonce}"', f'uri="{uri}"']
    if qop:
        nc, cnonce = "00000001", secrets.token_hex(8)
        response = md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
        fields += ["qop=auth", f"nc={nc}", f'cnonce="{cnonce}"']
    else:
        response = md5(f"{ha1}:{nonce}:{ha2}")
    fields.append(f'response="{response}"')
    return "Digest " + ", ".join(fields)


class UDPSIPPeer:
    def __init__(self, target_host: str, target_port: int, local_host: str,
                 local_port: int) -> None:
        self.target = (target_host, target_port)
        self.local_host = local_host
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind((local_host, local_port))
        self.local_port = self._socket.getsockname()[1]

    async def send(self, message: bytes) -> None:
        await asyncio.get_running_loop().sock_sendto(self._socket, message, self.target)

    async def receive(self, timeout_s: float) -> SIPMessage:
        while True:
            data, source = await asyncio.wait_for(
                asyncio.get_running_loop().sock_recvfrom(self._socket, 65535), timeout_s,
            )
            if source == self.target:
                return parse_sip(data)

    async def close(self) -> None:
        self._socket.close()


def request_bytes(method: str, uri: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    lines = [f"{method} {uri} SIP/2.0"]
    lines.extend(f"{name}: {value}" for name, value in headers.items())
    lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body
