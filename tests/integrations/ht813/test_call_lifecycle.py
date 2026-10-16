"""VOIC-OPS-008 M10-S1/S2: isolated UDP/RTP, core, encrypted retention and HTTP."""

from __future__ import annotations

import asyncio
import socket
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from tests.integrations.ht813.test_loopback_sip_rtp import (
    ALLOWED, LOCAL, Events, SyntheticSTT, SyntheticTask, available_ports,
    inbound_request, media_port_from_sdp, response, rtp_output, rtp_turn,
    sip_receive, sip_send, udp_socket, until,
)
from voice_agent.channels.ht813.call_manager import OutboundCallManager
from voice_agent.channels.ht813.inbound import InboundSIPService
from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.channels.ht813.outbound import HT813Outbound
from voice_agent.channels.ht813.rtp import RTPMedia
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import AllowedNumberPolicy, CallStatus, StepTimeouts
from voice_agent.core.orchestrator import VoiceOrchestrator
from voice_agent.infrastructure.retention import EncryptedRetention

TOKEN = "synthetic-lifecycle-token"


class InterruptibleTask(SyntheticTask):
    def __init__(self, phase):
        super().__init__()
        self.phase = phase
        self.entered = asyncio.Event()
        self.finished = asyncio.Event()

    async def process(self, text, context, cancel, *, history=()):
        result = await super().process(text, context, cancel, history=history)
        if self.phase == "processing" and len(self.calls) == 1:
            self.entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.finished.set()
        return result


class LifecycleTTS:
    def __init__(self, phase):
        self.phase, self.count = phase, 0

    async def synthesize(self, text, context, cancel):
        self.count += 1
        # The first playback has 50 real paced RTP packets; later replies have 5.
        samples = 16000 if self.phase == "playback" and self.count == 1 else 1600
        yield AudioChunk(context.session_id, 0,
                         (900).to_bytes(2, "little", signed=True) * samples,
                         INTERNAL_AUDIO_FORMAT)


class ObservedMedia(RTPMedia):
    """Observe the real RTP sender without replacing its packet/codec behavior."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sending = asyncio.Event()
        self.send_finished = asyncio.Event()
        self.closed = asyncio.Event()

    async def send_audio(self, chunk):
        self.sending.set()
        try:
            await super().send_audio(chunk)
        finally:
            self.send_finished.set()

    async def close(self):
        await super().close()
        self.closed.set()


def assert_port_released(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind((LOCAL, port))


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["inbound-bye", "outbound-bye", "operator-cancel"])
@pytest.mark.parametrize("phase", ["processing", "playback"])
async def test_voic_ops_008_m10_interruption_reclaims_and_accepts_next_call(tmp_path, route, phase):
    """PRD 0.1.0 PRD-02/03/06/08; SRS 0.1.0 C03~C05/T04/T06/I03/I04/O04/O12.

    Given a real core/UDP/RTP call with synthetic model data and encrypted files,
    when BYE or authenticated DELETE interrupts processing or actual RTP playback,
    then work and media finish, the gate/port are reclaimed, partial HTTP history
    is correct, and a new call completes with a new ID and empty prior context.
    This is loopback evidence, not physical FXO Idle or live model cancellation.
    """
    peer_sip, peer_rtp = udp_socket(), udp_socket()
    app_sip, app_rtp = available_ports(2)
    gate, events, medias = SingleSessionGate(), Events(), []
    store = EncryptedRetention(
        recordings_dir=tmp_path / "private" / "recordings",
        transcripts_dir=tmp_path / "private" / "transcripts",
        audit_path=tmp_path / "private" / "deletion-audit.jsonl", key=bytes(range(32)),
    )
    stt, task, tts = SyntheticSTT(), InterruptibleTask(phase), LifecycleTTS(phase)
    runner = VoiceOrchestrator(stt, task, tts, gate, StepTimeouts(5, 5, 5), retention=store)

    def media_factory(*args, **kwargs):
        media = ObservedMedia(*args, **kwargs)
        medias.append(media)
        return media

    channel = HT813Outbound(
        host=LOCAL, port=peer_sip.getsockname()[1], local_host=LOCAL,
        local_sip_port=app_sip, local_rtp_port=app_rtp, user_id="agent",
        policy=AllowedNumberPolicy(exact=frozenset({ALLOWED})), media_factory=media_factory,
    )
    operator = OperatorCalls(
        OutboundCallManager(channel, runner, gate, TurnBoundary(400, 100, 2000)),
        gate, TOKEN, store,
    )
    inbound = InboundSIPService(
        peer_host=LOCAL, peer_port=peer_sip.getsockname()[1], local_host=LOCAL,
        sip_port=app_sip, rtp_port=app_rtp, user_id="agent", runner=runner,
        gate=gate, boundary=TurnBoundary(400, 100, 2000), events=events,
        retention=store, media_factory=media_factory,
    )
    app = FastAPI()
    app.include_router(operator_router(operator))

    async def inbound_send(method, call_id):
        await sip_send(peer_sip, inbound_request(
            method, sip_port=app_sip, peer_port=peer_sip.getsockname()[1],
            media_port=peer_rtp.getsockname()[1], call_id=call_id,
        ), app_sip)

    async def connect(client, index):
        if route == "inbound-bye":
            call_id = f"synthetic-lifecycle-{index}"
            await inbound_send("INVITE", call_id)
            assert (await sip_receive(peer_sip)).status == 100
            answer = await sip_receive(peer_sip)
            assert answer.status == 200 and media_port_from_sdp(answer.body) == app_rtp
            await inbound_send("ACK", call_id)
            await until(lambda: events.call_statuses().count(CallStatus.ACTIVE) == index)
            return gate.active_session_id, call_id
        created = await client.post("/operator/calls", json={"number": ALLOWED})
        assert created.status_code == 202
        sid = UUID(created.json()["session_id"])
        invite = await sip_receive(peer_sip)
        assert invite.start.startswith("INVITE ")
        assert media_port_from_sdp(invite.body) == app_rtp
        await sip_send(peer_sip, response(invite, 200,
                                       media_port=peer_rtp.getsockname()[1]), app_sip)
        assert (await sip_receive(peer_sip)).start.startswith("ACK ")
        await until(lambda: operator.current.status == "active")
        assert (await client.get(f"/operator/calls/{sid}")).json()["status"] == "active"
        return sid, invite.headers["call-id"]

    async def end(client, sid, call_id, *, operator_cancel=False):
        if operator_cancel:
            result = await client.delete(f"/operator/calls/{sid}")
            assert result.status_code == 202
            bye = await sip_receive(peer_sip)
            assert bye.start.startswith("BYE ") and bye.headers["call-id"] == call_id
        else:
            await inbound_send("BYE", call_id)
            assert (await sip_receive(peer_sip)).status == 200
        if route != "inbound-bye":
            await asyncio.wait_for(operator.current.task, 2)
            assert (await client.get(f"/operator/calls/{sid}")).json()["status"] == "ended"
        await until(lambda: gate.active_session_id is None)
        assert medias[-1].closed.is_set()
        assert_port_released(app_rtp)

    try:
        await store.start()
        if route == "inbound-bye":
            await inbound.start()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(LOCAL, 1234)),
            base_url="http://localhost", headers={"Authorization": f"Bearer {TOKEN}"},
        ) as client:
            first, first_call_id = await connect(client, 1)
            assert first is not None and gate.active_session_id == first
            await rtp_turn(peer_rtp, app_rtp, 0)
            received = 0
            if phase == "processing":
                await asyncio.wait_for(task.entered.wait(), 2)
                assert not task.finished.is_set() and tts.count == 0
            else:
                await asyncio.wait_for(medias[0].sending.wait(), 2)
                received = len(await rtp_output(peer_rtp, 1))
                assert not medias[0].send_finished.is_set(), "playback finished before interruption"
            await end(client, first, first_call_id, operator_cancel=route == "operator-cancel")
            if phase == "processing":
                assert task.finished.is_set() and tts.count == 0
            else:
                assert medias[0].send_finished.is_set()
            # Queued packets predate cleanup; drain them before checking silence.
            while True:
                try:
                    peer_rtp.recvfrom(2048)
                    received += 1
                except BlockingIOError:
                    break
            if phase == "processing":
                assert received == 0
            else:
                assert 0 < received < 50
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.get_running_loop().sock_recvfrom(peer_rtp, 2048), .05)
            first_history = await client.get(f"/operator/calls/{first}/conversation")
            assert first_history.status_code == 200
            expected = [("user", "synthetic-question-1")]
            if phase == "playback":
                expected.append(("assistant", "synthetic-answer-1"))
            assert [(row["speaker"], row["text"]) for row in first_history.json()["turns"]] == expected

            second, second_call_id = await connect(client, 2)
            assert second != first and gate.active_session_id == second
            await rtp_turn(peer_rtp, app_rtp, 100)
            assert len(await rtp_output(peer_rtp)) == 5
            await asyncio.wait_for(medias[1].send_finished.wait(), 2)
            assert len(task.calls) == 2
            assert task.calls[0][0] == first and task.calls[1][0] == second
            assert task.calls[0][2] == task.calls[1][2] == ()
            await end(client, second, second_call_id)
            second_history = await client.get(f"/operator/calls/{second}/conversation")
            assert second_history.status_code == 200
            assert [(row["turn_index"], row["speaker"], row["text"])
                    for row in second_history.json()["turns"]] == [
                        (0, "user", "synthetic-question-2"),
                        (0, "assistant", "synthetic-answer-2"),
                    ]
            assert (await client.get(f"/operator/calls/{first}/conversation")).json() == first_history.json()
            if route == "inbound-bye":
                listing = await client.get("/operator/inbound-calls")
                assert listing.status_code == 200
                history = listing.json()["items"]
                assert {row["session_id"] for row in history} == {str(first), str(second)}
                assert all(row["status"] == "ended" and row["ended_at"] for row in history)
    finally:
        try:
            await operator.close()
        finally:
            try:
                await inbound.close()
            finally:
                try:
                    await store.close()
                finally:
                    peer_sip.close()
                    peer_rtp.close()
    assert_port_released(app_sip)
    assert_port_released(app_rtp)
