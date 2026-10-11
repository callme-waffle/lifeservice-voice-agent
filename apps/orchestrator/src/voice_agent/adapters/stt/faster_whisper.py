"""Faster Whisper adapter for the 16 kHz PCM port (VOIC-FEAT-001 M5-S2)."""

from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import AsyncIterator, Callable

from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.ports import Cancellation
from voice_agent.contracts.session import SessionContext, Transcript


class FasterWhisperSTT:
    def __init__(self, model_name: str = "small", model_factory: Callable[..., object] | None = None):
        if model_name not in {"small", "medium"}:
            raise ValueError("only measured STT candidates are supported")
        self.model_name = model_name
        self._factory = model_factory

    def transcribe(
        self, audio: AsyncIterator[AudioChunk], context: SessionContext, cancel: Cancellation,
    ) -> AsyncIterator[Transcript]:
        async def result() -> AsyncIterator[Transcript]:
            pcm = bytearray()
            expected = 0
            async for chunk in audio:
                cancel.raise_if_cancelled()
                if (chunk.session_id != context.session_id or chunk.sequence != expected
                        or chunk.format != INTERNAL_AUDIO_FORMAT):
                    raise ValueError("invalid STT audio stream")
                pcm.extend(chunk.data)
                expected += 1
            if not pcm:
                raise ValueError("empty STT audio")
            cancel.raise_if_cancelled()

            def infer() -> str:
                if self._factory is None:
                    from faster_whisper import WhisperModel
                    factory = WhisperModel
                else:
                    factory = self._factory
                model = factory(self.model_name, device="cuda", compute_type="int8")
                try:
                    source = io.BytesIO()
                    with wave.open(source, "wb") as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16_000)
                        wav.writeframes(pcm)
                    source.seek(0)
                    segments, _ = model.transcribe(source, language="ko", beam_size=5)
                    return " ".join(segment.text.strip() for segment in segments).strip()
                finally:
                    del model

            text = await asyncio.to_thread(infer)
            cancel.raise_if_cancelled()
            if not text:
                raise ValueError("no speech was recognized")
            yield Transcript(text, True)

        return result()
