"""VOIC-FEAT-001 M4-S2-T2 admission, backpressure and cancellation tests."""

import asyncio
from uuid import UUID

import pytest

from voice_agent.contracts.flow import (
    BoundedAudioBuffer,
    CancellationToken,
    OperationCancelled,
    SessionBusy,
    SingleSessionGate,
)
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT

SESSION = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")


def chunk(sequence: int, session_id: UUID = SESSION) -> AudioChunk:
    return AudioChunk(session_id, sequence, b"\x00\x00" * 320, INTERNAL_AUDIO_FORMAT)


@pytest.mark.asyncio
async def test_voic_feat_001_single_gate_rejects_second_channel_and_releases() -> None:
    """Given one owner, when another enters, then it is busy until release."""
    gate = SingleSessionGate()
    async with await gate.acquire(SESSION):
        assert gate.active_session_id == SESSION
        with pytest.raises(SessionBusy):
            await gate.acquire(OTHER)
    assert gate.active_session_id is None
    async with await gate.acquire(OTHER):
        assert gate.active_session_id == OTHER


@pytest.mark.asyncio
async def test_voic_feat_001_buffer_backpressures_and_preserves_order() -> None:
    """Given a full buffer, when sending, then producer waits and order survives."""
    buffer = BoundedAudioBuffer(SESSION, 1, CancellationToken())
    await buffer.send(chunk(0))
    pending = asyncio.create_task(buffer.send(chunk(1)))
    await asyncio.sleep(0)
    assert not pending.done()
    assert await buffer.receive() == chunk(0)
    await asyncio.wait_for(pending, 1)
    assert await buffer.receive() == chunk(1)
    await buffer.finish()
    assert await buffer.receive() is None
    assert await buffer.receive() is None


@pytest.mark.asyncio
async def test_voic_feat_001_buffer_cancel_wakes_blocked_producer() -> None:
    """Given blocked send, when cancelled, then it ends without hanging."""
    buffer = BoundedAudioBuffer(SESSION, 1, CancellationToken())
    await buffer.send(chunk(0))
    pending = asyncio.create_task(buffer.send(chunk(1)))
    await asyncio.sleep(0)
    buffer.cancel()
    with pytest.raises(OperationCancelled):
        await asyncio.wait_for(pending, 1)
    with pytest.raises(OperationCancelled):
        await buffer.receive()


@pytest.mark.asyncio
async def test_voic_feat_001_buffer_rejects_wrong_sequence_and_session() -> None:
    """Given channel frames, when correlation or order differs, then reject them."""
    buffer = BoundedAudioBuffer(SESSION, 1, CancellationToken())
    with pytest.raises(ValueError):
        await buffer.send(chunk(1))
    with pytest.raises(ValueError):
        await buffer.send(chunk(0, OTHER))
