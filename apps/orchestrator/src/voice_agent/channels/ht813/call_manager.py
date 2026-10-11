"""One gated, continuous outbound HT813 conversation (VOIC-FEAT-001 M6-S1-T4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from voice_agent.channels.ht813.conversation import PhoneMediaConversation, SequencedCallEvents
from voice_agent.channels.ht813.outbound import HT813Outbound
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SessionLease, SingleSessionGate
from voice_agent.contracts.ports import EventSink, PhoneSessionRunner
from voice_agent.contracts.session import CallStatus, Channel, OutboundCallRequest, SessionContext


class OutboundCallManager:
    def __init__(
        self, outbound: HT813Outbound, runner: PhoneSessionRunner,
        gate: SingleSessionGate, boundary: TurnBoundary,
    ) -> None:
        self.outbound, self.runner, self.gate, self.boundary = outbound, runner, gate, boundary

    async def call(
        self, request: OutboundCallRequest, events: EventSink,
        cancel: CancellationToken, *, lease: SessionLease | None = None,
    ) -> None:
        """Dial exactly one allowed destination; hold the shared gate through cleanup."""
        if request.number.value not in self.outbound.policy.exact:
            raise PermissionError("destination is not explicitly allowed")
        request.authorize(self.outbound.policy)
        context = SessionContext(request.session_id, Channel.HT813_FXO,
                                 datetime.now(timezone.utc))
        if lease is None:
            lease = await self.gate.acquire(request.session_id)
        elif (lease._gate is not self.gate or lease.session_id != request.session_id
              or lease._released or self.gate.active_session_id != request.session_id):
            raise ValueError("invalid outbound call lease")
        async with lease:
            sink = SequencedCallEvents(request.session_id, events)
            dial_task = asyncio.create_task(self.outbound.dial(request, sink, cancel))
            active_wait = asyncio.create_task(sink.active.wait())
            try:
                await asyncio.wait({active_wait, dial_task}, return_when=asyncio.FIRST_COMPLETED)
                if not sink.active.is_set():
                    await dial_task
                    return
                normal_end = [False]
                conversation = PhoneMediaConversation(
                    self.outbound, self.runner, self.boundary,
                )
                core_task = asyncio.create_task(conversation.run(
                    context, sink, cancel, lease, lambda: normal_end[0],
                ))
                try:
                    await dial_task
                finally:
                    normal_end[0] = sink.final_status is CallStatus.ENDED and not cancel.cancelled
                    cancel.cancel()
                    await core_task
            finally:
                active_wait.cancel()
                await asyncio.gather(active_wait, return_exceptions=True)
                if not dial_task.done():
                    cancel.cancel()
                    await asyncio.gather(dial_task, return_exceptions=True)
