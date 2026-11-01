"""VOIC-FEAT-010 M14-S2-T1: continuous phone input bypasses turn gating."""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from voice_agent.channels.ht813.conversation import PhoneMediaConversation
from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.flow import CancellationToken, SingleSessionGate
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT
from voice_agent.contracts.session import Channel, SessionContext


async def test_live_phone_reads_silence_continuously_while_playing():
    """Given Live capability, even silence reaches the runner without waiting for VAD turns."""
    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    token, gate = CancellationToken(), SingleSessionGate()
    played = asyncio.Event()
    class Media:
        sequence = 0
        async def receive_audio(self):
            chunk = AudioChunk(context.session_id, self.sequence, b'\0'*640, INTERNAL_AUDIO_FORMAT)
            self.sequence += 1
            return chunk
        async def receive_dtmf(self):
            await asyncio.Future()
        async def send_audio(self, chunk):
            played.set()
            await asyncio.Future()
    class Runner:
        continuous_input = True
        async def run(self, current, incoming, events, output, cancel, *, lease):
            assert current == context and lease.session_id == context.session_id
            playback = asyncio.create_task(output(AudioChunk(context.session_id, 0, b'\0'*640, INTERNAL_AUDIO_FORMAT)))
            try:
                await played.wait()
                assert (await anext(incoming)).sequence == 0
                assert (await anext(incoming)).sequence == 1
            finally:
                playback.cancel()
                await asyncio.gather(playback, return_exceptions=True)
    class Events:
        async def publish(self, event):
            pass
    async with await gate.acquire(context.session_id) as lease:
        await asyncio.wait_for(PhoneMediaConversation(Media(), Runner(), TurnBoundary()).run(
            context, Events(), token, lease, lambda: False), 1)
    assert gate.active_session_id is None
