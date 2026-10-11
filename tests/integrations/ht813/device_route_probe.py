"""VOIC-FEAT-001 M6-S2 prerequisite diagnostic for PRD-03, SRS-I01/I02.

Given the approved HT813 backup/change/rollback procedure and an idle FXO,
when the operator applies the temporary server specified at launch and reactivates
registration, pair device-side transmission evidence with receipt of an
unsolicited REGISTER or OPTIONS from the exact peer. Editing the server alone
is not evidence of transmission; see the M6 live runbook's corrected procedure.
Exit 0 proves only that this SIP request reached the GPU. Exit 2 means no
matching request was observed; it does not distinguish no transmission from
routing/firewall failure. This is not an application/call/RTP acceptance test.

Passive, bounded, manually launched helper: never transmits, answers a call,
challenges authentication, loads models, or logs packet contents/identifiers.
The operator must restore the original Primary SIP Server afterwards.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--bind-host", required=True)
    parser.add_argument("--peer-host", required=True)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 900:
        parser.error("seconds must be between 10 and 900")
    local = (args.bind_host, 5061)
    peer = (args.peer_host, 5062)
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc)
    next_report = started + 30
    counts = {"datagrams": 0, "peer_ip_datagrams": 0,
              "unexpected_source": 0, "unrecognized_method": 0}

    def report(state: str, **extra: object) -> None:
        print(json.dumps({"state": state,
                          "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "elapsed_s": round(time.monotonic() - started, 3),
                          **counts, "sent_packets": 0, **extra}), flush=True)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(local)
            report("listening", address=local, deadline_seconds=args.seconds,
                   deadline_utc=(started_utc + timedelta(seconds=args.seconds)).isoformat(
                       timespec="seconds"))
            while (remaining := args.seconds - (time.monotonic() - started)) > 0:
                if time.monotonic() >= next_report:
                    report("waiting")
                    next_report = time.monotonic() + 30
                sock.settimeout(min(remaining, 1.0))
                try:
                    packet, source = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                counts["datagrams"] += 1
                if source[0] == peer[0]:
                    counts["peer_ip_datagrams"] += 1
                if source != peer:
                    counts["unexpected_source"] += 1
                    continue
                first_line = packet.split(b"\r\n", 1)[0]
                match = re.fullmatch(
                    rb"(REGISTER|OPTIONS) [^\x00-\x20\x7f]{1,1024} SIP/2\.0",
                    first_line,
                )
                if match is None:
                    counts["unrecognized_method"] += 1
                    continue
                report("request_received", method=match[1].decode("ascii"), source=peer)
                return 0
    except (OSError, KeyboardInterrupt) as exc:
        report("stopped", reason=type(exc).__name__)
        return 3
    report("no_matching_request")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
