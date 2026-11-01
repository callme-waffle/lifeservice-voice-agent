"""VOIC-FEAT-010: PRD/SRS VOICE01..07 local boundaries; no OpenAI or real phone.
Gate 2: user approved local synthetic WebSocket/storage/cancellation execution.
"""
import asyncio
import base64
import json
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from voice_agent.adapters.live import OpenAILive
from voice_agent.channels.web.voice import web_voice_router
from voice_agent.channels.ht813.operator import OperatorCalls, operator_router
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import Channel, SessionContext, TaskResult
from voice_agent.core.live import LiveRunner
from voice_agent.infrastructure.retention import EncryptedRetention


def store_at(path, clock=None):
    return EncryptedRetention(recordings_dir=path/'private'/'audio',
                              transcripts_dir=path/'private'/'text',
                              audit_path=path/'private'/'audit.jsonl', key=b'K'*32, clock=clock)


@pytest.mark.asyncio
async def test_web_live_duplex_delegation_cancel_and_encrypted_storage(tmp_path):
    """VOICE02/03/04/05: web PCM crosses real local WS; cancel after end closes all resources."""
    storage, gate = store_at(tmp_path), SingleSessionGate()
    requests, api_events = [], []
    finalized = asyncio.Event()

    class Task:
        async def process(self, text, context, cancel):
            requests.append(text)
            return TaskResult('합성 업무 결과')

    async def mock_api(ws):
        start = json.loads(await ws.recv())
        assert start['type'] == 'session.start'
        assert start['session']['delegation'] == {'type': 'client'}
        assert ws.request.headers['Authorization'] == 'Bearer synthetic-only'
        await ws.send(json.dumps({'type': 'session.started', 'session': {'id': 'local'}}))
        async for raw in ws:
            event = json.loads(raw)
            api_events.append(event['type'])
            if event['type'] == 'session.input_audio.append':
                assert base64.b64decode(event['audio'])
                for outgoing in [
                    {'type': 'session.input_transcript.delta', 'delta': '합성 요청', 'start_ms': 0, 'end_ms': 20},
                    {'type': 'session.delegation.created', 'delegation': {'id': 'd-local', 'target': 'client'}},
                    {'type': 'session.output_audio.delta', 'delta': base64.b64encode(b'\0'*1920).decode()},
                ]:
                    await ws.send(json.dumps(outgoing))
            if event['type'] == 'session.close':
                await ws.send(json.dumps({'type': 'session.closed', 'usage': {'seconds': 1.25}}))
                finalized.set()
                return

    await storage.start()
    async with serve(mock_api, '127.0.0.1', 0) as mock:
        api_port = mock.sockets[0].getsockname()[1]
        def connector(url, **kwargs):
            assert url == 'wss://api.openai.com/v1/live/sessions'
            return connect(f'ws://127.0.0.1:{api_port}', **kwargs)
        runner = LiveRunner(OpenAILive('synthetic-only', 'gpt-live-1', 'marin', 2, connector=connector),
                            Task(), gate, storage, drain_s=5)
        app = FastAPI()
        app.include_router(web_voice_router(runner, 'synthetic-token'))
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(.01)
                async with connect(f'ws://127.0.0.1:{port}/voice', subprotocols=['voice-agent', 'token.synthetic-token']) as web:
                    await web.send(json.dumps({'type': 'start'}))
                    assert json.loads(await web.recv())['type'] == 'started'
                    await web.send((0).to_bytes(4, 'big') + b'\0'*640)
                    while True:
                        received = await web.recv()
                        if isinstance(received, bytes):
                            assert received[:4] == b'\0'*4 and len(received) == 644
                            break
                    while 'session.commentary.append' not in api_events:
                        await asyncio.sleep(.01)
                    await web.send(json.dumps({'type': 'end'}))
                    await web.send(json.dumps({'type': 'cancel'}))
                    await asyncio.wait_for(finalized.wait(), 2)
                while gate.active_session_id is not None:
                    await asyncio.sleep(.01)
            assert requests and 'partial' in requests[0]
            assert runner.last_usage_final
            audio = [storage.read_artifact(p)[1] for p in storage.recordings_dir.glob('*.va1')]
            assert {'input', 'generated', 'sent'} <= {r['direction'] for r in audio}
            texts = list(storage.transcripts_dir.glob('*.va1'))
            assert texts and all('합성 요청'.encode() not in p.read_bytes() for p in texts)
            assert storage.read_artifact(texts[0])[1]['partial'] is True
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            sock.close()
            await storage.close()


@pytest.mark.asyncio
async def test_live_and_legacy_phone_history_coexist_and_expire(tmp_path):
    """VOICE05: encrypted partial segments coexist with final legacy turns and expire at day 30."""
    instant = [datetime.now(timezone.utc)]
    storage = store_at(tmp_path, lambda: instant[0])
    await storage.start()
    live = SessionContext(uuid4(), Channel.HT813_FXO, instant[0])
    legacy = SessionContext(uuid4(), Channel.HT813_FXO, instant[0])
    app = FastAPI()
    app.include_router(operator_router(OperatorCalls(None, SingleSessionGate(), 'synthetic-token', storage)))
    try:
        await storage.record_live_text(live, 0, {'text': '합성 부분', 'direction': 'input',
                                               'start_ms': 0, 'end_ms': 20, 'partial': True})
        await storage.record_text(legacy, 0, 'transcript', '이전 최종')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1)),
                                     base_url='http://localhost', headers={'Authorization': 'Bearer synthetic-token'}) as client:
            response = await client.get(f'/operator/calls/{live.session_id}/conversation')
            assert response.status_code == 200
            assert response.json()['turns'] == [] and response.json()['segments'][0]['partial']
            previous = await client.get(f'/operator/calls/{legacy.session_id}/conversation')
            assert previous.status_code == 200 and previous.json()['turns'][0]['text'] == '이전 최종'
            instant[0] += timedelta(days=30)
            await storage.sweep()
            assert (await client.get(f'/operator/calls/{live.session_id}/conversation')).status_code == 404
    finally:
        await storage.close()
