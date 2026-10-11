"""Session, event, error and outbound number contracts for VOIC-FEAT-001."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from .media import DtmfEvent


class Channel(StrEnum):
    WEB = "web"
    HT813_FXO = "ht813_fxo"


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: UUID
    channel: Channel
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.channel, Channel):
            raise TypeError("session channel must be a Channel")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("session time must be UTC aware")


@dataclass(frozen=True, slots=True)
class StepTimeouts:
    stt_s: float
    task_s: float
    tts_s: float

    def __post_init__(self) -> None:
        if any(not 0 < value <= 600 for value in (self.stt_s, self.task_s, self.tts_s)):
            raise ValueError("each processing timeout must be 0..600 seconds")


class CallStatus(StrEnum):
    DIALING = "dialing"
    RINGING = "ringing"
    ACTIVE = "active"
    BUSY = "busy"
    FAILED = "failed"
    ENDED = "ended"


class SessionStatus(StrEnum):
    STARTING = "starting"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SessionState:
    status: SessionStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, SessionStatus):
            raise TypeError("session status must be a SessionStatus")


@dataclass(frozen=True, slots=True)
class CallState:
    status: CallStatus
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, CallStatus):
            raise TypeError("call status must be a CallStatus")
        if self.reason is not None and len(self.reason) > 160:
            raise ValueError("call reason is too long")


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    is_final: bool

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("transcript text is empty")


@dataclass(frozen=True, slots=True)
class TaskResult:
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("task result text is empty")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """Only a final user transcript and its successful assistant reply."""

    user_text: str
    assistant_text: str

    def __post_init__(self) -> None:
        if not self.user_text.strip() or not self.assistant_text.strip():
            raise ValueError("conversation turn must contain final texts")


class ErrorCode(StrEnum):
    BUSY = "busy"
    INVALID_INPUT = "invalid_input"
    NOT_ALLOWED = "not_allowed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class PublicError:
    code: ErrorCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode):
            raise TypeError("public error code must be an ErrorCode")
        if not self.message.strip() or len(self.message) > 160:
            raise ValueError("public error message must be 1..160 characters")


EventPayload = SessionState | CallState | Transcript | TaskResult | DtmfEvent | PublicError


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    session_id: UUID
    sequence: int
    payload: EventPayload

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("event sequence must be nonnegative")
        if isinstance(self.payload, DtmfEvent) and self.payload.session_id != self.session_id:
            raise ValueError("DTMF session does not match envelope")
        if not isinstance(self.payload, (SessionState, CallState, Transcript, TaskResult, DtmfEvent, PublicError)):
            raise TypeError("unsupported event payload")


_DIAL_NUMBER = re.compile(r"\+?[0-9]{3,15}\Z")


@dataclass(frozen=True, slots=True)
class DialNumber:
    value: str

    def __post_init__(self) -> None:
        if not _DIAL_NUMBER.fullmatch(self.value):
            raise ValueError("dial number must be 3..15 digits with optional leading +")


@dataclass(frozen=True, slots=True)
class AllowedNumberPolicy:
    exact: frozenset[str] = frozenset()
    prefixes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.exact and not self.prefixes:
            raise ValueError("an explicit allowed number policy is required")
        for number in self.exact:
            DialNumber(number)
        for prefix in self.prefixes:
            if not re.fullmatch(r"\+?[0-9]{2,15}", prefix):
                raise ValueError("invalid allowed prefix")

    def allows(self, number: DialNumber) -> bool:
        return number.value in self.exact or any(
            number.value.startswith(prefix) for prefix in self.prefixes
        )


@dataclass(frozen=True, slots=True)
class OutboundCallRequest:
    session_id: UUID
    number: DialNumber
    timeout_s: float

    def __post_init__(self) -> None:
        if not 0 < self.timeout_s <= 120:
            raise ValueError("dial timeout must be 0..120 seconds")

    def authorize(self, policy: AllowedNumberPolicy) -> None:
        if not policy.allows(self.number):
            raise PermissionError("destination is not in the allowed number policy")
