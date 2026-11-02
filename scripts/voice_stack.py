#!/usr/bin/env python3
"""Select a Compose topology without evaluating shell code or printing secrets."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def provider_from_file(path):
    provider = "onprem"
    for line in path.read_text().splitlines():
        key, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and key.strip() == "VOICE_AGENT_VOICE_PROVIDER":
            provider = value.strip().split(" #", 1)[0].strip().strip("\"'")
    return provider


def command(env_file, args):
    provider = os.environ.get("VOICE_AGENT_VOICE_PROVIDER", provider_from_file(env_file))
    if provider not in ("onprem", "openai_live"):
        raise ValueError("VOICE_AGENT_VOICE_PROVIDER must be onprem or openai_live")
    files = ["compose.live.yaml"] if provider == "openai_live" else ["compose.yaml", "compose.backend.yaml"]
    result = ["docker", "compose", "--project-name", "voice-agent-gpu", "--env-file", str(env_file)]
    for file in files:
        result += ["-f", str(ROOT / "deploy/gpu" / file)]
    return result + args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("compose_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        cmd = command(args.env_file.resolve(), args.compose_args or ["config", "--quiet"])
    except (OSError, ValueError):
        parser.error("env 파일을 읽을 수 없거나 제공자 선택값이 잘못되었습니다.")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
