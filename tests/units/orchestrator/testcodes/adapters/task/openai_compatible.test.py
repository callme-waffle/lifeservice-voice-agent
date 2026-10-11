"""VOIC-FEAT-001 M5-S3: fake HTTP success, auth failure, timeout, secret hygiene."""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from voice_agent.adapters.task.openai_compatible import OpenAICompatibleTask, TaskBackendError
from voice_agent.contracts.flow import CancellationToken
from voice_agent.contracts.session import Channel, SessionContext, TaskResult


def context():
    return SessionContext(uuid4(), Channel.WEB, datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s3_sends_only_final_text_to_approved_url():
    """Given text, when processed, then only chat user content and Bearer token leave."""
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "완료"}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAICompatibleTask(base_url="https://llm.example.test", approved_host="llm.example.test", model="configured-model",
                                       api_key="private-test-token", client=client)
        result = await adapter.process("요청", context(), CancellationToken())
    assert result == TaskResult("완료")
    assert str(requests[0].url) == "https://llm.example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer private-test-token"
    assert requests[0].read().decode() == (
        '{"model":"configured-model","messages":[{"role":"user","content":"요청"}],"stream":false}'
    )


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s3_auth_failure_sanitizes_secret():
    """Given 401 with secret in body, when handled, then exception reveals no secret."""
    def respond(request):
        return httpx.Response(401, text="private-test-token denied")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAICompatibleTask(base_url="https://llm.example.test/v1", approved_host="llm.example.test", model="model",
                                       api_key="private-test-token", client=client)
        with pytest.raises(TaskBackendError) as raised:
            await adapter.process("요청", context(), CancellationToken())
    assert "private-test-token" not in str(raised.value)
    assert "authentication" in str(raised.value)


@pytest.mark.asyncio
async def test_voic_feat_001_m5_s3_timeout_is_sanitized():
    """Given HTTP timeout, when handled, then a stable backend error reaches core."""
    def timeout(request):
        raise httpx.ReadTimeout("private-test-token", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        adapter = OpenAICompatibleTask(base_url="https://llm.example.test", approved_host="llm.example.test", model="model",
                                       api_key="private-test-token", client=client)
        with pytest.raises(TaskBackendError) as raised:
            await adapter.process("요청", context(), CancellationToken())
    assert str(raised.value) == "task backend timed out"


def test_voic_feat_001_m5_s3_rejects_unapproved_origin():
    """Given different host or cleartext URL, when configured, then token cannot be sent."""
    for url in ("http://llm.example.test", "https://example.com", "https://llm.example.test/other"):
        with pytest.raises(ValueError):
            OpenAICompatibleTask(base_url=url, approved_host="llm.example.test", model="model", api_key="private-test-token")


@pytest.mark.asyncio
async def test_voic_feat_001_m6_s1_t3_sends_only_same_call_final_turns():
    """Given prior final turns, when queried, then ordered messages contain those turns only."""
    import json
    from voice_agent.contracts.session import ConversationTurn

    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "최종"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAICompatibleTask(base_url="https://llm.example.test", approved_host="llm.example.test", model="configured-model",
                                       api_key="private-test-token", client=client)
        result = await adapter.process(
            "질문2", context(), CancellationToken(),
            history=(ConversationTurn("질문1", "답변1"),),
        )
    assert result == TaskResult("최종")
    assert json.loads(requests[0].read())["messages"] == [
        {"role": "user", "content": "질문1"},
        {"role": "assistant", "content": "답변1"},
        {"role": "user", "content": "질문2"},
    ]
    assert requests[0].headers["authorization"] == "Bearer private-test-token"
