"""VOIC-OPS-008 M10; PRD-02/06/07/08/09, SRS-T01/O04/O11/O12.

Only MockTransport, synthetic secrets and private tmp_path files are used.
No real network, operator API, device, call, or operational data is accessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import logging
from pathlib import Path
import sys
from uuid import UUID

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location("m10_probe_under_test", Path(__file__).with_name("m10_probe.py"))
probe_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe_module
SPEC.loader.exec_module(probe_module)
Config, Probe, ProbeError, State = (probe_module.Config, probe_module.Probe,
                                  probe_module.ProbeError, probe_module.State)
SID_A = str(UUID(int=1))
SID_B = str(UUID(int=2))
TOKEN = "synthetic-private-token"
NUMBER = "12345"


def private_file(path: Path, value: str) -> Path:
    path.write_text(value)
    path.chmod(0o600)
    return path


def setup_config(tmp_path: Path, *, url="http://127.0.0.1:8000"):
    raw = {"base_url": url,
           "token_file": str(private_file(tmp_path / "token", TOKEN)),
           "number_file": str(private_file(tmp_path / "number", NUMBER)),
           "state_file": str(private_file(tmp_path / "state.json", "{}"))}
    config_file = private_file(tmp_path / "config.json", json.dumps(raw))
    return config_file, raw


class Clock:
    def __init__(self):
        self.now = 0.0
        self.on_sleep = lambda: None

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.on_sleep()


@pytest.mark.parametrize("url", ["http://192.0.2.1:8000", "http://localhost:8000",
                                "http://127.0.0.1:8000@192.0.2.1", "https://127.0.0.1:8000",
                                "http://127.0.0.1:8000/path", "http://127.0.0.1:8000?token=secret"])
def test_voic_ops_008_probe_rejects_nonliteral_or_unsafe_origin(tmp_path, url):
    """Given an unsafe origin, when loading config, then no HTTP client can be used."""
    path, _ = setup_config(tmp_path, url=url)
    with pytest.raises(ProbeError, match="invalid_base_url"):
        Config.load(path)


@pytest.mark.parametrize("which", ["config", "token_file", "number_file", "state_file"])
def test_voic_ops_008_probe_requires_private_files(tmp_path, which):
    """Given any broadly readable control file, when loaded, then reject before HTTP."""
    path, raw = setup_config(tmp_path)
    (path if which == "config" else Path(raw[which])).chmod(0o644)
    with pytest.raises(ProbeError, match="unsafe_file"):
        Config.load(path)


def test_voic_ops_008_probe_rejects_symlink_and_broad_directory(tmp_path):
    """Given a symlink or shared directory, when loaded, then secrets remain unread."""
    path, raw = setup_config(tmp_path)
    token = Path(raw["token_file"])
    target = token.with_name("real-token")
    token.rename(target)
    token.symlink_to(target)
    with pytest.raises(ProbeError, match="unsafe_file"):
        Config.load(path)
    token.unlink()
    target.rename(token)
    tmp_path.chmod(0o755)
    try:
        with pytest.raises(ProbeError, match="unsafe_directory"):
            Config.load(path)
    finally:
        tmp_path.chmod(0o700)


def test_voic_ops_008_probe_preflight_has_no_auth_on_negative_check(tmp_path):
    """Given a ready loopback app, when preflight runs, then health200 and unauth401 are checked."""
    path, _ = setup_config(tmp_path)
    seen = []

    def handler(request):
        seen.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"status": "ready"}) if request.url.path == "/health" else httpx.Response(401)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert Probe(Config.load(path), client).preflight()["ok"]
    assert len(seen) == 2 and all(item.method == "GET" for item in seen)


def test_voic_ops_008_probe_consumes_before_post_and_rejects_reuse(tmp_path):
    """Given one approval, when an attempt completes, then case and approval cannot POST again."""
    path, _ = setup_config(tmp_path)
    config = Config.load(path)
    posts = []

    def handler(request):
        if request.method == "POST":
            persisted = State(config.state_file).read()["F02"]
            assert persisted["consumed"] and persisted["approval_id"] == "reply-1"
            assert persisted["session_id"] is None
            posts.append(request)
            return httpx.Response(202, json={"session_id": SID_A})
        return httpx.Response(200, json={"session_id": SID_A, "status": "ended"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe = Probe(config, client)
        probe.dial("F02", "reply-1", 30)
        for case, approval in (("F02", "reply-2"), ("C", "reply-1")):
            with pytest.raises(ProbeError, match="attempt_already_consumed"):
                probe.dial(case, approval, 30)
    assert len(posts) == 1
    persisted = json.loads(config.state_file.read_text())
    assert set(persisted["F02"]) == probe_module.FIELDS
    assert config.state_file.stat().st_mode & 0o777 == 0o600
    assert NUMBER not in config.state_file.read_text() and TOKEN not in config.state_file.read_text()


def test_voic_ops_008_probe_concurrent_consumption_is_single(tmp_path):
    """Given two contenders for one approval, when locked consumption races, then exactly one succeeds."""
    path, _ = setup_config(tmp_path)
    config = Config.load(path)

    def consume(case):
        try:
            State(config.state_file).consume(case, "shared-reply")
            return True
        except ProbeError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, ["F02", "C"]))
    assert sorted(results) == [False, True]
    assert len(State(config.state_file).read()) == 1


@pytest.mark.parametrize("confirmed,max_seconds,reason,elapsed", [
    (False, 240, "ring_timeout", 15), (True, 4, "occupancy_timeout", 4),
])
def test_voic_ops_008_probe_watchdog_cancels_even_active(tmp_path, confirmed, max_seconds, reason, elapsed):
    """Given active SIP state, when no bell or occupancy deadline expires, then one DELETE occurs."""
    path, _ = setup_config(tmp_path)
    clock, requests = Clock(), []
    config = Config.load(path)
    if confirmed:
        clock.on_sleep = lambda: State(config.state_file).confirm_ring("F02")

    def handler(request):
        requests.append(request)
        if request.method in {"POST", "DELETE"}:
            return httpx.Response(202, json={"session_id": SID_A})
        return httpx.Response(200, json={"session_id": SID_A, "status": "active"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Probe(config, client, clock=clock.monotonic, sleep=clock.sleep).dial("F02", "reply-1", max_seconds)
    assert not result["ok"] and result["reason"] == reason
    assert result["cancel_requested"] and not result["shutdown_required"]
    assert clock.now == elapsed
    assert sum(item.method == "POST" for item in requests) == 1
    assert sum(item.method == "DELETE" for item in requests) == 1
    assert all(item.url.host == "127.0.0.1" for item in requests)


def test_voic_ops_008_probe_lost_post_response_is_not_retried(tmp_path):
    """Given a lost POST response, when dial fails, then shutdown is required and the attempt stays consumed."""
    path, _ = setup_config(tmp_path)
    config, requests = Config.load(path), []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("synthetic secret " + TOKEN, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe = Probe(config, client)
        result = probe.dial("F02", "reply-1", 30)
        assert result == {"ok": False, "case": "F02", "reason": "dial_ambiguous", "shutdown_required": True}
        with pytest.raises(ProbeError, match="attempt_already_consumed"):
            probe.dial("F02", "reply-2", 30)
    assert len(requests) == 1 and requests[0].method == "POST"
    assert TOKEN not in json.dumps(result)
    assert State(config.state_file).read()["F02"]["consumed"]


def test_voic_ops_008_probe_reject_dial_uses_only_disallowed_synthetic_inputs(tmp_path):
    """Given one approved number, when negative cases run, then only distinct synthetic/code inputs POST once."""
    path, _ = setup_config(tmp_path)
    numbers = []

    def handler(request):
        number = json.loads(request.content)["number"]
        numbers.append(number)
        return httpx.Response(403 if number.isdigit() else 422)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert Probe(Config.load(path), client).reject_dial()["ok"]
    assert len(numbers[0]) == 5 and numbers[0] != NUMBER
    assert numbers[1:] == ["*00", "#"]


@pytest.mark.parametrize("has_id", [True, False])
def test_voic_ops_008_probe_unexpected_reject_acceptance_recovers_or_requests_shutdown(tmp_path, has_id):
    """Given an unexpectedly accepted negative test, when 202 arrives, then cancel its known ID or request shutdown."""
    path, _ = setup_config(tmp_path)
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(202, json={"session_id": SID_A} if has_id else {})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Probe(Config.load(path), client).reject_dial()
    assert not result["ok"]
    assert result["shutdown_required"] is not has_id
    assert methods == (["POST", "DELETE"] if has_id else ["POST"])


def test_voic_ops_008_probe_redirect_does_not_escape_loopback(tmp_path):
    """Given a redirect, when preflight reads it, then the external destination is never requested."""
    path, _ = setup_config(tmp_path)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://example.invalid/"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        assert not Probe(Config.load(path), client).preflight()["ok"]
    assert hosts == ["127.0.0.1", "127.0.0.1"]


def test_voic_ops_008_probe_history_reports_metadata_only(tmp_path):
    """Given two distinct phone IDs and private text, when histories are checked, then output/state contain no content."""
    path, _ = setup_config(tmp_path)
    config = Config.load(path)
    state = State(config.state_file)
    for case, sid in (("F02", SID_A), ("F03", SID_B)):
        state.consume(case, "reply-1" if case == "F02" else "")
        state.update(case, session_id=sid, status="ended")

    def handler(request):
        sid = request.url.path.split("/")[3]
        return httpx.Response(200, json={"session_id": sid, "turns": [
            {"turn_index": turn, "speaker": speaker, "text": f"PRIVATE {sid} {TOKEN} {NUMBER}",
             "created_at": f"2026-10-16T14:00:0{turn}+00:00"}
            for turn in (0, 1) for speaker in ("user", "assistant")
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Probe(config, client).history(["F02", "F03"])
    assert result["ok"] and result["distinct_case_ids"] and result["content_comparison_required"]
    assert all(item["same_id"] and item["ordered"] and item["two_complete_turns"] for item in result["cases"])
    for forbidden in ("PRIVATE", TOKEN, NUMBER, SID_A, SID_B):
        assert forbidden not in json.dumps(result)
    assert "PRIVATE" not in config.state_file.read_text()


@pytest.mark.parametrize("malformation", ["wrong_id", "reversed", "one_pair"])
def test_voic_ops_008_probe_history_rejects_mismatch_order_and_insufficient_turns(tmp_path, malformation):
    """Given mismatched identity/order/count, when querying, then metadata verdict is false."""
    path, _ = setup_config(tmp_path)
    config = Config.load(path)
    state = State(config.state_file)
    state.consume("F02", "reply-1")
    state.update("F02", session_id=SID_A, status="ended")
    turns = [{"turn_index": turn, "speaker": speaker, "text": "private",
              "created_at": "2026-10-16T14:00:00+00:00"}
             for turn in (0, 1) for speaker in ("user", "assistant")]
    if malformation == "reversed":
        turns.reverse()
    if malformation == "one_pair":
        turns = turns[:2]
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "session_id": SID_B if malformation == "wrong_id" else SID_A, "turns": turns,
    }))) as client:
        assert not Probe(config, client).history(["F02"])["ok"]


@pytest.mark.parametrize("multiple", [False, True])
def test_voic_ops_008_probe_observe_requires_one_new_id(tmp_path, multiple):
    """Given an inbound baseline, when arrivals are observed, then bind one new ID and reject ambiguity."""
    path, _ = setup_config(tmp_path)
    config, clock = Config.load(path), Clock()
    calls = []

    def handler(request):
        calls.append(request)
        ids = [] if len(calls) == 1 else ([SID_A, SID_B] if multiple else [SID_A])
        return httpx.Response(200, json={"items": [{"session_id": sid, "caller_number": "PRIVATE"} for sid in ids],
                                        "next_offset": None})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe = Probe(config, client, clock=clock.monotonic, sleep=clock.sleep)
        if multiple:
            with pytest.raises(ProbeError, match="ambiguous_inbound"):
                probe.observe("F03")
        else:
            result = probe.observe("F03")
            assert result["ok"] and result["new_id_bound"]
            assert SID_A not in json.dumps(result)
            assert State(config.state_file).read()["F03"]["session_id"] == SID_A
    assert "PRIVATE" not in config.state_file.read_text()


def test_voic_ops_008_probe_argument_errors_never_echo_inputs(capsys):
    """Given invalid CLI arguments carrying secret text, when parsed, then stderr/stdout redact input."""
    previous = logging.root.manager.disable
    assert probe_module.main([TOKEN]) == 1
    assert logging.root.manager.disable == previous
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert json.loads(output.out)["reason"] == "invalid_arguments"



def test_voic_ops_008_probe_late_confirmation_cannot_release_watchdog(tmp_path):
    """Given bell confirmation arriving after 15 seconds, when checked, then it cannot suppress cancellation."""
    path, _ = setup_config(tmp_path)
    config, clock = Config.load(path), Clock()
    methods = []

    def sleep(seconds):
        clock.now += seconds
        if clock.now == 15:
            State(config.state_file).confirm_ring("F02")

    def handler(request):
        methods.append(request.method)
        return httpx.Response(202 if request.method != "GET" else 200,
                              json={"session_id": SID_A, "status": "active"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Probe(config, client, clock=clock.monotonic, sleep=sleep).dial("F02", "reply-1", 30)
    assert result["reason"] == "ring_timeout" and methods.count("DELETE") == 1


def test_voic_ops_008_probe_external_cancel_survives_inflight_status(tmp_path):
    """Given cancel during a status GET, when its stale active reply returns, then cancellation stays recorded."""
    path, _ = setup_config(tmp_path)
    config, clock = Config.load(path), Clock()
    requests = []
    probe = None

    def handler(request):
        requests.append(request.method)
        if request.method == "GET":
            probe.cancel("F02")
        return httpx.Response(200 if request.method == "GET" else 202,
                              json={"session_id": SID_A, "status": "active"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe = Probe(config, client, clock=clock.monotonic, sleep=clock.sleep)
        result = probe.dial("F02", "reply-1", 30)
    assert result["reason"] == "operator_cancelled"
    assert requests == ["POST", "GET", "DELETE"]
    assert State(config.state_file).read()["F02"]["status"] == "cancel_requested"


def test_voic_ops_008_probe_confirmed_bell_and_remote_end_succeed(tmp_path):
    """Given explicit timely bell confirmation, when the same call ends, then no synthetic timeout/cancel occurs."""
    path, _ = setup_config(tmp_path)
    config, clock = Config.load(path), Clock()
    requests = []
    clock.on_sleep = lambda: State(config.state_file).confirm_ring("F02")

    def handler(request):
        requests.append(request.method)
        return httpx.Response(202 if request.method == "POST" else 200, json={
            "session_id": SID_A, "status": "ended" if clock.now >= 2 else "active",
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Probe(config, client, clock=clock.monotonic, sleep=clock.sleep).dial("F02", "reply-1", 30)
    assert result["ok"] and result["ring_confirmed"] and result["status"] == "ended"
    assert requests.count("POST") == 1 and "DELETE" not in requests


@pytest.mark.parametrize("seconds", [0, -1, 241, float("nan"), float("inf")])
def test_voic_ops_008_probe_invalid_deadline_does_not_consume_or_post(tmp_path, seconds):
    """Given a nonpositive/nonfinite/excessive bound, when dial is requested, then no attempt or HTTP is made."""
    path, _ = setup_config(tmp_path)
    config = Config.load(path)
    requests = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request))) as client:
        with pytest.raises(ProbeError, match="invalid_duration"):
            Probe(config, client).dial("F02", "reply-1", seconds)
    assert not requests and State(config.state_file).read() == {}
