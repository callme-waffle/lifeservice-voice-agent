"""VOIC-FEAT-001 M4-S2-T2 session and dialing contract tests."""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from voice_agent.contracts.media import DtmfEvent
from voice_agent.contracts.session import (
    AllowedNumberPolicy,
    CallState,
    CallStatus,
    Channel,
    DialNumber,
    EventEnvelope,
    OutboundCallRequest,
    SessionContext,
    SessionState,
    SessionStatus,
    StepTimeouts,
)

SESSION = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")


def test_voic_feat_001_session_requires_utc_and_explicit_channel() -> None:
    """Given session metadata, when built, then time and channel are unambiguous."""
    assert SessionContext(SESSION, Channel.WEB, datetime(2026, 9, 24, tzinfo=timezone.utc)).channel is Channel.WEB
    with pytest.raises(ValueError):
        SessionContext(SESSION, Channel.WEB, datetime(2026, 9, 24))


def test_voic_feat_001_dial_rejects_feature_codes_and_unauthorized_number() -> None:
    """Given an explicit allowlist, when dialing, then only approved digits pass."""
    with pytest.raises(ValueError):
        DialNumber("*00123")
    with pytest.raises(ValueError):
        AllowedNumberPolicy()
    policy = AllowedNumberPolicy(exact=frozenset({"0212345678"}))
    request = OutboundCallRequest(SESSION, DialNumber("0212345678"), 30)
    request.authorize(policy)
    with pytest.raises(PermissionError):
        OutboundCallRequest(SESSION, DialNumber("0212345679"), 30).authorize(policy)


def test_voic_feat_001_event_rejects_wrong_session_dtmf() -> None:
    """Given an event envelope, when DTMF belongs elsewhere, then correlation fails."""
    with pytest.raises(ValueError):
        EventEnvelope(SESSION, 0, DtmfEvent(OTHER, "1", 100))
    assert EventEnvelope(SESSION, 1, CallState(CallStatus.RINGING)).sequence == 1
    assert EventEnvelope(SESSION, 2, SessionState(SessionStatus.LISTENING)).sequence == 2


def test_voic_feat_001_timeout_contract_rejects_unbounded_steps() -> None:
    """Given per-stage limits, when one is unbounded, then reject the policy."""
    assert StepTimeouts(10, 30, 10).task_s == 30
    with pytest.raises(ValueError):
        StepTimeouts(10, 0, 10)
