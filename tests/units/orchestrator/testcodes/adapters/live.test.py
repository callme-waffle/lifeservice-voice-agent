"""VOIC-FEAT-010 M14-S1-T1: isolated official Live event contract and rejection."""
import json
from contextlib import asynccontextmanager

import pytest

from voice_agent.adapters.live import OpenAILive


@pytest.mark.parametrize('reply', [{'type': 'error', 'message': 'private-key'}, {'type': 'wrong'}])
async def test_live_start_rejection_closes_socket_without_exposing_server_content(reply):
    """Given rejected start, release socket and expose a content-free exception."""
    sent, closed = [], []
    class Socket:
        async def send(self, raw):
            sent.append(json.loads(raw))
        async def recv(self):
            return json.dumps(reply)
    @asynccontextmanager
    async def connector(url, **kwargs):
        assert url == 'wss://api.openai.com/v1/live/sessions'
        assert kwargs['additional_headers']['Authorization'] == 'Bearer synthetic'
        try:
            yield Socket()
        finally:
            closed.append(True)
    adapter = OpenAILive('synthetic', 'gpt-live-1', 'marin', .1, connector=connector)
    with pytest.raises(RuntimeError) as exc:
        async with adapter.open():
            raise AssertionError('must not start')
    assert 'private-key' not in str(exc.value) and closed
    assert sent[0]['session']['audio']['format'] == {'type': 'audio/pcm', 'rate': 24000}
