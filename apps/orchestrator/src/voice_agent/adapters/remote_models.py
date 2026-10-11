"""HTTP model adapters; audio and text stay on the private model network."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from opentelemetry import propagate

from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.ports import Cancellation
from voice_agent.contracts.session import SessionContext, Transcript


class ModelEndpoint:
    def __init__(self, base_url: str, timeout_s: float):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    async def ready(self) -> bool:
        try:
            response = await self.client.get("/ready", timeout=2.0)
            return response.status_code == 200 and response.json().get("status") == "ready"
        except (httpx.HTTPError, ValueError):
            return False

    async def close(self) -> None:
        await self.client.aclose()


class RemoteSTT(ModelEndpoint):
    async def transcribe(self, audio: AsyncIterator[AudioChunk], context: SessionContext,
                         cancel: Cancellation) -> AsyncIterator[Transcript]:
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
        headers = {"content-type": "audio/L16"}
        propagate.inject(headers)
        response = await self.client.post("/infer", content=bytes(pcm), headers=headers)
        response.raise_for_status()
        text = response.json()["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty STT result")
        cancel.raise_if_cancelled()
        yield Transcript(text, True)


class RemoteTTS(ModelEndpoint):
    async def synthesize(self, text: str, context: SessionContext,
                         cancel: Cancellation) -> AsyncIterator[AudioChunk]:
        if not text.strip():
            raise ValueError("TTS text is empty")
        cancel.raise_if_cancelled()
        headers: dict[str, str] = {}
        propagate.inject(headers)
        response = await self.client.post("/infer", json={"text": text}, headers=headers)
        response.raise_for_status()
        pcm = response.content
        if not pcm or len(pcm) % 2:
            raise ValueError("invalid TTS PCM")
        for sequence, offset in enumerate(range(0, len(pcm), 32_000)):
            cancel.raise_if_cancelled()
            yield AudioChunk(context.session_id, sequence, pcm[offset:offset + 32_000],
                             INTERNAL_AUDIO_FORMAT)
