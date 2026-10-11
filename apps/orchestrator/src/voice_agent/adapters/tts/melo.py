"""MeloTTS adapter that normalizes 44.1 kHz WAV to internal PCM."""

from __future__ import annotations

import asyncio
import audioop
import wave
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.ports import Cancellation
from voice_agent.contracts.session import SessionContext


class MeloTTSAdapter:
    def __init__(self, speed: float = 1.25, model_factory: Callable[..., object] | None = None):
        if not 0.5 <= speed <= 2.0:
            raise ValueError("MeloTTS speed must be 0.5..2.0")
        self.speed = speed
        self._factory = model_factory

    def synthesize(
        self, text: str, context: SessionContext, cancel: Cancellation,
    ) -> AsyncIterator[AudioChunk]:
        async def result() -> AsyncIterator[AudioChunk]:
            if not text.strip():
                raise ValueError("TTS text is empty")
            cancel.raise_if_cancelled()

            def infer() -> bytes:
                if self._factory is None:
                    from melo.api import TTS
                    factory = TTS
                else:
                    factory = self._factory
                model = factory(language="KR", device="cuda:0")
                try:
                    speaker = model.hps.data.spk2id["KR"]
                    with TemporaryDirectory(prefix="voice-agent-tts-") as directory:
                        output = Path(directory) / "speech.wav"
                        model.tts_to_file(text, speaker, str(output), speed=self.speed)
                        with wave.open(str(output), "rb") as wav:
                            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                                raise ValueError("MeloTTS output must be mono PCM16")
                            source_rate = wav.getframerate()
                            if source_rate != 44_100:
                                raise ValueError("unexpected MeloTTS sample rate")
                            pcm = wav.readframes(wav.getnframes())
                    converted, _ = audioop.ratecv(pcm, 2, 1, source_rate, 16_000, None)
                    return converted
                finally:
                    del model

            pcm = await asyncio.to_thread(infer)
            cancel.raise_if_cancelled()
            if not pcm:
                raise ValueError("MeloTTS returned empty audio")
            bytes_per_chunk = 16_000 * 2
            for sequence, offset in enumerate(range(0, len(pcm), bytes_per_chunk)):
                cancel.raise_if_cancelled()
                yield AudioChunk(
                    context.session_id, sequence, pcm[offset:offset + bytes_per_chunk],
                    INTERNAL_AUDIO_FORMAT,
                )

        return result()
