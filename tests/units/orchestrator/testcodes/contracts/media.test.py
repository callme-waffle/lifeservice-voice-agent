"""VOIC-FEAT-001 M4-S2-T2 audio and DTMF contract tests."""

from uuid import UUID

import pytest

from voice_agent.contracts.media import (
    AudioChunk,
    AudioEncoding,
    AudioFormat,
    DtmfEvent,
    INTERNAL_AUDIO_FORMAT,
)

SESSION = UUID("00000000-0000-0000-0000-000000000001")


def test_voic_feat_001_pcm_chunk_has_explicit_duration() -> None:
    """Given 20 ms PCM, when built, then timing and sequence are preserved."""
    chunk = AudioChunk(SESSION, 0, b"\x00\x00" * 320, INTERNAL_AUDIO_FORMAT)

    assert chunk.duration_ms == 20
    assert chunk.sequence == 0


@pytest.mark.parametrize("data", [b"", b"\x00", b"\x00" * 16_001])
def test_voic_feat_001_pcm_rejects_empty_partial_or_oversize(data: bytes) -> None:
    """Given invalid PCM, when built, then malformed frames are rejected."""
    with pytest.raises(ValueError):
        AudioChunk(SESSION, 0, data, INTERNAL_AUDIO_FORMAT)


def test_voic_feat_001_g711_requires_telephone_rate() -> None:
    """Given G.711 input, when format is built, then only 8 kHz is accepted."""
    assert AudioFormat(8_000, 1, AudioEncoding.PCMU).bytes_per_sample == 1
    with pytest.raises(ValueError):
        AudioFormat(16_000, 1, AudioEncoding.PCMA)


def test_voic_feat_001_dtmf_rejects_non_digit_and_short_event() -> None:
    """Given DTMF input, when invalid, then it cannot cross channel contracts."""
    assert DtmfEvent(SESSION, "#", 100).digit == "#"
    with pytest.raises(ValueError):
        DtmfEvent(SESSION, "E", 100)
    with pytest.raises(ValueError):
        DtmfEvent(SESSION, "1", 10)
