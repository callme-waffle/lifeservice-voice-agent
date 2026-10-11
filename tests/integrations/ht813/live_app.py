"""Supervised M6-S2 live app; VOIC-FEAT-001, PRD-03/05/06, SRS-I01/I02/C02/O01.

Run on the GPU with one JSON environment object on stdin. This is a manual
integration harness, not an automated passing test. It never initiates a call.
--smoke disables inbound and checks local port binding before a short app run.
Only allowlisted metadata reaches stdout; model output and raw exceptions do not.
Real retention data and its separately supplied key must survive this process.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
import socket
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 3600:
        parser.error('--seconds must be between 5 and 3600')
    # Keep a dedicated metadata stream; third-party native/model output is muted.
    output = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    os.umask(0o077)
    started = time.monotonic()

    def emit(kind: str, **values) -> None:
        output.write(json.dumps({'event': kind, 'elapsed_s': round(time.monotonic()-started, 3),
                                 **values}) + '\n')

    try:
        env = json.loads(sys.stdin.readline())
        if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                            for k, v in env.items()):
            raise ValueError('invalid configuration')
        from voice_agent.config import Settings
        from voice_agent.bootstrap import create_app
        from voice_agent.contracts.session import CallState, SessionState, Transcript, TaskResult, PublicError
        from voice_agent.contracts.media import DtmfEvent
        import uvicorn

        # This harness only accepts inbound calls; outbound requires separate setup.
        env['VOICE_AGENT_HT813_ALLOWED_EXACT'] = ''
        env['VOICE_AGENT_HT813_ALLOWED_PREFIXES'] = ''
        env['VOICE_AGENT_API_HOST'] = '127.0.0.1'
        env['VOICE_AGENT_HT813_INBOUND_ENABLED'] = 'false' if args.smoke else 'true'
        if args.smoke:
            sockets = []
            try:
                for port in (5060, 5061, 4000, 4002):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sockets.append(sock)
                    sock.bind((env['VOICE_AGENT_HT813_LOCAL_IPV4'], port))
                emit('phone_ports_bindable')
            finally:
                for sock in sockets:
                    sock.close()
        settings = Settings.from_env(env)
        app = create_app(settings)
        counts = Counter()

        class Events:
            async def publish(self, event):
                value = event.payload
                if isinstance(value, (CallState, SessionState)):
                    emit(type(value).__name__, status=value.status.value)
                    counts[type(value).__name__ + ':' + value.status.value] += 1
                elif isinstance(value, Transcript) and value.is_final:
                    counts['final_transcripts'] += 1
                    emit('final_transcript', count=counts['final_transcripts'])
                elif isinstance(value, TaskResult):
                    counts['task_results'] += 1
                    emit('task_result', count=counts['task_results'])
                elif isinstance(value, DtmfEvent):
                    counts['dtmf_events'] += 1
                    emit('dtmf', count=counts['dtmf_events'])
                elif isinstance(value, PublicError):
                    counts['errors'] += 1
                    emit('public_error', code=value.code.value)

        if app.state.inbound is not None:
            service = app.state.inbound
            service.events = Events()
            from voice_agent.channels.ht813.sip import parse_sip
            methods = {'INVITE', 'ACK', 'BYE', 'CANCEL', 'OPTIONS', 'REGISTER'}

            def sip_metadata(raw):
                try:
                    message = parse_sip(raw)
                    method = (message.headers.get('cseq', '').split()[-1]
                              if message.status else message.start.split()[0])
                    return {'method': method if method in methods else 'other',
                            'status': message.status or 0,
                            'has_contact': bool(message.headers.get('contact'))}
                except (ValueError, UnicodeError, IndexError):
                    return {'malformed': True}

            original_handle = service.handle_packet
            original_send = service._send
            original_terminate = service._terminate

            async def observed_handle(raw, source):
                trusted = source == service.peer
                emit('sip_receive', trusted=trusted, source_port=source[1],
                     **(sip_metadata(raw) if trusted else {}))
                try:
                    await original_handle(raw, source)
                except Exception as exc:
                    emit('sip_handler_error', category=type(exc).__name__)
                    raise

            async def observed_send(raw):
                await original_send(raw)
                emit('sip_send', **sip_metadata(raw))

            async def observed_terminate(dialog, *, normal):
                emit('dialog_terminate', normal=normal, state=dialog.state,
                     received_audio_chunks=dialog.media._incoming_audio,
                     attempted_output_chunks=dialog.media._next_audio)
                await original_terminate(dialog, normal=normal)

            service.handle_packet = observed_handle
            service._send = observed_send
            service._terminate = observed_terminate
        server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port,
                                              workers=1, access_log=False, log_config=None,
                                              ws='wsproto', timeout_graceful_shutdown=10))

        async def run():
            async def watch():
                while not server.started:
                    await asyncio.sleep(.1)
                emit('ready', inbound=not args.smoke, window_seconds=args.seconds)
                try:
                    await asyncio.sleep(args.seconds)
                    emit('window_expired')
                    server.should_exit = True
                finally:
                    emit('counts', counts=dict(counts))
            observer = asyncio.create_task(watch())
            try:
                await server.serve()
            finally:
                observer.cancel()
                await asyncio.gather(observer, return_exceptions=True)
            if not server.started:
                raise RuntimeError('startup failed')
        asyncio.run(run())
        emit('stopped')
        return 0
    except BaseException as exc:
        emit('failed', category=type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
