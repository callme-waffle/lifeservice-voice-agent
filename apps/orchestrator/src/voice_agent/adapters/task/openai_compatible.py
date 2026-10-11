"""OpenAI-compatible chat completion task adapter (VOIC-FEAT-001 M5-S3)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from voice_agent.contracts.ports import Cancellation
from voice_agent.contracts.session import ConversationTurn, SessionContext, TaskResult


class TaskBackendError(Exception):
    """Sanitized backend failure; never contains response body or credentials."""


class OpenAICompatibleTask:
    def __init__(
        self, *, base_url: str, approved_host: str, model: str, api_key: str,
        timeout_s: float = 30.0, client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if (parsed.scheme != "https" or not approved_host or parsed.hostname != approved_host
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.path not in ("", "/", "/v1", "/v1/")
                or parsed.query or parsed.fragment):
            raise ValueError("task backend must use the configured approved HTTPS host")
        if not model.strip() or not api_key.strip():
            raise ValueError("task model and API key are required")
        if not 0 < timeout_s <= 600:
            raise ValueError("task timeout must be 0..600 seconds")
        self._url = f"https://{approved_host}/v1/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_s
        self._client = client

    async def process(
        self, text: str, context: SessionContext, cancel: Cancellation,
        *, history: tuple[ConversationTurn, ...] = (),
    ) -> TaskResult:
        if not text.strip():
            raise ValueError("task input is empty")
        cancel.raise_if_cancelled()
        messages = []
        for turn in history:
            if not isinstance(turn, ConversationTurn):
                raise TypeError("task history must contain final conversation turns")
            messages.extend((("user", turn.user_text), ("assistant", turn.assistant_text)))
        messages.append(("user", text))
        payload = {
            "model": self._model,
            "messages": [{"role": role, "content": content} for role, content in messages],
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is None:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self._url, json=payload, headers=headers, timeout=self._timeout,
                    )
            else:
                response = await self._client.post(
                    self._url, json=payload, headers=headers, timeout=self._timeout,
                )
            cancel.raise_if_cancelled()
            if response.status_code in (401, 403):
                raise TaskBackendError("task backend authentication failed")
            if response.status_code >= 400:
                raise TaskBackendError("task backend unavailable")
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError
                return TaskResult(content)
            except (KeyError, IndexError, TypeError, ValueError):
                raise TaskBackendError("task backend returned invalid response") from None
        except httpx.TimeoutException:
            raise TaskBackendError("task backend timed out") from None
        except httpx.RequestError:
            raise TaskBackendError("task backend unavailable") from None
