"""VOIC-OPS-008 M10 F04; PRD-01/03/06, SRS-C03/I04/W01/W03.

Real loopback WebSocket framing and production router, fake runner, synthetic
secrets. No audio/model/task API/phone/operational host is used.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from fastapi import FastAPI
import pytest
import uvicorn

from voice_agent.channels.web.voice import web_voice_router
from voice_agent.contracts.flow import SingleSessionGate
from voice_agent.contracts.session import EventEnvelope, SessionState, SessionStatus

SPEC = importlib.util.spec_from_file_location("m10_web_probe_under_test", Path(__file__).with_name("m10_web_probe.py"))
web = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = web
SPEC.loader.exec_module(web)
TOKEN = "synthetic-private-web-token"


class SilentRunner:
    def __init__(self, *, early_close=False):
        self.gate = SingleSessionGate()
        self.session_ids = []
        self.received = []
        self.cancelled = 0
        self.early_close = early_close

    async def run(self, context, incoming, events, send_audio, cancel):
        async with await self.gate.acquire(context.session_id):
            self.session_ids.append(str(context.session_id))
            await events.publish(EventEnvelope(context.session_id, 0, SessionState(SessionStatus.STARTING)))
            if self.early_close:
                return
            async for chunk in incoming:
                self.received.append(chunk)
                raise AssertionError("The silent probe must not send audio")
            self.cancelled += int(cancel.cancelled)


@contextmanager
def local_server(runner):
    app = FastAPI()
    app.include_router(web_voice_router(runner, TOKEN))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", ws="wsproto",
                                         log_config=None, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.005)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


def config_file(tmp_path, url, *, token=TOKEN):
    values = {"token_file": token, "number_file": "12345", "state_file": "{}"}
    raw = {"base_url": url}
    for name, value in values.items():
        path = tmp_path / name
        path.write_text(value)
        path.chmod(0o600)
        raw[name] = str(path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    path.chmod(0o600)
    return path


def test_voic_ops_008_web_hold_busy_and_next_hold_use_no_audio(tmp_path):
    """Given one silent holder, when a second probe starts, then busy is seen and cancellation permits reuse."""
    runner, ready = SilentRunner(), threading.Event()
    emitted = []
    with local_server(runner) as url:
        config = web.Config.load(config_file(tmp_path, url))

        def readiness(value):
            emitted.append(value)
            ready.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            hold = pool.submit(web.run, "hold", config, .3, emit=readiness)
            assert ready.wait(3)
            assert not hold.done()  # Ready metadata arrives before the hold completes.
            assert runner.gate.active_session_id is not None
            busy = web.run("busy", config, .2, emit=emitted.append)
            assert busy["ok"] and busy["busy"] and not busy["session_started"]
            result = hold.result(timeout=4)
        assert result["ok"] and result["session_started"] and result["cancel_sent"]
        assert result["close_acknowledged"]
        reused = web.run("hold", config, .05, emit=emitted.append)
        assert reused["ok"] and runner.gate.active_session_id is None
    assert not runner.received and runner.cancelled == 2
    assert emitted == [{"session_started": True}, {"session_started": True}]
    output = json.dumps([emitted, result, busy, reused])
    assert TOKEN not in output
    assert all(sid not in output for sid in runner.session_ids)
    assert json.loads(config.state_file.read_text()) == {}  # Web UUID stays in memory.


def test_voic_ops_008_web_busy_mode_fails_when_slot_is_free(tmp_path):
    """Given a free slot, when busy is requested, then started is not mistaken for rejection and the slot is released."""
    runner = SilentRunner()
    with local_server(runner) as url:
        config = web.Config.load(config_file(tmp_path, url))
        result = web.run("busy", config, .2, emit=lambda _: pytest.fail("busy mode emits no hold readiness"))
        assert not result["ok"] and not result["busy"] and result["session_started"]
        assert result["cancel_sent"] and result["close_acknowledged"]
        assert runner.gate.active_session_id is None
    assert not runner.received


def test_voic_ops_008_web_hold_rejects_busy_without_ready_signal(tmp_path):
    """Given an occupied gate, when hold receives started then busy, then it never announces acquired readiness."""
    runner, ready = SilentRunner(), threading.Event()
    with local_server(runner) as url:
        config = web.Config.load(config_file(tmp_path, url))
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(web.run, "hold", config, .2, emit=lambda _: ready.set())
            assert ready.wait(3)
            emitted = []
            second = web.run("hold", config, .1, emit=emitted.append)
            assert not second["ok"] and second["busy"] and not emitted
            assert first.result(timeout=4)["ok"]


def test_voic_ops_008_web_early_server_close_is_not_success(tmp_path):
    """Given early server shutdown, when a requested hold is cut short, then it fails instead of claiming elapsed occupancy."""
    runner = SilentRunner(early_close=True)
    with local_server(runner) as url:
        config = web.Config.load(config_file(tmp_path, url))
        with pytest.raises(web.ProbeError, match="web_closed"):
            web.run("hold", config, .2, emit=lambda _: None)
    assert not runner.received


def test_voic_ops_008_web_cli_rejects_auth_without_sensitive_output(tmp_path, capsys):
    """Given the wrong private token, when the real loopback handshake fails, then CLI emits only a public reason."""
    runner = SilentRunner()
    with local_server(runner) as url:
        path = config_file(tmp_path, url, token="synthetic-wrong-token")
        previous = logging.root.manager.disable
        assert web.main(["busy", "--config-file", str(path), "--seconds", ".1"]) == 1
        assert logging.root.manager.disable == previous
    output = capsys.readouterr()
    assert json.loads(output.out) == {"ok": False, "reason": "web_handshake_rejected"}
    assert not output.err
    for value in (TOKEN, "synthetic-wrong-token", str(path)):
        assert value not in output.out
    assert not runner.session_ids


@pytest.mark.parametrize("seconds", [0, -1, 61, float("nan"), float("inf")])
def test_voic_ops_008_web_invalid_duration_never_connects(tmp_path, seconds):
    """Given invalid hold limits, when invoked, then validation rejects before opening a socket."""
    config = web.Config.load(config_file(tmp_path, "http://127.0.0.1:8000"))
    with pytest.raises(web.ProbeError, match="invalid_web_duration"):
        web.run("hold", config, seconds, connector=lambda *args, **kwargs: pytest.fail("unexpected connection"))


@pytest.mark.parametrize("command", [
    ["tests/integrations/ht813/m10_web_probe.py", "--help"],
    ["-m", "tests.integrations.ht813.m10_web_probe", "--help"],
])
def test_voic_ops_008_web_direct_and_package_import_without_network(command):
    """Given either supported invocation style, when help is requested, then shared config imports successfully without network."""
    completed = subprocess.run([sys.executable, *command], capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0
    assert "hold" in completed.stdout and "busy" in completed.stdout
    assert not completed.stderr


def test_voic_ops_008_web_immediate_metadata_is_flushed(capsys, monkeypatch):
    """Given a readiness event, when emitted, then JSON is flushed and contains only its boolean."""
    calls = []
    monkeypatch.setattr("builtins.print", lambda value, **kwargs: calls.append((value, kwargs)))
    web.emit_metadata({"session_started": True})
    assert calls == [('{"session_started": true}', {"flush": True})]


def test_voic_ops_008_web_coalesced_busy_and_close_is_acknowledged(tmp_path):
    """Given started/busy/close in one TCP read, when cleanup runs, then queued close is acknowledged without sending invalid cancel."""
    from wsproto import ConnectionType, WSConnection
    from wsproto.events import AcceptConnection, CloseConnection, Request, TextMessage

    class CoalescedPeer:
        def __init__(self):
            self.connection = WSConnection(ConnectionType.SERVER)
            self.pending = b""
            self.commands = []
            self.closed = False

        def sendall(self, data):
            self.connection.receive_data(data)
            for event in self.connection.events():
                if isinstance(event, Request):
                    assert event.target == "/voice"
                    assert event.subprotocols == ["voice-agent", "token." + TOKEN]
                    self.pending += self.connection.send(AcceptConnection(subprotocol="voice-agent"))
                elif isinstance(event, TextMessage):
                    command = json.loads(event.data)
                    self.commands.append(command)
                    assert command == {"type": "start"}
                    for payload in ({"type": "started", "session_id": "00000000-0000-0000-0000-000000000001"},
                                    {"type": "error", "code": "busy"}):
                        self.pending += self.connection.send(TextMessage(data=json.dumps(payload)))
                    self.pending += self.connection.send(CloseConnection(code=1000))
                else:
                    assert isinstance(event, CloseConnection)

        def recv(self, size):
            assert self.pending
            data, self.pending = self.pending[:size], self.pending[size:]
            return data

        def settimeout(self, seconds):
            pass

        def close(self):
            self.closed = True

    config = web.Config.load(config_file(tmp_path, "http://127.0.0.1:8000"))
    peer = CoalescedPeer()
    result = web.run("busy", config, 1, connector=lambda *args, **kwargs: peer)
    assert result["ok"] and result["busy"] and result["close_acknowledged"]
    assert not result["cancel_sent"]
    assert peer.commands == [{"type": "start"}] and peer.closed
