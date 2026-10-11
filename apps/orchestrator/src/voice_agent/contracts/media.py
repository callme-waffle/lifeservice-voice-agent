"""Channel independent audio and DTMF values (VOIC-FEAT-001, M4-S2-T2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class AudioEncoding(StrEnum):
    PCM_S16LE = "pcm_s16le"
    PCMU = "pcmu"
    PCMA = "pcma"


@dataclass(frozen=True, slots=True)
class AudioFormat:
    sample_rate_hz: int
    channels: int
    encoding: AudioEncoding

    def __post_init__(self) -> None:
        if not isinstance(self.encoding, AudioEncoding):
            raise TypeError("audio encoding must be an AudioEncoding")
        if not 8_000 <= self.sample_rate_hz <= 48_000:
            raise ValueError("sample rate must be 8000..48000 Hz")
        if self.channels != 1:
            raise ValueError("voice audio must be mono")
        if self.encoding in (AudioEncoding.PCMU, AudioEncoding.PCMA):
            if self.sample_rate_hz != 8_000:
                raise ValueError("G.711 audio must be 8000 Hz")

    @property
    def bytes_per_sample(self) -> int:
        return 2 if self.encoding is AudioEncoding.PCM_S16LE else 1


INTERNAL_AUDIO_FORMAT = AudioFormat(16_000, 1, AudioEncoding.PCM_S16LE)
MAX_CHUNK_DURATION_MS = 1_000


@dataclass(frozen=True, slots=True)
class AudioChunk:
    session_id: UUID
    sequence: int
    data: bytes
    format: AudioFormat

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("audio sequence must be nonnegative")
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("audio chunk must contain immutable bytes")
        if len(self.data) % (self.format.channels * self.format.bytes_per_sample):
            raise ValueError("audio chunk must contain complete samples")
        if len(self.data) * 1_000 > (
            self.format.sample_rate_hz
            * self.format.channels
            * self.format.bytes_per_sample
            * MAX_CHUNK_DURATION_MS
        ):
            raise ValueError("audio chunk exceeds one second")

    @property
    def duration_ms(self) -> float:
        return (
            len(self.data)
            * 1_000
            / (self.format.sample_rate_hz * self.format.channels * self.format.bytes_per_sample)
        )


@dataclass(frozen=True, slots=True)
class DtmfEvent:
    session_id: UUID
    digit: str
    duration_ms: int

    def __post_init__(self) -> None:
        if len(self.digit) != 1 or self.digit not in "0123456789*#ABCD":
            raise ValueError("unsupported DTMF digit")
        if not 40 <= self.duration_ms <= 2_000:
            raise ValueError("DTMF duration must be 40..2000 ms")
