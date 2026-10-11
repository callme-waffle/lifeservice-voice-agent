"""VOIC-FEAT-001 M5-S5: fake RTP socket validates G.711 and DTMF packets."""

import asyncio
import struct
from uuid import uuid4

import pytest

from voice_agent.channels.ht813.rtp import RTPMedia
from voice_agent.contracts.media import AudioChunk, DtmfEvent, INTERNAL_AUDIO_FORMAT


@pytest.mark.asyncio
@pytest.mark.parametrize("codec", [0, 8])
async def test_voic_feat_001_m5_s5_rtp_g711_and_dtmf_packaging(monkeypatch, codec):
    """Given 20 ms PCM and DTMF, when sent, then G.711 and telephone events are framed."""
    media = RTPMedia(uuid4(), local_host="127.0.0.1")
    media._peer = ("127.0.0.1", 22000)
    media._payload_type = codec
    media._telephone_type = 101
    packets = []
    loop = asyncio.get_running_loop()

    async def capture(sock, packet, peer):
        packets.append((packet, peer))

    monkeypatch.setattr(loop, "sock_sendto", capture)
    try:
        await media.send_audio(AudioChunk(media.session_id, 0, b"\0\0" * 320,
                                          INTERNAL_AUDIO_FORMAT))
        await media.send_dtmf(DtmfEvent(media.session_id, "5", 100))
        assert len(packets) == 5
        assert packets[0][0][1] & 0x7F == codec
        assert len(packets[0][0]) == 12 + 160
        assert [packet[0][1] & 0x7F for packet in packets[1:]] == [101] * 4
        assert packets[1][0][12] == 5
        assert packets[-1][0][13] & 0x80
    finally:
        await media.close()


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s5_rtp_receive_audio_and_dtmf_once(monkeypatch):
    """Given fake PCMU and repeated DTMF end packets, when received, then PCM and one key emerge."""
    media = RTPMedia(uuid4(), local_host="127.0.0.1")
    media._peer = ("127.0.0.1", 22000)
    media._payload_type = 0
    media._telephone_type = 101
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def fake_receive(sock, size):
        return await queue.get()

    monkeypatch.setattr(loop, "sock_recvfrom", fake_receive)
    media._receiver = asyncio.create_task(media._receive())
    header = struct.pack("!BBHII", 0x80, 0, 1, 160, 42)
    key_header = struct.pack("!BBHII", 0x80, 101, 2, 320, 42)
    try:
        await queue.put((header + b"\xff" * 160, media._peer))
        key_packet = key_header + struct.pack("!BBH", 5, 0x8A, 800)
        await queue.put((key_packet, media._peer))
        await queue.put((key_packet, media._peer))
        audio = await asyncio.wait_for(media.audio.get(), 1)
        digit = await asyncio.wait_for(media.dtmf.get(), 1)
        assert audio.session_id == media.session_id
        assert audio.sequence == 0 and audio.format == INTERNAL_AUDIO_FORMAT
        assert 0 < len(audio.data) <= 640
        assert digit == DtmfEvent(media.session_id, "5", 100)
        await asyncio.sleep(0)
        assert media.dtmf.empty()
    finally:
        await media.close()
