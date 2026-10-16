"""VOIC-OPS-008 M10 F04: bounded, silent loopback WebSocket hold/busy probe.

Uses the existing private m10_probe config. No PCM, microphone input, transcript,
response body, token, or session UUID is emitted. A started packet alone does not
prove gate acquisition; hold readiness waits for the core starting/listening event.
"""
from __future__ import annotations

from collections import deque
import importlib.util
import json
import logging
import math
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID

from wsproto import ConnectionType, WSConnection
from wsproto.connection import ConnectionState
from wsproto.events import (AcceptConnection, BytesMessage, CloseConnection, Ping,
                            Pong, RejectConnection, Request, TextMessage)

if __package__:
    from .m10_probe import Config, ProbeError, SafeParser, loopback_url
else:
    # Works both as a direct script and when loaded by pytest's importlib mode.
    _spec = importlib.util.spec_from_file_location(
        "_m10_web_operator_config", Path(__file__).with_name("m10_probe.py"),
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)
    Config, ProbeError, SafeParser, loopback_url = (
        _module.Config, _module.ProbeError, _module.SafeParser, _module.loopback_url,
    )


def emit_metadata(value: dict) -> None:
    print(json.dumps(value), flush=True)


class VoiceSocket:
    def __init__(self, config: Config, *, connector=socket.create_connection, clock=time.monotonic):
        origin = urlsplit(loopback_url(config.base_url))
        self.config, self.clock = config, clock
        self.socket = connector((origin.hostname, origin.port), timeout=3)
        self.connection = WSConnection(ConnectionType.CLIENT)
        self.queue = deque()
        self.fragments = ""
        self.accepted = False
        self.start_sent = False
        self.peer_closed = False
        self.close_acknowledged = False
        self.cancel_sent = False
        try:
            self.send(Request(host=origin.netloc, target="/voice",
                              subprotocols=["voice-agent", "token." + config.token]))
            deadline = self.clock() + 3
            event = self.next_event(deadline)
            if not isinstance(event, AcceptConnection) or event.subprotocol != "voice-agent":
                raise ProbeError("web_handshake_rejected")
            self.accepted = True
            self.send(TextMessage(data='{"type":"start"}'))
            self.start_sent = True
        except BaseException:
            self.socket.close()
            raise

    def send(self, event) -> None:
        data = self.connection.send(event)
        self.socket.sendall(data)

    def next_event(self, deadline: float):
        while not self.queue:
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError
            self.socket.settimeout(min(1, remaining))
            try:
                data = self.socket.recv(8192)
            except TimeoutError:
                continue
            if not data:
                self.connection.receive_data(None)
                self.queue.extend(self.connection.events())
                if not self.queue:
                    raise ProbeError("web_disconnected")
                break
            self.connection.receive_data(data)
            self.queue.extend(self.connection.events())
        return self.queue.popleft()

    def receive_json(self, deadline: float) -> dict:
        while True:
            event = self.next_event(deadline)
            if isinstance(event, Ping):
                self.send(event.response())
            elif isinstance(event, Pong):
                continue
            elif isinstance(event, CloseConnection):
                self.received_close(event)
                raise ProbeError("web_closed")
            elif isinstance(event, (RejectConnection, BytesMessage)):
                raise ProbeError("unexpected_web_data")
            elif isinstance(event, TextMessage):
                self.fragments += event.data
                if len(self.fragments) > 16384:
                    raise ProbeError("oversized_web_message")
                if event.message_finished:
                    try:
                        value = json.loads(self.fragments)
                    except ValueError:
                        raise ProbeError("invalid_web_message") from None
                    self.fragments = ""
                    if not isinstance(value, dict):
                        raise ProbeError("invalid_web_message")
                    return value
            else:
                raise ProbeError("unexpected_web_event")

    def received_close(self, event: CloseConnection) -> None:
        self.peer_closed = True
        self.close_acknowledged = event.code in {1000, 1001}
        if self.connection.state == ConnectionState.REMOTE_CLOSING:
            self.send(event.response())

    def close(self) -> bool:
        """Send no audio: cancel, close, and bounded close acknowledgement."""
        try:
            # A busy response and peer close can arrive in the same TCP read.
            # wsproto already enters REMOTE_CLOSING before that close is popped.
            while self.queue:
                event = self.queue.popleft()
                if isinstance(event, CloseConnection):
                    self.received_close(event)
            if self.accepted and not self.peer_closed:
                if self.start_sent:
                    self.send(TextMessage(data='{"type":"cancel"}'))
                    self.cancel_sent = True
                self.send(CloseConnection(code=1000))
                deadline = self.clock() + 2
                while not self.peer_closed:
                    event = self.next_event(deadline)
                    if isinstance(event, CloseConnection):
                        self.received_close(event)
        except Exception:
            pass
        finally:
            self.socket.close()
        return self.close_acknowledged


def checked_uuid(value) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        return str(UUID(value))
    except ValueError:
        raise ProbeError("invalid_web_id") from None


def run(mode: str, config: Config, seconds: float, *, connector=socket.create_connection,
        clock=time.monotonic, emit=emit_metadata) -> dict:
    if mode not in {"hold", "busy"}:
        raise ProbeError("invalid_web_command")
    if not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise ProbeError("invalid_web_duration")
    stream = VoiceSocket(config, connector=connector, clock=clock)
    session_id = None  # Memory only, never written to state/stdout.
    acquired = False
    deadline = clock() + min(3, seconds)
    result = {"ok": False, "session_started": False, "busy": False}
    try:
        while True:
            try:
                message = stream.receive_json(deadline)
            except TimeoutError:
                if mode == "hold" and acquired:
                    result = {"ok": True, "session_started": True, "busy": False}
                    break
                raise ProbeError("web_start_timeout") from None
            if message.get("type") == "started":
                if session_id is not None:
                    raise ProbeError("duplicate_web_start")
                session_id = checked_uuid(message.get("session_id"))
            elif message.get("type") == "error":
                if message.get("code") == "busy":
                    result = {"ok": mode == "busy", "session_started": False, "busy": True}
                    break
                raise ProbeError("web_server_error")
            elif message.get("type") == "event":
                event = message.get("event")
                if (not isinstance(event, dict) or session_id is None
                        or checked_uuid(event.get("session_id")) != session_id
                        or not isinstance(event.get("payload"), dict)):
                    raise ProbeError("invalid_web_event")
                status = event["payload"].get("status")
                if status in {"starting", "listening"}:
                    if mode == "busy":
                        result = {"ok": False, "session_started": True, "busy": False}
                        break
                    if not acquired:
                        acquired = True
                        deadline = clock() + seconds
                        emit({"session_started": True})
                else:
                    # No speech was sent: any error, processing or early end
                    # prevents us from claiming that the hold lasted as requested.
                    raise ProbeError("unexpected_web_session_event")
            else:
                raise ProbeError("invalid_web_message")
    finally:
        acknowledged = stream.close()
    result.update(cancel_sent=stream.cancel_sent, close_acknowledged=acknowledged)
    result["ok"] = result["ok"] and acknowledged
    return result


def main(argv=None) -> int:
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        parser = SafeParser(description="F04 무음 웹 점유·busy 확인")
        parser.add_argument("command", choices=["hold", "busy"])
        parser.add_argument("--config-file", type=Path, required=True)
        parser.add_argument("--seconds", type=float, default=30)
        args = parser.parse_args(argv)
        result = run(args.command, Config.load(args.config_file), args.seconds)
        emit_metadata(result)
        return 0 if result["ok"] else 1
    except ProbeError as error:
        emit_metadata({"ok": False, "reason": error.code})
        return 1
    except (Exception, KeyboardInterrupt):
        emit_metadata({"ok": False, "reason": "web_probe_failed"})
        return 1
    finally:
        logging.disable(previous)


if __name__ == "__main__":
    raise SystemExit(main())
