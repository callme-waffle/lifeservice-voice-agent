"""VOIC-FEAT-001 M6-S2: PRD-01/05/06, SRS-W01/W02/W03/O02 browser/API boundary."""

from __future__ import annotations

import audioop
import base64
import json
import os
import secrets
import shlex
import subprocess
import time
import urllib.request
import wave
from urllib.parse import urlparse
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
REMOTE_ROOT = "/tmp/voice-agent-m6-web-bd66c29"


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


def remote(script: str, *, timeout: int = 30) -> str:
    completed = subprocess.run(
        SSH + ["python3 -c " + shlex.quote(script)], capture_output=True, text=True,
        timeout=timeout, check=True,
    )
    return completed.stdout.strip()


def private_env() -> dict[str, str]:
    """Read only the approved task fields without echoing values or sourcing shell code."""
    result: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in {"VOICE_AGENT_TASK_MODEL", "VOICE_AGENT_TASK_API_KEY",
                   "VOICE_AGENT_TASK_API_BASE_URL", "VOICE_AGENT_TASK_APPROVED_HOST"}:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            result[key] = value
    assert result.get("VOICE_AGENT_TASK_MODEL")
    assert result.get("VOICE_AGENT_TASK_API_KEY")
    assert urlparse(result["VOICE_AGENT_TASK_API_BASE_URL"]).hostname == result["VOICE_AGENT_TASK_APPROVED_HOST"]
    return result


def pcm16k(source: Path, destination: Path) -> None:
    with wave.open(str(source), "rb") as sound:
        assert sound.getnchannels() == 1 and sound.getsampwidth() == 2
        source_rate = sound.getframerate()
        pcm = sound.readframes(sound.getnframes())
    converted, _ = audioop.ratecv(pcm, 2, 1, source_rate, 16_000, None)
    assert converted and len(converted) % 2 == 0
    destination.write_bytes(converted)


def stop_remote() -> None:
    script = f"""
import os, pathlib, shutil, signal
for entry in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        args = (entry / 'cmdline').read_bytes().split(b'\\0')
        if b'uvicorn' in args and b'voice_agent.main:app' in args:
            os.kill(int(entry.name), signal.SIGTERM)
    except (OSError, ValueError):
        pass
shutil.rmtree({REMOTE_ROOT!r}, ignore_errors=True)
"""
    remote(script)


def test_voic_feat_001_m6_s2_real_chrome_gpu_task_api_one_request():
    """Given synthetic Korean speech, when Chrome sends it, then one authenticated session returns text/audio and frees the slot."""
    task = private_env()
    with TemporaryDirectory(prefix="voic-m6-web-", dir="/tmp") as temporary:
        directory = Path(temporary)
        pcm_file = directory / "synthetic.pcm"
        pcm16k(Path("/tmp/voice-agent-m4-tts-speed125-short.wav"), pcm_file)
        runtime = {
            **task,
            "VOICE_AGENT_WEB_ACCESS_TOKEN": secrets.token_urlsafe(32),
            "VOICE_AGENT_DATA_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
            "VOICE_AGENT_STT_MODEL_ID": "small",
            "VOICE_AGENT_TTS_SPEED": "1.25",
            "VOICE_AGENT_API_HOST": "127.0.0.1",
            "VOICE_AGENT_API_PORT": "18080",
            "VOICE_AGENT_HT813_ALLOWED_EXACT": "",
            "VOICE_AGENT_HT813_ALLOWED_PREFIXES": "",
            "VOICE_AGENT_HT813_INBOUND_ENABLED": "false",
            "VOICE_AGENT_RECORDINGS_DIR": REMOTE_ROOT + "/data/recordings",
            "VOICE_AGENT_TRANSCRIPTS_DIR": REMOTE_ROOT + "/data/transcripts",
            "VOICE_AGENT_DELETION_AUDIT_LOG": REMOTE_ROOT + "/data/deletion-audit.jsonl",
        }
        launcher = f"""
import glob, json, os, sys
settings = json.loads(sys.stdin.readline())
os.environ.update(settings)
os.environ['PYTHONPATH'] = {REMOTE_ROOT!r} + ':' + {REMOTE_ROOT!r} + '/vendor'
os.environ['LD_LIBRARY_PATH'] = ':'.join(sorted(glob.glob({REMOTE_VENV!r} + '/lib/python3.11/site-packages/nvidia/*/lib')))
os.execv({REMOTE_VENV!r} + '/bin/python', [
    {REMOTE_VENV!r} + '/bin/python', '-m', 'uvicorn', 'voice_agent.main:app',
    '--host', '127.0.0.1', '--port', '18080', '--no-access-log',
])
"""
        server = None
        tunnel = None
        chrome = None
        monitor = None
        outcome: dict[str, object] = {}
        started = time.monotonic()
        try:
            remote(f"from pathlib import Path; Path({REMOTE_ROOT!r}).mkdir(mode=0o700, exist_ok=True)")
            subprocess.run(
                SSH + [shlex.quote(REMOTE_VENV + "/bin/python")
                       + " -m pip install --disable-pip-version-check --no-input --no-deps"
                       + " --target " + shlex.quote(REMOTE_ROOT + "/vendor")
                       + " 'wsproto>=1.2,<2'"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60,
            )
            subprocess.run(
                SCP + [str(ROOT / "apps/orchestrator/src/voice_agent"),
                       REMOTE_TARGET + ":" + REMOTE_ROOT + "/"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60,
            )
            server = subprocess.Popen(
                SSH + ["python3 -u -c " + shlex.quote(launcher)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True,
            )
            assert server.stdin is not None
            server.stdin.write(json.dumps(runtime) + "\n")
            server.stdin.close()
            tunnel = subprocess.Popen(
                SSH[:-1] + ["-N", "-L", "127.0.0.1:18000:127.0.0.1:18080", SSH[-1]],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            ready = False
            for _ in range(100):
                if server.poll() is not None or tunnel.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18000/health", timeout=1) as response:
                        ready = json.load(response)["status"] == "ready"
                    if ready:
                        break
                except (OSError, ValueError):
                    time.sleep(0.3)
            assert ready, "remote application did not reach health ready"

            monitor_script = f"""
import json, pathlib, time
minimum_available = 10**15
maximum_swap = 0
maximum_rss = 0
samples = 0
stop = pathlib.Path({(REMOTE_ROOT + '/monitor.stop')!r})
while not stop.exists() and samples < 600:
    values = {{}}
    for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
        name, rest = line.split(':', 1)
        if name in ('MemAvailable', 'SwapTotal', 'SwapFree'):
            values[name] = int(rest.split()[0])
    minimum_available = min(minimum_available, values['MemAvailable'])
    maximum_swap = max(maximum_swap, values['SwapTotal'] - values['SwapFree'])
    for entry in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\\0')
            if b'uvicorn' in args and b'voice_agent.main:app' in args:
                for line in (entry / 'status').read_text().splitlines():
                    if line.startswith('VmRSS:'):
                        maximum_rss = max(maximum_rss, int(line.split()[1]))
        except (OSError, ValueError):
            pass
    samples += 1
    time.sleep(.5)
print(json.dumps({{'samples': samples, 'minimumAvailableKiB': minimum_available,
                  'maximumSwapUsedKiB': maximum_swap, 'maximumAppRssKiB': maximum_rss}}))
"""
            monitor = subprocess.Popen(
                SSH + ["python3 -u -c " + shlex.quote(monitor_script)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True,
            )
            chrome = subprocess.Popen([
                "/home/codex/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",
                "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-background-networking", "--disable-extensions", "--no-first-run",
                "--remote-debugging-port=19222", "--remote-allow-origins=*",
                "--user-data-dir=" + str(directory / "chrome"), "about:blank",
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(150):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:19222/json/list", timeout=1) as response:
                        if json.load(response):
                            break
                except (OSError, ValueError):
                    time.sleep(0.4)
            else:
                raise AssertionError("Chrome DevTools unavailable")
            probe_env = os.environ.copy()
            probe_env["VOICE_AGENT_WEB_ACCESS_TOKEN"] = runtime["VOICE_AGENT_WEB_ACCESS_TOKEN"]
            completed = subprocess.run(
                ["node", str(Path(__file__).with_name("browser_probe.js")), str(pcm_file)],
                env=probe_env, capture_output=True, text=True, timeout=220,
            )
            assert completed.returncode == 0, "browser probe failed before a result"
            outcome = json.loads(completed.stdout)
            assert outcome["rejected"] is True
            result = outcome["result"]
            assert result["opened"] and result["sessionMatch"]
            assert result["transcripts"] == 1 and result["taskResults"] == 1
            assert result["audioChunks"] > 0 and result["audioBytes"] > 0
            assert result["audioContiguous"]
            assert result["statuses"] == ["starting", "listening", "processing", "speaking", "completed"]
            assert outcome["afterCancel"]["started"] and "cancelled" in outcome["afterCancel"]["statuses"]
            assert outcome["nextSession"]["started"] and "cancelled" in outcome["nextSession"]["statuses"]
            count = remote(f"""
from pathlib import Path
root = Path({REMOTE_ROOT!r}) / 'data'
files = list(root.glob('recordings/*.va1')) + list(root.glob('transcripts/*.va1'))
print(len(files))
""")
            assert int(count) == 4
        finally:
            try:
                remote(f"from pathlib import Path; Path({(REMOTE_ROOT + '/monitor.stop')!r}).touch()")
                if monitor is not None:
                    output, _ = monitor.communicate(timeout=8)
                    if output.strip():
                        outcome["memory"] = json.loads(output)
            finally:
                for process in (chrome, tunnel, server, monitor):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                stop_remote()
        result = outcome["result"]
        print(json.dumps({
            "browser": "Chrome for Testing 153",
            "unauthorizedRejected": outcome["rejected"],
            "inputChunks": result["inputChunks"],
            "finalTranscriptCount": result["transcripts"],
            "taskResultCount": result["taskResults"],
            "outputChunks": result["audioChunks"],
            "outputBytes": result["audioBytes"],
            "statuses": result["statuses"],
            "timesMs": result["timesMs"],
            "memory": outcome.get("memory"),
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False))
