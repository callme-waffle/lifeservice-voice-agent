"""VOIC-FEAT-001 M6-S2: PRD-02/06, SRS-T06/C05 external same-call context boundary."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from voice_agent.adapters.task.openai_compatible import OpenAICompatibleTask
from voice_agent.contracts.flow import CancellationToken
from voice_agent.contracts.session import Channel, ConversationTurn, SessionContext


ROOT = Path(__file__).resolve().parents[3]
FIELDS = {"VOICE_AGENT_TASK_MODEL", "VOICE_AGENT_TASK_API_KEY", "VOICE_AGENT_TASK_API_BASE_URL", "VOICE_AGENT_TASK_APPROVED_HOST"}


def private_task_settings() -> dict[str, str]:
    """Read the user-approved runtime fields without executing or echoing .env content."""
    found: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key not in FIELDS:
            continue
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[key] = value
    assert found.get("VOICE_AGENT_TASK_MODEL")
    assert found.get("VOICE_AGENT_TASK_API_KEY")
    assert found.get("VOICE_AGENT_TASK_APPROVED_HOST")
    return found


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s2_real_api_accepts_one_same_call_context_request():
    """Given synthetic final turns, when one authenticated request reaches the approved API, then it accepts ordered same-call context without retry."""
    settings = private_task_settings()
    requests = 0

    async def count_request(request: httpx.Request) -> None:
        nonlocal requests
        requests += 1
        assert request.url.host == settings["VOICE_AGENT_TASK_APPROVED_HOST"]
        assert request.url.path == "/v1/chat/completions"
        assert request.headers.get("authorization", "").startswith("Bearer ")

    context = SessionContext(uuid4(), Channel.HT813_FXO, datetime.now(timezone.utc))
    started = time.monotonic()
    async with httpx.AsyncClient(event_hooks={"request": [count_request]}) as client:
        adapter = OpenAICompatibleTask(
            base_url=settings["VOICE_AGENT_TASK_API_BASE_URL"],
            approved_host=settings["VOICE_AGENT_TASK_APPROVED_HOST"],
            model=settings["VOICE_AGENT_TASK_MODEL"],
            api_key=settings["VOICE_AGENT_TASK_API_KEY"],
            timeout_s=60,
            client=client,
        )
        result = await adapter.process(
            "두 번째 합성 질문입니다.", context, CancellationToken(),
            history=(ConversationTurn("첫 번째 합성 질문입니다.", "첫 번째 합성 답변입니다."),),
        )
    assert requests == 1
    assert result.text.strip()
    print(f"same_call_context_requests={requests} elapsed_seconds={time.monotonic() - started:.3f}")
