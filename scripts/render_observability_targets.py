"""Render local Prometheus file discovery targets from an untracked environment file."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


PORTS = {
    "voice-backend": 8001,
    "voice-stt": 8103,
    "voice-tts": 8104,
    "voice-gpu": 9400,
}


def read_host(env_file: Path) -> str:
    """Read only the target address; never execute shell content or display it."""
    host = ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "VOICE_AGENT_GPU_HOST":
            host = value.strip().strip('"\'')
    ipaddress.ip_address(host)
    return host


def render(env_file: Path, output_dir: Path) -> None:
    host = read_host(env_file)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for job, port in PORTS.items():
        payload = json.dumps([{"targets": [f"{host}:{port}"]}], separators=(",", ":"))
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir,
                                prefix=f".{job}-", delete=False) as temporary:
            os.chmod(temporary.name, 0o600)
            temporary.write(payload)
            temporary.write("\n")
            temporary_name = temporary.name
        os.replace(temporary_name, output_dir / f"{job}.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("deploy/observability/targets"))
    args = parser.parse_args()
    render(args.env_file, args.output_dir)
