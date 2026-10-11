"""VOIC-FEAT-001 M5-S5: SIP parser and Digest challenge unit cases."""

import pytest

from voice_agent.channels.ht813.sip import digest_header, parse_sip, request_bytes


def test_voic_feat_001_m5_s5_sip_request_roundtrip():
    """Given INVITE headers and SDP, when encoded then parsed, values survive."""
    raw = request_bytes("INVITE", "sip:12345@192.0.2.17", {"Call-ID": "call-1"}, b"v=0\r\n")
    message = parse_sip(raw)
    assert message.start == "INVITE sip:12345@192.0.2.17 SIP/2.0"
    assert message.headers["call-id"] == "call-1"
    assert message.body == b"v=0\r\n"


def test_voic_feat_001_m5_s5_digest_auth_uses_challenge_without_plain_password():
    """Given 401 Digest challenge, when built, then response contains no plain secret."""
    result = digest_header('Digest realm="fxo", nonce="abc", qop="auth"',
                           username="agent", password="private-password",
                           method="INVITE", uri="sip:12345@192.0.2.17")
    assert result.startswith("Digest username=")
    assert 'qop=auth' in result
    assert "private-password" not in result


def test_voic_feat_001_m5_s5_rejects_unsupported_digest():
    """Given unsupported Digest algorithm, when challenged, then no auth header is sent."""
    with pytest.raises(ValueError):
        digest_header('Digest realm="fxo", nonce="abc", algorithm="SHA-256"',
                      username="agent", password="secret", method="INVITE", uri="sip:12345@host")
