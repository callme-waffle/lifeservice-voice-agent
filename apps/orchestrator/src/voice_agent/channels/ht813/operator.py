"""Loopback-only authenticated outbound call control (VOIC-FEAT-001 M6-S1-T4)."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response

from voice_agent.channels.ht813.call_manager import OutboundCallManager
from voice_agent.contracts.flow import CancellationToken, SessionBusy, SingleSessionGate
from voice_agent.contracts.ports import RetentionUnavailable
from voice_agent.contracts.session import (
    CallState, CallStatus, DialNumber, EventEnvelope, OutboundCallRequest,
)
from voice_agent.infrastructure.retention import EncryptedRetention


@dataclass(slots=True)
class _Call:
    session_id: UUID
    token: CancellationToken
    status: str = "dialing"
    task: asyncio.Task[None] | None = None


class OperatorCalls:
    """One in-memory control record; no number, transcript or audio is retained here."""

    def __init__(self, manager: OutboundCallManager | None,
                 gate: SingleSessionGate, token: str,
                 retention: EncryptedRetention | None = None) -> None:
        if not token:
            raise ValueError("operator access token is required")
        self.manager, self.gate, self.token = manager, gate, token
        self.retention = retention
        self.current: _Call | None = None

    async def start(self, number: str) -> _Call:
        if self.manager is None:
            raise HTTPException(503, "outbound call is not configured")
        try:
            dial_number = DialNumber(number)
        except ValueError:
            raise HTTPException(422, "invalid destination") from None
        if dial_number.value not in self.manager.outbound.policy.exact:
            raise HTTPException(403, "destination is not allowed")
        session_id = uuid4()
        request = OutboundCallRequest(session_id, dial_number, 60)
        try:
            lease = await self.gate.acquire(session_id)
        except SessionBusy:
            raise HTTPException(409, "voice session is busy") from None
        entry = _Call(session_id, CancellationToken())
        self.current = entry

        class Events:
            async def publish(self, event: EventEnvelope) -> None:
                if isinstance(event.payload, CallState):
                    entry.status = event.payload.status.value

        async def run() -> None:
            try:
                await self.manager.call(request, Events(), entry.token, lease=lease)
            except Exception:
                entry.status = CallStatus.FAILED.value
                await lease.release()
            finally:
                if entry.status not in (CallStatus.ENDED.value, CallStatus.FAILED.value,
                                        CallStatus.BUSY.value):
                    entry.status = CallStatus.ENDED.value if entry.token.cancelled else CallStatus.FAILED.value

        entry.task = asyncio.create_task(run())
        return entry

    async def close(self) -> None:
        if self.current is not None and self.current.task is not None:
            self.current.token.cancel()
            await self.current.task


def operator_router(service: OperatorCalls) -> APIRouter:
    router = APIRouter()

    def authorize(request: Request) -> None:
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if not local:
            raise HTTPException(403, "local operator access only")
        provided = request.headers.get("authorization", "")
        if not hmac.compare_digest(provided, f"Bearer {service.token}"):
            raise HTTPException(401, "operator authorization required")

    @router.post("/operator/calls", status_code=202)
    async def create_call(request: Request) -> dict[str, str]:
        authorize(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "invalid request") from None
        if not isinstance(body, dict) or set(body) != {"number"} or not isinstance(body["number"], str):
            raise HTTPException(422, "invalid request")
        entry = await service.start(body["number"])
        return {"session_id": str(entry.session_id), "status": entry.status}

    @router.get("/operator/calls/{session_id}")
    async def call_status(session_id: UUID, request: Request) -> dict[str, str]:
        authorize(request)
        entry = service.current
        if entry is None or entry.session_id != session_id:
            raise HTTPException(404, "call not found")
        return {"session_id": str(entry.session_id), "status": entry.status}

    @router.get("/operator/inbound-calls")
    async def inbound_calls(request: Request, limit: int = 50,
                            offset: int = 0) -> dict[str, object]:
        authorize(request)
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "invalid call history page")
        if service.retention is None:
            raise HTTPException(503, "call history unavailable")
        try:
            return await asyncio.to_thread(
                service.retention.list_inbound_calls, limit=limit, offset=offset,
            )
        except RetentionUnavailable:
            raise HTTPException(503, "call history unavailable") from None

    @router.delete("/operator/calls/{session_id}", status_code=202)
    async def cancel_call(session_id: UUID, request: Request) -> Response:
        authorize(request)
        entry = service.current
        if entry is None or entry.session_id != session_id:
            raise HTTPException(404, "call not found")
        entry.token.cancel()
        return Response(status_code=202)

    return router
