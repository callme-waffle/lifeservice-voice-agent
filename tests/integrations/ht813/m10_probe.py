"""VOIC-OPS-008 M10 local operator probe; no implicit approval or retry.

Run only within an approved execution bundle. The JSON config references existing
0600 files: base_url, token_file, number_file, state_file. number_file contains the
single approved exact destination; server allowlist equivalence remains a P0 check.
State starts as {} in a private directory. stdout contains metadata only.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import fcntl
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx


CASES = {"F02", "F02-R1", "C", "F03", "F04-A", "F04-B", "F05", "P"}
REJECT_CASES = {"F01-NUMBER", "F01-STAR", "F01-HASH"}
CALL_STATUSES = {"dialing", "ringing", "active", "busy", "failed", "ended"}
STATE_STATUSES = CALL_STATUSES | {"posting", "observing", "accepted", "cancel_requested"}
FIELDS = {"session_id", "status", "consumed", "approval_id", "ring_confirmed"}


class ProbeError(Exception):
    """Public code is fixed by the probe; never use external exception text."""

    def __init__(self, code: str, *, shutdown_required: bool = False):
        self.code, self.shutdown_required = code, shutdown_required
        super().__init__(code)


def private_parent(path: Path) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise ProbeError("unsafe_file")
    info = path.parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ProbeError("unsafe_directory")


def check_fd(fd: int) -> None:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid() or info.st_nlink != 1):
        raise ProbeError("unsafe_file")


def read_private(path: Path) -> str:
    private_parent(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            check_fd(stream.fileno())
            data = stream.read(65537)
        if len(data) > 65536:
            raise ProbeError("invalid_file")
        return data
    except (OSError, UnicodeError):
        raise ProbeError("unavailable_file") from None


def object_json(value: str) -> dict:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ProbeError("invalid_json")
            result[key] = item
        return result
    try:
        result = json.loads(value, object_pairs_hook=unique)
    except (ValueError, TypeError):
        raise ProbeError("invalid_json") from None
    if not isinstance(result, dict):
        raise ProbeError("invalid_json")
    return result


def uuid_text(value) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        return str(UUID(value))
    except ValueError:
        raise ProbeError("invalid_response") from None


def loopback_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback
                or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError
    except (ValueError, TypeError):
        raise ProbeError("invalid_base_url") from None
    return value.rstrip("/")


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str = field(repr=False)
    number: str = field(repr=False)
    state_file: Path

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = object_json(read_private(path))
        if set(raw) != {"base_url", "token_file", "number_file", "state_file"}:
            raise ProbeError("invalid_config")
        if not all(isinstance(value, str) for value in raw.values()):
            raise ProbeError("invalid_config")
        url = loopback_url(raw["base_url"])
        paths = [Path(raw[name]) for name in ("token_file", "number_file", "state_file")]
        if len({path, *paths}) != 4:
            raise ProbeError("invalid_config")
        token, number = (read_private(item).strip() for item in paths[:2])
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ProbeError("invalid_token")
        if not re.fullmatch(r"\+?[0-9]{3,15}", number):
            raise ProbeError("invalid_number")
        result = cls(url, token, number, paths[2])
        State(result.state_file).read()
        return result


class State:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def locked(self):
        private_parent(self.path)
        lock = self.path.with_name(self.path.name + ".lock")
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            check_fd(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _read(self) -> dict:
        data = object_json(read_private(self.path))
        for case, item in data.items():
            if case not in CASES | REJECT_CASES or not isinstance(item, dict) or set(item) != FIELDS:
                raise ProbeError("invalid_state")
            if (item["status"] not in STATE_STATUSES
                    or type(item["consumed"]) is not bool
                    or type(item["ring_confirmed"]) is not bool
                    or not isinstance(item["approval_id"], str)
                    or (item["approval_id"] and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", item["approval_id"]))):
                raise ProbeError("invalid_state")
            if item["session_id"] is not None:
                uuid_text(item["session_id"])
        return data

    def read(self) -> dict:
        with self.locked():
            return self._read()

    def _write(self, data: dict) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".m10-state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def consume(self, case: str, approval_id: str = "", status: str = "posting") -> None:
        if case not in CASES | REJECT_CASES:
            raise ProbeError("invalid_case")
        if case in {"F02", "F02-R1", "C"} and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", approval_id):
            raise ProbeError("approval_reference_required")
        with self.locked():
            data = self._read()
            if case in data or (approval_id and any(
                item["approval_id"] == approval_id for item in data.values()
            )):
                raise ProbeError("attempt_already_consumed")
            data[case] = {"session_id": None, "status": status, "consumed": True,
                          "approval_id": approval_id, "ring_confirmed": False}
            self._write(data)

    def update(self, case: str, **changes) -> None:
        if not set(changes) <= {"session_id", "status"}:
            raise ProbeError("invalid_state_change")
        if "session_id" in changes:
            changes["session_id"] = uuid_text(changes["session_id"])
        if "status" in changes and changes["status"] not in STATE_STATUSES:
            raise ProbeError("invalid_state_change")
        with self.locked():
            data = self._read()
            if case not in data:
                raise ProbeError("unknown_case")
            data[case].update(changes)
            self._write(data)

    def refresh_status(self, case: str, status: str) -> dict:
        """A late GET must not overwrite another CLI's cancellation."""
        if status not in CALL_STATUSES:
            raise ProbeError("invalid_status")
        with self.locked():
            data = self._read()
            item = data.get(case)
            if not item:
                raise ProbeError("unknown_case")
            if item["status"] not in {"cancel_requested", "failed", "busy", "ended"}:
                item["status"] = status
                self._write(data)
            return dict(item)

    def confirm_ring(self, case: str) -> None:
        with self.locked():
            data = self._read()
            item = data.get(case)
            if (case not in {"F02", "F02-R1", "C"} or not item or not item["session_id"]
                    or item["status"] not in {"accepted", "dialing", "ringing", "active"}):
                raise ProbeError("ring_confirmation_not_applicable")
            item["ring_confirmed"] = True
            self._write(data)


def response_object(response: httpx.Response) -> dict:
    try:
        value = response.json()
    except (ValueError, UnicodeError):
        raise ProbeError("invalid_response") from None
    if not isinstance(value, dict):
        raise ProbeError("invalid_response")
    return value


def bounded_seconds(value: float) -> float:
    if not math.isfinite(value) or not 0 < value <= 240:
        raise ProbeError("invalid_duration")
    return value


class Probe:
    def __init__(self, config: Config, client: httpx.Client, *, clock=time.monotonic, sleep=time.sleep):
        self.config, self.client = config, client
        self.state = State(config.state_file)
        self.clock, self.sleep = clock, sleep

    def request(self, method: str, path: str, *, authenticated=True, timeout_s=2, **kwargs) -> httpx.Response:
        # Absolute validated origin; never follow redirects or use env proxies.
        headers = {"Authorization": f"Bearer {self.config.token}"} if authenticated else {}
        try:
            return self.client.request(method, self.config.base_url + path,
                                       headers=headers, follow_redirects=False, timeout=timeout_s, **kwargs)
        except (httpx.HTTPError, OSError):
            raise ProbeError("network_error") from None

    def preflight(self) -> dict:
        health = self.request("GET", "/health", authenticated=False)
        denied = self.request("GET", "/operator/inbound-calls", authenticated=False)
        return {"ok": health.status_code == 200 and response_object(health).get("status") == "ready"
                and denied.status_code == 401,
                "health_status": health.status_code, "unauthorized_status": denied.status_code}

    def cancel(self, case: str) -> dict:
        item = self.state.read().get(case)
        if not item or not item["session_id"]:
            raise ProbeError("missing_call_id", shutdown_required=True)
        if item["status"] == "cancel_requested":
            return {"ok": True, "case": case, "http_status": 202,
                    "cancel_requested": True, "shutdown_required": False}
        try:
            response = self.request("DELETE", f"/operator/calls/{item['session_id']}")
        except ProbeError:
            self.state.update(case, status="failed")
            raise ProbeError("cancel_failed", shutdown_required=True) from None
        accepted = response.status_code == 202
        self.state.update(case, status="cancel_requested" if accepted else "failed")
        return {"ok": accepted, "case": case, "http_status": response.status_code,
                "cancel_requested": accepted, "shutdown_required": not accepted}

    def _abort(self, case: str, code: str) -> dict:
        try:
            result = self.cancel(case)
            result.update(ok=False, reason=code)
            return result
        except (ProbeError, OSError):
            return {"ok": False, "case": case, "reason": code, "shutdown_required": True}

    def dial(self, case: str, approval_id: str, max_seconds: float, *, confirmation_seconds: float = 15) -> dict:
        if case not in {"F02", "F02-R1", "C"}:
            raise ProbeError("invalid_case")
        max_seconds = bounded_seconds(max_seconds)
        if not math.isfinite(confirmation_seconds) or not 15 <= confirmation_seconds <= 45:
            raise ProbeError("invalid_confirmation_window")
        self.state.consume(case, approval_id)
        started = self.clock()  # Consumption is fsynced before the single POST.
        ring_seen_in_time = False
        try:
            response = self.request("POST", "/operator/calls", json={"number": self.config.number},
                                    timeout_s=min(2, max_seconds, confirmation_seconds))
            if response.status_code != 202:
                self.state.update(case, status="failed")
                return {"ok": False, "case": case, "http_status": response.status_code,
                        "reason": "dial_rejected", "shutdown_required": not 400 <= response.status_code < 500}
            sid = uuid_text(response_object(response).get("session_id"))
            self.state.update(case, session_id=sid, status="accepted")
            while True:
                item = self.state.read()[case]
                elapsed = self.clock() - started
                if elapsed < confirmation_seconds and item["ring_confirmed"]:
                    ring_seen_in_time = True
                if not ring_seen_in_time and elapsed >= confirmation_seconds:
                    return self._abort(case, "ring_timeout")
                if elapsed >= max_seconds:
                    return self._abort(case, "occupancy_timeout")
                if item["status"] == "cancel_requested":
                    return {"ok": False, "case": case, "cancel_requested": True,
                            "shutdown_required": False, "reason": "operator_cancelled"}
                remaining_deadline = min(max_seconds - elapsed,
                                         confirmation_seconds - elapsed if not ring_seen_in_time else max_seconds)
                response = self.request("GET", f"/operator/calls/{sid}",
                                        timeout_s=min(2, remaining_deadline))
                if response.status_code != 200:
                    return self._abort(case, "status_unavailable")
                body = response_object(response)
                status = body.get("status")
                if uuid_text(body.get("session_id")) != sid or status not in CALL_STATUSES:
                    return self._abort(case, "invalid_status")
                item = self.state.refresh_status(case, status)
                elapsed = self.clock() - started
                if elapsed < confirmation_seconds and item["ring_confirmed"]:
                    ring_seen_in_time = True
                if not ring_seen_in_time and elapsed >= confirmation_seconds:
                    return self._abort(case, "ring_timeout")
                if elapsed >= max_seconds:
                    return self._abort(case, "occupancy_timeout")
                if item["status"] == "cancel_requested":
                    return {"ok": False, "case": case, "cancel_requested": True,
                            "shutdown_required": False, "reason": "operator_cancelled"}
                if status in {"ended", "failed", "busy"}:
                    return {"ok": status == "ended" and ring_seen_in_time, "case": case,
                            "status": status, "ring_confirmed": ring_seen_in_time,
                            "shutdown_required": False}
                remaining = min(max_seconds - (self.clock() - started),
                                confirmation_seconds - (self.clock() - started) if not ring_seen_in_time else 1)
                self.sleep(max(0, min(1, remaining)))
        except (ProbeError, OSError, KeyboardInterrupt):
            # A lost POST response must never lead to another POST.
            return self._abort(case, "dial_ambiguous")

    def reject_dial(self) -> dict:
        synthetic = next(number for number in ("99999", "88888") if number != self.config.number)
        for case, number, expected in (("F01-NUMBER", synthetic, 403),
                                       ("F01-STAR", "*00", 422), ("F01-HASH", "#", 422)):
            self.state.consume(case)
            try:
                response = self.request("POST", "/operator/calls", json={"number": number})
                if response.status_code == 202:
                    sid = uuid_text(response_object(response).get("session_id"))
                    self.state.update(case, session_id=sid, status="accepted")
                    return self._abort(case, "unexpected_acceptance")
                self.state.update(case, status="ended" if response.status_code == expected else "failed")
                if response.status_code != expected:
                    return {"ok": False, "case": case, "http_status": response.status_code,
                            "reason": "unexpected_rejection", "shutdown_required": not 400 <= response.status_code < 500}
            except (ProbeError, OSError, KeyboardInterrupt):
                return self._abort(case, "reject_dial_ambiguous")
        return {"ok": True, "rejected_count": 3, "sip_invite_observation_required": True}

    def inbound_ids(self) -> set[str]:
        ids = set()
        offset = 0
        # Bounded full snapshot avoids mistaking older pages for a new arrival.
        for _ in range(100):
            response = self.request("GET", f"/operator/inbound-calls?limit=100&offset={offset}")
            if response.status_code != 200:
                raise ProbeError("history_unavailable")
            body = response_object(response)
            items = body.get("items")
            if not isinstance(items, list):
                raise ProbeError("invalid_response")
            for item in items:
                if not isinstance(item, dict):
                    raise ProbeError("invalid_response")
                ids.add(uuid_text(item.get("session_id")))
            following = body.get("next_offset")
            if following is None:
                return ids
            if type(following) is not int or following <= offset:
                raise ProbeError("invalid_response")
            offset = following
        raise ProbeError("history_snapshot_limit")

    def observe(self, case: str, max_seconds: float = 240) -> dict:
        if case not in {"F03", "F04-A", "F04-B", "F05", "P"}:
            raise ProbeError("invalid_case")
        bounded_seconds(max_seconds)
        baseline = self.inbound_ids()
        self.state.consume(case, status="observing")
        started = self.clock()
        while self.clock() - started < max_seconds:
            new = self.inbound_ids() - baseline
            if len(new) > 1:
                self.state.update(case, status="failed")
                raise ProbeError("ambiguous_inbound")
            if new:
                sid = new.pop()
                known = {item["session_id"] for item in self.state.read().values()}
                if sid in known:
                    raise ProbeError("duplicate_inbound")
                self.state.update(case, session_id=sid, status="accepted")
                return {"ok": True, "case": case, "new_id_bound": True,
                        "event_correlation_required": True}
            self.sleep(1)
        self.state.update(case, status="failed")
        return {"ok": False, "case": case, "reason": "observe_timeout"}

    def history(self, cases: list[str]) -> dict:
        if not cases or len(cases) != len(set(cases)) or not set(cases) <= CASES:
            raise ProbeError("invalid_case")
        state = self.state.read()
        ids = [state.get(case, {}).get("session_id") for case in cases]
        if None in ids or len(ids) != len(set(ids)):
            raise ProbeError("invalid_case_ids")
        results = []
        for case, sid in zip(cases, ids):
            response = self.request("GET", f"/operator/calls/{sid}/conversation")
            if response.status_code != 200:
                results.append({"case": case, "http_status": response.status_code, "ok": False})
                continue
            body = response_object(response)
            same_id = uuid_text(body.get("session_id")) == sid
            turns = body.get("turns")
            if not isinstance(turns, list):
                raise ProbeError("invalid_response")
            order, roles = [], {}
            for item in turns:
                if (not isinstance(item, dict) or set(item) != {"turn_index", "speaker", "text", "created_at"}
                        or type(item["turn_index"]) is not int or item["turn_index"] < 0
                        or item["speaker"] not in {"user", "assistant"}
                        or not isinstance(item["text"], str) or not item["text"].strip()):
                    raise ProbeError("invalid_response")
                try:
                    created = datetime.fromisoformat(item["created_at"])
                    if created.utcoffset() is None:
                        raise ValueError
                except (ValueError, TypeError):
                    raise ProbeError("invalid_response") from None
                order.append((item["turn_index"], created, item["speaker"] != "user"))
                roles.setdefault(item["turn_index"], []).append(item["speaker"])
            two_pairs = sum(sorted(value) == ["assistant", "user"] for value in roles.values()) >= 2
            ordered = order == sorted(order)
            results.append({"case": case, "http_status": 200, "same_id": same_id,
                            "ordered": ordered, "two_complete_turns": two_pairs,
                            "ok": same_id and ordered and two_pairs})
        return {"ok": all(item["ok"] for item in results), "distinct_case_ids": True,
                "content_comparison_required": True, "cases": results}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProbeError("invalid_arguments")


def main(argv=None) -> int:
    # HTTP debug logs can contain URLs/headers. This one-shot tool never emits them.
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        parser = SafeParser(description="M10 승인 범위의 로컬 운영 제어")
        parser.add_argument("command", choices=["preflight", "reject-dial", "dial", "cancel",
                                               "confirm-ring", "observe", "history"])
        parser.add_argument("--config-file", type=Path, required=True)
        parser.add_argument("--case")
        parser.add_argument("--approval-id")
        parser.add_argument("--max-seconds", type=float, default=240)
        parser.add_argument("--ring-confirmation-seconds", type=float, default=15)
        args = parser.parse_args(argv)
        config = Config.load(args.config_file)
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            probe = Probe(config, client)
            if args.command == "preflight":
                result = probe.preflight()
            elif args.command == "reject-dial":
                result = probe.reject_dial()
            elif args.command == "dial":
                result = probe.dial(args.case, args.approval_id or "", args.max_seconds,
                                    confirmation_seconds=args.ring_confirmation_seconds)
            elif args.command == "cancel":
                result = probe.cancel(args.case)
            elif args.command == "confirm-ring":
                probe.state.confirm_ring(args.case)
                result = {"ok": True, "case": args.case, "ring_confirmed": True}
            elif args.command == "observe":
                result = probe.observe(args.case, args.max_seconds)
            else:
                result = probe.history((args.case or "").split(","))
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["ok"] else 1
    except ProbeError as exc:
        print(json.dumps({"ok": False, "reason": exc.code, "shutdown_required": exc.shutdown_required}))
        return 1
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"ok": False, "reason": "probe_failed", "shutdown_required": True}))
        return 1
    finally:
        logging.disable(previous_logging_disable)


if __name__ == "__main__":
    raise SystemExit(main())
