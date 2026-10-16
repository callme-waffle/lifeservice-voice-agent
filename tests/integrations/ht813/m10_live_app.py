"""VOIC-OPS-008 M10 supervised metadata observer (PRD-02/03/06, SRS-T04/O07/O11).

Starting this app requires the separate live-environment Gate 2. It never dials.
One worker, an existing exact allowlist and retention key/path are preserved.
Only metadata goes to stdout; the UUID/alias map stays in a private local file.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import os
import queue
import threading
from pathlib import Path
import sys
import tempfile
import time

from voice_agent.channels.ht813.sip import parse_sip
from voice_agent.contracts.media import DtmfEvent
from voice_agent.contracts.session import CallState, SessionState, Transcript, TaskResult, PublicError


class Metadata:
    def __init__(self, output, mapping_file: Path | None = None, *, capacity=1024):
        self.output, self.mapping_file = output, mapping_file
        self.started = time.monotonic()
        self.aliases: dict[str, str] = {}
        self.counts = Counter()
        if capacity < 1:
            raise ValueError("positive queue capacity required")
        self._queue = queue.Queue(maxsize=capacity)
        self._closing = threading.Event()
        self._lost = threading.Event()
        if mapping_file is not None:
            parent = mapping_file.parent
            if parent.is_symlink() or not parent.is_dir() or parent.stat().st_mode & 0o077:
                raise ValueError('private mapping directory required')
            if mapping_file.exists() or mapping_file.is_symlink():
                raise ValueError('mapping file must be new for this run')
            self._save()
        self._worker = threading.Thread(target=self._write, daemon=True, name="m10-metadata")
        self._worker.start()

    @property
    def evidence_lost(self):
        return self._lost.is_set()

    def _write(self):
        while not self._closing.is_set() or not self._queue.empty():
            try:
                data, sid = self._queue.get(timeout=.05)
            except queue.Empty:
                continue
            try:
                alias = self.alias(sid)
                if alias is not None:
                    data["call"] = alias
                self.output.write(json.dumps(data, sort_keys=True) + "\n")
                self.output.flush()
            except Exception:
                self._lost.set()
            finally:
                self._queue.task_done()
        if self.evidence_lost:
            try:
                self.output.write('{"event":"evidence_lost"}\n')
                self.output.flush()
            except Exception:
                pass

    def close(self, timeout=1.0):
        """Bounded drain: a stuck sink remains only in a daemon thread."""
        self._closing.set()
        self._worker.join(timeout)
        if self._worker.is_alive():
            self._lost.set()
        return not self.evidence_lost

    def _save(self):
        if self.mapping_file is None:
            return
        fd, name = tempfile.mkstemp(dir=self.mapping_file.parent, prefix='.m10-map-')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({alias: sid for sid, alias in self.aliases.items()}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.mapping_file)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def alias(self, sid):
        if sid is None:
            return None
        key = str(sid)
        if key not in self.aliases:
            self.aliases[key] = f'call-{len(self.aliases)+1}'
            self._save()
        return self.aliases[key]

    def emit(self, kind: str, sid=None, **fields):
        # Callers supply only schema-defined fields, never exception strings/bodies.
        data = {'event': kind, 'utc': datetime.now(timezone.utc).isoformat(),
                'elapsed_s': round(time.monotonic()-self.started, 6)}
        data.update(fields)
        self.counts[kind] += 1
        if self._closing.is_set():
            self._lost.set()
            return
        try:
            self._queue.put_nowait((data, sid))
        except queue.Full:
            self._lost.set()

    def event(self, envelope):
        value, sid = envelope.payload, envelope.session_id
        if isinstance(value, (CallState, SessionState)):
            self.emit(type(value).__name__, sid, status=value.status.value)
        elif isinstance(value, Transcript) and value.is_final:
            self.emit('final_transcript', sid)
        elif isinstance(value, TaskResult):
            self.emit('task_result', sid)
        elif isinstance(value, DtmfEvent):
            self.emit('dtmf', sid, test_symbol=value.digit if value.digit in {'5', '#'} else 'other',
                      duration_ms=value.duration_ms)
        elif isinstance(value, PublicError):
            self.emit('public_error', sid, code=value.code.value)

    def sip(self, kind, raw, sid=None, *, call_id=None, direction="unknown"):
        try:
            message = parse_sip(raw) if isinstance(raw, bytes) else raw
            method = (message.headers.get('cseq', '').split()[-1]
                      if message.status else message.start.split()[0])
            allowed = {'INVITE', 'ACK', 'BYE', 'CANCEL', 'OPTIONS', 'REGISTER'}
            matched = bool(sid is not None and call_id
                           and message.headers.get("call-id") == call_id)
            status = message.status
            if status and not 100 <= status <= 699:
                raise ValueError("invalid SIP status")
            self.emit(kind, sid if matched else None, matched=matched, direction=direction,
                      method=method if method in allowed else "other", status=status,
                      has_contact=bool(message.headers.get("contact")))
        except (ValueError, IndexError, UnicodeError):
            self.emit(kind, malformed=True, matched=False, direction=direction)


class ObservedEvents:
    def __init__(self, original, metadata):
        self.original, self.metadata = original, metadata

    async def publish(self, event):
        await self.original.publish(event)
        self.metadata.event(event)


def instrument(app, metadata: Metadata):
    """Wrap existing instances only; preserve admission/leases, events and exceptions."""
    calls = app.state.operator_calls
    gate = calls.gate
    original_release = gate.release

    async def release(sid):
        await original_release(sid)
        metadata.emit('gate_released', sid)
    gate.release = release

    def media_factory(original):
        def create(sid, **kwargs):
            media = original(sid, **kwargs)
            send_audio, close = media.send_audio, media.close
            output = Counter(attempted=0, completed=0, cancelled=0, failed=0)

            async def send(chunk):
                output["attempted"] += 1
                metadata.emit("output_chunk_started", sid)
                try:
                    result = await send_audio(chunk)
                except asyncio.CancelledError:
                    output["cancelled"] += 1
                    metadata.emit("output_chunk_cancelled", sid)
                    raise
                except Exception:
                    output["failed"] += 1
                    metadata.emit("output_chunk_failed", sid)
                    raise
                else:
                    output["completed"] += 1
                    metadata.emit("output_chunk_complete", sid, duration_ms=chunk.duration_ms)
                    return result

            async def finish():
                await close()
                # Snapshot of callback counts, not RTP packets or first-audible time.
                metadata.emit('media_closed', sid,
                              output_inflight=output['attempted']-output['completed']
                                              -output['cancelled']-output['failed'],
                              input_audio_chunks=getattr(media, '_incoming_audio', 0),
                              **{f'output_{key}': value for key, value in output.items()})
            media.send_audio, media.close = send, finish
            return media
        return create

    inbound = app.state.inbound
    if inbound is not None:
        inbound.events = ObservedEvents(inbound.events, metadata)
        inbound._media_factory = media_factory(inbound._media_factory)
        original_handle, original_send = inbound.handle_packet, inbound._send

        async def handle(raw, source):
            if source == inbound.peer:
                dialog = inbound._dialog
                metadata.sip('sip_receive', raw,
                             dialog.context.session_id if dialog else None,
                             call_id=dialog.call_id if dialog else None, direction='inbound')
            else:
                metadata.emit('sip_untrusted')
            return await original_handle(raw, source)

        async def send(raw):
            await original_send(raw)
            dialog = inbound._dialog
            metadata.sip('sip_send', raw, dialog.context.session_id if dialog else None,
                         call_id=dialog.call_id if dialog else None, direction='inbound')
        inbound.handle_packet, inbound._send = handle, send

    if calls.manager is not None:
        manager = calls.manager
        original_call = manager.call

        async def call(request, events, cancel, *, lease=None):
            return await original_call(request, ObservedEvents(events, metadata), cancel, lease=lease)
        manager.call = call
        outbound = manager.outbound
        outbound._media_factory = media_factory(outbound._media_factory)
        original_peer = outbound._peer_factory

        def peer_factory(*args, **kwargs):
            peer = original_peer(*args, **kwargs)
            send_original, receive_original, close_original = peer.send, peer.receive, peer.close
            sid, call_id = gate.active_session_id, None

            async def send(raw):
                nonlocal call_id
                await send_original(raw)
                try:
                    message = parse_sip(raw)
                    if call_id is None and message.start.startswith('INVITE '):
                        call_id = message.headers.get('call-id')
                except (ValueError, IndexError, UnicodeError):
                    pass
                metadata.sip('sip_send', raw, sid, call_id=call_id, direction='outbound')

            async def receive(timeout_s):
                message = await receive_original(timeout_s)
                metadata.sip('sip_receive', message, sid, call_id=call_id, direction='outbound')
                return message

            async def close():
                await close_original()
                metadata.emit('sip_closed', sid)
            peer.send, peer.receive, peer.close = send, receive, close
            return peer
        outbound._peer_factory = peer_factory


async def serve(app, metadata, seconds, *, shutdown_grace=15):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8000, workers=1,
                                          access_log=False, log_config=None, ws='wsproto',
                                          lifespan='on', timeout_graceful_shutdown=10))

    until = metadata.started+seconds

    async def deadline():
        # Request normal shutdown at the window boundary, even before readiness.
        while not server.started and time.monotonic() < until:
            await asyncio.sleep(min(.1, max(0, until-time.monotonic())))
        if server.started:
            metadata.emit('ready', window_seconds=seconds)
        await asyncio.sleep(max(0, until-time.monotonic()))
        server.should_exit = True
        metadata.emit('window_expired')

    watcher = asyncio.create_task(deadline())
    clean = False
    try:
        await asyncio.wait_for(server.serve(),
                               timeout=max(0, until-time.monotonic())+shutdown_grace)
        lifespan = getattr(server, 'lifespan', None)
        clean = bool(server.started and lifespan is not None
                     and not lifespan.startup_failed and not lifespan.shutdown_failed
                     and not lifespan.error_occurred and lifespan.shutdown_event.is_set())
    except Exception:
        pass
    finally:
        server.should_exit = True
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        metadata.emit('stopped' if clean else 'shutdown_failed', ready_seen=server.started)
        await asyncio.to_thread(metadata.close)
    return 0 if clean and not metadata.evidence_lost else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping-file', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 1800:
        parser.error('window must be 5..1800 seconds')
    output = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    os.umask(0o077)
    metadata = None
    try:
        from voice_agent.bootstrap import create_app
        from voice_agent.config import Settings
        settings = Settings.from_env(os.environ)
        if (settings.host != '127.0.0.1' or settings.port != 8000
                or not settings.ht813_inbound_enabled or settings.allowed_numbers is None
                or len(settings.allowed_numbers.exact) != 1 or settings.allowed_numbers.prefixes):
            raise ValueError('supervised live configuration required')
        metadata = Metadata(output, args.mapping_file)
        app = create_app(settings)
        instrument(app, metadata)
        return asyncio.run(serve(app, metadata, args.seconds))
    except BaseException:
        # No exception names/messages: paths, tokens or model text may be embedded.
        if metadata is not None:
            metadata.emit('observer_failed')
        return 1
    finally:
        if metadata is not None:
            metadata.close()


if __name__ == '__main__':
    raise SystemExit(main())
