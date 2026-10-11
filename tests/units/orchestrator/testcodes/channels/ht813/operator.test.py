"""VOIC-FEAT-001 M6-S1-T4: authenticated loopback operator call control."""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import AllowedNumberPolicy, CallState, CallStatus, EventEnvelope


class FakeManager:
    def __init__(self):
        self.outbound = type("Outbound", (), {"policy": AllowedNumberPolicy(frozenset({"123456"}))})()
        self.calls = 0

    async def call(self, request, events, cancel, *, lease):
        self.calls += 1
        try:
            await events.publish(EventEnvelope(request.session_id, 0, CallState(CallStatus.ACTIVE)))
            await cancel.wait()
            await events.publish(EventEnvelope(request.session_id, 1, CallState(CallStatus.ENDED)))
        finally:
            await lease.release()


def make_request(host="127.0.0.1", token="test-only-token", body=None):
    if body is None:
        body = {"number": "123456"}
    content = json.dumps(body).encode()
    async def receive():
        return {"type": "http.request", "body": content, "more_body": False}
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": "/operator/calls",
                    "headers": [(b"authorization", f"Bearer {token}".encode())],
                    "client": (host, 1234), "server": ("127.0.0.1", 8000)}, receive)


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_operator_local_auth_and_cancel():
    """Given a loopback bearer request, when started and cancelled, then one call owns the gate."""
    gate, manager = SingleSessionGate(), FakeManager()
    service = OperatorCalls(manager, gate, "test-only-token")
    routes = {route.path: route.endpoint for route in operator_router(service).routes if "GET" in route.methods or route.path == "/operator/calls" and "POST" in route.methods}
    response = await routes["/operator/calls"](make_request())
    assert response["status"] == "dialing"
    assert gate.active_session_id is not None
    while manager.calls == 0:
        await asyncio.sleep(0)
    sid = service.current.session_id
    assert (await routes["/operator/calls/{session_id}"](sid, make_request()))["status"] == "active"
    cancel_route = next(r.endpoint for r in operator_router(service).routes if r.path == "/operator/calls/{session_id}" and "DELETE" in r.methods)
    await cancel_route(sid, make_request())
    await service.close()
    assert gate.active_session_id is None
    assert service.current.status == "ended"


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_operator_rejects_remote_and_wrong_token_before_dial():
    """Given remote or invalid auth, when calling, then no dial or gate lease occurs."""
    gate, manager = SingleSessionGate(), FakeManager()
    service = OperatorCalls(manager, gate, "test-only-token")
    create = next(r.endpoint for r in operator_router(service).routes if r.path == "/operator/calls")
    for request, code in ((make_request(host="192.0.2.4"), 403),
                          (make_request(token="wrong"), 401),
                          (make_request(body={"number": "999999"}), 403)):
        with pytest.raises(HTTPException) as raised:
            await create(request)
        assert raised.value.status_code == code
    assert manager.calls == 0
    assert gate.active_session_id is None


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t4_operator_asgi_smoke_without_device():
    """Given a fake dialer, when HTTP controls a call, then auth, status and cancel work."""
    import httpx
    from fastapi import FastAPI

    gate, manager = SingleSessionGate(), FakeManager()
    service = OperatorCalls(manager, gate, "test-only-token")
    app = FastAPI()
    app.include_router(operator_router(service))
    headers = {"Authorization": "Bearer test-only-token"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
        base_url="http://localhost",
    ) as client:
        created = await client.post("/operator/calls", headers=headers, json={"number": "123456"})
        assert created.status_code == 202
        sid = created.json()["session_id"]
        while manager.calls == 0:
            await asyncio.sleep(0)
        status = await client.get(f"/operator/calls/{sid}", headers=headers)
        assert status.status_code == 200
        assert status.json()["status"] == "active"
        cancelled = await client.delete(f"/operator/calls/{sid}", headers=headers)
        assert cancelled.status_code == 202
        await service.close()
    assert gate.active_session_id is None
    assert manager.calls == 1
