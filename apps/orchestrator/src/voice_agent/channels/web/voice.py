"""Authenticated browser voice WebSocket (VOIC-FEAT-001 M5-S4)."""

from __future__ import annotations

import asyncio
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from voice_agent.contracts.flow import CancellationToken, SessionBusy
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.ports import VoiceSessionRunner
from voice_agent.contracts.session import Channel, EventEnvelope, SessionContext


def web_voice_router(runner: VoiceSessionRunner, access_token: str) -> APIRouter:
    if not access_token:
        raise ValueError("web access token must be configured")
    router = APIRouter()

    @router.websocket("/voice")
    async def voice(ws: WebSocket) -> None:
        protocols = ws.scope.get("subprotocols", [])
        authorized = any(
            p.startswith("token.") and hmac.compare_digest(p[6:], access_token)
            for p in protocols
        )
        if "voice-agent" not in protocols or not authorized:
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol="voice-agent")
        try:
            start = json.loads(await ws.receive_text())
            if start != {"type": "start"}:
                await ws.close(code=1003)
                return
        except (ValueError, RuntimeError, WebSocketDisconnect):
            await ws.close(code=1003)
            return

        context = SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))
        token = CancellationToken()
        send_lock = asyncio.Lock()
        await ws.send_json({"type": "started", "session_id": str(context.session_id)})

        class Events:
            async def publish(self, event: EventEnvelope) -> None:
                async with send_lock:
                    await ws.send_json({"type": "event", "event": jsonable_encoder(event)})

        async def output(chunk: AudioChunk) -> None:
            if chunk.session_id != context.session_id or chunk.format != INTERNAL_AUDIO_FORMAT:
                raise ValueError("invalid outgoing web audio")
            async with send_lock:
                await ws.send_bytes(chunk.sequence.to_bytes(4, "big") + chunk.data)

        async def incoming():
            sequence = 0
            try:
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        token.cancel()
                        return
                    data = message.get("bytes")
                    if data is not None:
                        if len(data) < 6 or len(data) > 32_004:
                            raise ValueError("invalid web audio frame size")
                        received = int.from_bytes(data[:4], "big")
                        if received != sequence:
                            raise ValueError("non-contiguous web audio sequence")
                        yield AudioChunk(context.session_id, sequence, data[4:], INTERNAL_AUDIO_FORMAT)
                        sequence += 1
                        continue
                    command = json.loads(message.get("text") or "")
                    if command == {"type": "end"}:
                        return
                    if command == {"type": "cancel"}:
                        token.cancel()
                        return
                    raise ValueError("unsupported web voice message")
            except (ValueError, RuntimeError):
                raise

        try:
            await runner.run(context, incoming(), Events(), output, token)
        except SessionBusy:
            await ws.send_json({"type": "error", "code": "busy"})
        except ValueError:
            await ws.send_json({"type": "error", "code": "invalid_input"})
        except Exception:
            token.cancel()
            try:
                await ws.send_json({"type": "error", "code": "unavailable"})
            except RuntimeError:
                pass
        finally:
            token.cancel()
            try:
                await ws.close()
            except RuntimeError:
                pass

    return router
