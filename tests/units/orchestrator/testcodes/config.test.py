"""VOIC-FEAT-001 M6-S1-T1 runtime configuration cases."""

import pytest

from voice_agent.config import Settings
from voice_agent.contracts.session import DialNumber


def valid_env():
    return {
        "VOICE_AGENT_WEB_ACCESS_TOKEN": "test-only-token",
        "VOICE_AGENT_STT_MODEL_ID": "small",
        "VOICE_AGENT_TASK_MODEL": "test-model",
        "VOICE_AGENT_TASK_API_KEY": "test-only-key",
        "VOICE_AGENT_TASK_API_BASE_URL": "https://llm.example.test",
        "VOICE_AGENT_TASK_APPROVED_HOST": "llm.example.test",
        "VOICE_AGENT_DATA_ENCRYPTION_KEY": "S0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0s=",
    }


def test_valid_web_configuration_keeps_telephone_disabled():
    """Given no number policy, when loading config, then no outbound policy exists."""
    settings = Settings.from_env(valid_env())
    assert settings.allowed_numbers is None
    assert settings.tts_speed == 1.25
    assert settings.timeouts.task_s == 60


def test_voic_feat_001_m6_s3_reads_container_secrets_without_env_values(tmp_path):
    """Given mounted secret files, when loading config, then values stay out of env and errors."""
    env = valid_env()
    for key in ("VOICE_AGENT_TASK_API_KEY", "VOICE_AGENT_WEB_ACCESS_TOKEN",
                "VOICE_AGENT_DATA_ENCRYPTION_KEY"):
        value = env.pop(key)
        path = tmp_path / key
        path.write_text(value)
        env[f"{key}_FILE"] = str(path)
    settings = Settings.from_env(env)
    assert settings.task_key == "test-only-key"
    assert settings.web_token == "test-only-token"
    with pytest.raises(ValueError, match="set only one"):
        Settings.from_env(env | {"VOICE_AGENT_TASK_API_KEY": "duplicate"})
    env["VOICE_AGENT_TASK_API_KEY_FILE"] = str(tmp_path / "missing")
    with pytest.raises(ValueError, match="unavailable VOICE_AGENT_TASK_API_KEY_FILE") as raised:
        Settings.from_env(env)
    assert str(tmp_path) not in str(raised.value)


@pytest.mark.parametrize("missing", [
    "VOICE_AGENT_WEB_ACCESS_TOKEN", "VOICE_AGENT_STT_MODEL_ID",
    "VOICE_AGENT_TASK_MODEL", "VOICE_AGENT_TASK_API_KEY",
    "VOICE_AGENT_TASK_API_BASE_URL", "VOICE_AGENT_TASK_APPROVED_HOST",
])
def test_missing_required_setting_fails_without_echoing_secret(missing):
    """Given a missing required value, when loading, then validation fails safely."""
    env = valid_env()
    env.pop(missing)
    with pytest.raises(ValueError, match=missing):
        Settings.from_env(env)


def test_outbound_policy_requires_local_sip_identity():
    """Given allowed numbers, when SIP identity is absent, then startup fails."""
    env = valid_env() | {
        "VOICE_AGENT_HT813_ALLOWED_EXACT": "1234567",
        "VOICE_AGENT_HT813_HOST": "192.0.2.17",
    }
    with pytest.raises(ValueError, match="VOICE_AGENT_HT813_LOCAL_IPV4"):
        Settings.from_env(env)
    env["VOICE_AGENT_HT813_LOCAL_IPV4"] = "192.0.2.50"
    env["VOICE_AGENT_HT813_SIP_USER_ID"] = "test-user"
    assert Settings.from_env(env).allowed_numbers.allows(DialNumber("1234567"))


def test_disallowed_transport_retry_and_retention_are_rejected():
    """Given incompatible policy values, when loading, then startup rejects each."""
    for key, value in (
        ("VOICE_AGENT_HT813_SIP_TRANSPORT", "tcp"),
        ("VOICE_AGENT_TASK_MAX_RETRIES", "1"),
        ("VOICE_AGENT_RETENTION_DAYS", "31"),
    ):
        with pytest.raises(ValueError, match=key):
            Settings.from_env(valid_env() | {key: value})


def test_voic_feat_001_m6_s1_t5_inbound_independent_of_outbound_allowlist():
    """Given inbound enabled and no dial destinations, when configured, then only receive is available."""
    env = valid_env() | {
        "VOICE_AGENT_HT813_INBOUND_ENABLED": "true",
        "VOICE_AGENT_HT813_HOST": "192.0.2.17",
        "VOICE_AGENT_HT813_LOCAL_IPV4": "192.0.2.50",
        "VOICE_AGENT_HT813_SIP_USER_ID": "agent",
    }
    settings = Settings.from_env(env)
    assert settings.allowed_numbers is None
    assert settings.ht813_inbound_enabled is True
    assert (settings.ht813_inbound_sip_port, settings.ht813_inbound_rtp_port) == (5061, 4002)


def test_voic_feat_001_m6_s1_t5_inbound_port_conflicts_rejected():
    """Given identical inbound/outbound SIP or RTP ports, when loading, then startup fails."""
    env = valid_env() | {
        "VOICE_AGENT_HT813_INBOUND_ENABLED": "true",
        "VOICE_AGENT_HT813_HOST": "192.0.2.17",
        "VOICE_AGENT_HT813_LOCAL_IPV4": "192.0.2.50",
        "VOICE_AGENT_HT813_SIP_USER_ID": "agent",
    }
    for key, value in (("VOICE_AGENT_HT813_INBOUND_SIP_PORT", "5060"),
                       ("VOICE_AGENT_HT813_INBOUND_RTP_PORT", "4000")):
        with pytest.raises(ValueError, match="ports must differ"):
            Settings.from_env(env | {key: value})


def test_voic_feat_001_m6_s1_t6_requires_private_retention_key_and_policy():
    """Given missing key or disabled recording, when configured, then fail without echoing secrets."""
    for key, value in (
        ("VOICE_AGENT_DATA_ENCRYPTION_KEY", ""),
        ("VOICE_AGENT_DATA_ENCRYPTION_KEY", "invalid-key"),
        ("VOICE_AGENT_RECORD_AUDIO", "false"),
        ("VOICE_AGENT_STORE_TRANSCRIPTS", "false"),
        ("VOICE_AGENT_LOG_TRANSCRIPTS", "true"),
        ("VOICE_AGENT_LOG_AUDIO_PAYLOADS", "true"),
    ):
        with pytest.raises(ValueError) as raised:
            Settings.from_env(valid_env() | {key: value})
        assert key in str(raised.value)
        assert "test-only-key" not in str(raised.value)
    settings = Settings.from_env(valid_env())
    assert len(settings.data_encryption_key) == 32
    assert settings.data_encryption_key not in repr(settings).encode()
