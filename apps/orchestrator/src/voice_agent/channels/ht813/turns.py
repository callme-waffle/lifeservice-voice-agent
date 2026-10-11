"""Bounded PCM speech turns for a continuous HT813 call (VOIC-FEAT-001 M6-S1-T4)."""

from __future__ import annotations

import audioop
from dataclasses import dataclass

from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT


@dataclass(frozen=True, slots=True)
class TurnBoundary:
    energy_threshold: int = 400
    silence_ms: int = 800
    max_utterance_ms: int = 15_000

    def __post_init__(self) -> None:
        if not 0 < self.energy_threshold <= 32_767:
            raise ValueError("energy threshold must be positive PCM amplitude")
        if not 100 <= self.silence_ms <= 5_000:
            raise ValueError("silence duration must be 100..5000 ms")
        if not self.silence_ms < self.max_utterance_ms <= 60_000:
            raise ValueError("maximum utterance must exceed silence and be <=60000 ms")


class SpeechTurnDetector:
    """Start on audible PCM; finish one bounded turn on silence or maximum length."""

    def __init__(self, boundary: TurnBoundary) -> None:
        self.boundary = boundary
        self.reset()

    def reset(self) -> None:
        self._chunks: list[AudioChunk] = []
        self._duration_ms = 0.0
        self._silence_ms = 0.0

    def feed(self, chunk: AudioChunk) -> tuple[AudioChunk, ...] | None:
        if chunk.format != INTERNAL_AUDIO_FORMAT:
            raise ValueError("speech detector requires internal PCM")
        audible = audioop.rms(chunk.data, 2) >= self.boundary.energy_threshold
        if not self._chunks:
            if not audible:
                return None
            self._silence_ms = 0.0
        elif audible:
            self._silence_ms = 0.0
        else:
            self._silence_ms += chunk.duration_ms
        self._chunks.append(chunk)
        self._duration_ms += chunk.duration_ms
        if (self._silence_ms >= self.boundary.silence_ms
                or self._duration_ms >= self.boundary.max_utterance_ms):
            result = tuple(self._chunks)
            self.reset()
            return result
        return None
