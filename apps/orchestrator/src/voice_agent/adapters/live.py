"""OpenAI Live WebSocket transport; never logs credentials or event content."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

from websockets.asyncio.client import connect


class LiveTransport:
    def __init__(self, socket):
        self.socket = socket
        self._lock = asyncio.Lock()

    async def send(self, event):
        async with self._lock:
            await self.socket.send(json.dumps({"event_id": str(uuid4()), **event}))

    async def receive(self):
        event = json.loads(await self.socket.recv())
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("invalid Live event")
        if event["type"] == "error":
            raise RuntimeError("Live service rejected the session")
        return event


class OpenAILive:
    def __init__(self, api_key, model, voice, timeout_s, *, connector=connect):
        self._key, self.model, self.voice = api_key, model, voice
        self.timeout_s, self._connector = timeout_s, connector

    @asynccontextmanager
    async def open(self):
        async with self._connector(
            "wss://api.openai.com/v1/live/sessions",
            additional_headers={"Authorization": f"Bearer {self._key}"},
            open_timeout=self.timeout_s, close_timeout=1,
            max_size=1_048_576, max_queue=4,
        ) as socket:
            transport = LiveTransport(socket)
            async with asyncio.timeout(self.timeout_s):
                await transport.send({"type": "session.start", "session": {
                    "model": self.model,
                    "instructions": "한국어로 간결하게 대화하세요. 외부 업무는 client delegation으로 위임하고 결과를 확인한 뒤 답하세요. 전사 조각은 미완성이며 업무 성공을 추측하지 마세요.",
                    "audio": {"format": {"type": "audio/pcm", "rate": 24000},
                              "output": {"voice": self.voice}},
                    "delegation": {"type": "client"},
                }})
                event = await transport.receive()
                if event["type"] != "session.started":
                    raise RuntimeError("Live session did not start")
            transport.started = event
            yield transport
