"""VOIC-FEAT-001 M6-S2: PRD-02/05/06, SRS-T02/T03/T05/T06/C02/C05 real GPU phone media boundary."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def local_setting(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.strip().strip('"\'')
    raise ValueError(f"missing {key}")


REMOTE_VENV = local_setting("VOICE_AGENT_GPU_REMOTE_VENV")
REMOTE_TARGET = f"{local_setting('VOICE_AGENT_GPU_SSH_USER')}@{local_setting('VOICE_AGENT_GPU_SSH_HOST')}"
SSH_KEY = local_setting("VOICE_AGENT_GPU_SSH_KEY_PATH")
SSH = [
    "ssh", "-q", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/tmp/voic-m6-known_hosts",
    "-o", "ConnectTimeout=8", REMOTE_TARGET,
]
SCP = [
    "scp", "-q", "-r", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/tmp/voic-m6-known_hosts",
    "-o", "ConnectTimeout=8",
]


def remote(script: str, *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(SSH + ["python3 -c " + shlex.quote(script)],
                          capture_output=True, text=True, timeout=timeout, check=True)


def test_voic_feat_001_m6_s2_gpu_stt_tts_sip_two_turns_and_recovery():
    """Given synthetic Korean phone speech, when actual GPU models handle two SIP turns, then RTP output, same-call history and BYE release succeed."""
    remote_root = remote("import tempfile; print(tempfile.mkdtemp(prefix='voice-agent-m6-phone-', dir='/tmp'))").stdout.strip()
    assert remote_root.startswith("/tmp/voice-agent-m6-phone-")
    try:
        subprocess.run(SCP + [
            str(ROOT / "apps/orchestrator/src/voice_agent"),
            str(Path(__file__).with_name("phone_gpu_probe.py")),
            str(Path(__file__).with_name("fixtures") / "synthetic_ko_melo_125.wav"),
            REMOTE_TARGET + ":" + remote_root + "/",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=90)
        launcher = f"""
import glob, os
root = {remote_root!r}
os.environ['PYTHONPATH'] = root
os.environ['LD_LIBRARY_PATH'] = ':'.join(sorted(glob.glob({REMOTE_VENV!r} + '/lib/python3.11/site-packages/nvidia/*/lib')))
os.rename(root + '/synthetic_ko_melo_125.wav', root + '/synthetic.wav')
os.execv({REMOTE_VENV!r} + '/bin/python', [
    {REMOTE_VENV!r} + '/bin/python', root + '/phone_gpu_probe.py',
])
"""
        result = subprocess.run(
            SSH + ["python3 -u -c " + shlex.quote(launcher)],
            capture_output=True, text=True, timeout=360,
        )
        assert result.returncode == 0, f"GPU phone probe exited {result.returncode}"
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        assert summary["twoTurns"] == 2
        assert summary["historyLengths"] == [0, 1]
        assert summary["outputRtpPackets"] > 0
        assert len(summary["turnSecondsAfterInput"]) == 2
        print(json.dumps(summary))
    finally:
        remote(f"import shutil; shutil.rmtree({remote_root!r}, ignore_errors=True)")
