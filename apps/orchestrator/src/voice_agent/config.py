"""Validated runtime settings for M6 assembly (VOIC-FEAT-001)."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from urllib.parse import urlparse

from voice_agent.channels.ht813.turns import TurnBoundary
from voice_agent.contracts.session import AllowedNumberPolicy, StepTimeouts


def _number(env: Mapping[str, str], key: str, default: str, kind: type[int] | type[float]):
    try:
        return kind(env.get(key, default))
    except (ValueError, TypeError):
        raise ValueError(f"invalid {key}") from None


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ValueError(f"missing {key}")
    return value


def _secret(env: Mapping[str, str], key: str) -> str:
    """Read a secret from a mounted file, or from the existing local env contract."""
    filename = env.get(f"{key}_FILE", "").strip()
    if not filename:
        return _required(env, key)
    if env.get(key, "").strip():
        raise ValueError(f"set only one of {key} and {key}_FILE")
    try:
        value = Path(filename).read_text(encoding="utf-8").strip()
    except OSError:
        raise ValueError(f"unavailable {key}_FILE") from None
    if not value:
        raise ValueError(f"empty {key}_FILE")
    return value


def _csv(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    web_token: str = field(repr=False)
    stt_model: str
    tts_speed: float
    task_model: str
    task_key: str = field(repr=False)
    task_url: str
    task_approved_host: str
    timeouts: StepTimeouts
    buffer_capacity: int
    ht813_host: str | None
    ht813_port: int
    ht813_local_host: str | None
    ht813_local_sip_port: int
    ht813_local_rtp_port: int
    ht813_user: str | None
    ht813_password: str | None = field(repr=False)
    allowed_numbers: AllowedNumberPolicy | None
    turn_boundary: TurnBoundary
    ht813_inbound_enabled: bool
    ht813_inbound_sip_port: int
    ht813_inbound_rtp_port: int
    ht813_caller_id_header: str
    recordings_dir: Path
    transcripts_dir: Path
    calls_dir: Path
    deletion_audit_path: Path
    retention_sweep_interval_s: int
    data_encryption_key: bytes = field(repr=False)
    stt_endpoint: str | None = None
    tts_endpoint: str | None = None
    otel_endpoint: str | None = None
    metrics_host: str | None = None
    metrics_port: int = 8001

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        if env.get("VOICE_AGENT_MAX_ACTIVE_SESSIONS", "1") != "1":
            raise ValueError("VOICE_AGENT_MAX_ACTIVE_SESSIONS must be 1")
        if env.get("VOICE_AGENT_TASK_MAX_RETRIES", "0") != "0":
            raise ValueError("VOICE_AGENT_TASK_MAX_RETRIES must be 0")
        if env.get("VOICE_AGENT_TASK_TLS_VERIFY", "true").lower() != "true":
            raise ValueError("VOICE_AGENT_TASK_TLS_VERIFY must be true")
        if env.get("VOICE_AGENT_HT813_SIP_TRANSPORT", "udp").lower() != "udp":
            raise ValueError("VOICE_AGENT_HT813_SIP_TRANSPORT must be udp")
        for key, value in (("VOICE_AGENT_AUDIO_ENCODING", "pcm_s16le"),
                           ("VOICE_AGENT_AUDIO_SAMPLE_RATE_HZ", "16000"),
                           ("VOICE_AGENT_AUDIO_CHANNELS", "1")):
            if env.get(key, value) != value:
                raise ValueError(f"{key} does not match the internal audio contract")
        if env.get("VOICE_AGENT_RETENTION_DAYS", "30") != "30":
            raise ValueError("VOICE_AGENT_RETENTION_DAYS must be 30")
        for key in ("VOICE_AGENT_RECORD_AUDIO", "VOICE_AGENT_STORE_TRANSCRIPTS"):
            if env.get(key, "true").lower() != "true":
                raise ValueError(f"{key} must be true")
        for key in ("VOICE_AGENT_LOG_TRANSCRIPTS", "VOICE_AGENT_LOG_AUDIO_PAYLOADS"):
            if env.get(key, "false").lower() != "false":
                raise ValueError(f"{key} must be false")
        encoded_key = _secret(env, "VOICE_AGENT_DATA_ENCRYPTION_KEY")
        try:
            data_key = base64.b64decode(encoded_key, altchars=b"-_", validate=True)
        except (ValueError, base64.binascii.Error):
            raise ValueError("invalid VOICE_AGENT_DATA_ENCRYPTION_KEY") from None
        if len(data_key) != 32:
            raise ValueError("invalid VOICE_AGENT_DATA_ENCRYPTION_KEY")
        sweep_interval = _number(env, "VOICE_AGENT_RETENTION_SWEEP_INTERVAL_SECONDS", "3600", int)
        if not 60 <= sweep_interval <= 86400:
            raise ValueError("invalid VOICE_AGENT_RETENTION_SWEEP_INTERVAL_SECONDS")
        stt_model = _required(env, "VOICE_AGENT_STT_MODEL_ID")
        if stt_model not in ("small", "medium"):
            raise ValueError("unsupported VOICE_AGENT_STT_MODEL_ID")
        if env.get("VOICE_AGENT_STT_BACKEND", "faster-whisper") != "faster-whisper":
            raise ValueError("unsupported VOICE_AGENT_STT_BACKEND")
        if env.get("VOICE_AGENT_TTS_BACKEND", "MeloTTS-Korean") != "MeloTTS-Korean":
            raise ValueError("unsupported VOICE_AGENT_TTS_BACKEND")
        if env.get("VOICE_AGENT_TTS_MODEL_ID", "MeloTTS-Korean") != "MeloTTS-Korean":
            raise ValueError("unsupported VOICE_AGENT_TTS_MODEL_ID")
        speed = _number(env, "VOICE_AGENT_TTS_SPEED", "1.25", float)
        if not .5 <= speed <= 2:
            raise ValueError("invalid VOICE_AGENT_TTS_SPEED")
        stt_endpoint = env.get("VOICE_AGENT_STT_ENDPOINT") or None
        tts_endpoint = env.get("VOICE_AGENT_TTS_ENDPOINT") or None
        if bool(stt_endpoint) != bool(tts_endpoint):
            raise ValueError("both model endpoints must be configured together")
        otel_endpoint = env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or None
        metrics_host = env.get("VOICE_AGENT_METRICS_HOST") or None
        metrics_port = _number(env, "VOICE_AGENT_METRICS_PORT", "8001", int)
        if not 1 <= metrics_port <= 65535:
            raise ValueError("invalid VOICE_AGENT_METRICS_PORT")
        for name, endpoint in (("VOICE_AGENT_STT_ENDPOINT", stt_endpoint),
                               ("VOICE_AGENT_TTS_ENDPOINT", tts_endpoint),
                               ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", otel_endpoint)):
            if endpoint and (urlparse(endpoint).scheme not in {"http", "https"}
                             or not urlparse(endpoint).netloc):
                raise ValueError(f"invalid {name}")
        port = _number(env, "VOICE_AGENT_API_PORT", "8000", int)
        capacity = _number(env, "VOICE_AGENT_AUDIO_QUEUE_MAX_CHUNKS", "4", int)
        if not 1 <= port <= 65535 or capacity < 1:
            raise ValueError("invalid application port or queue capacity")
        timeouts = StepTimeouts(
            _number(env, "VOICE_AGENT_STT_TIMEOUT_SECONDS", "120", float),
            _number(env, "VOICE_AGENT_TASK_TIMEOUT_SECONDS", "60", float),
            _number(env, "VOICE_AGENT_TTS_TIMEOUT_SECONDS", "120", float),
        )
        exact = _csv(env.get("VOICE_AGENT_HT813_ALLOWED_EXACT", ""))
        prefixes = _csv(env.get("VOICE_AGENT_HT813_ALLOWED_PREFIXES", ""))
        policy = AllowedNumberPolicy(exact, prefixes) if exact or prefixes else None
        inbound_value = env.get("VOICE_AGENT_HT813_INBOUND_ENABLED", "false").lower()
        if inbound_value not in ("true", "false"):
            raise ValueError("invalid VOICE_AGENT_HT813_INBOUND_ENABLED")
        inbound_enabled = inbound_value == "true"
        caller_id_header = env.get("VOICE_AGENT_HT813_CALLER_ID_HEADER", "from").lower()
        if caller_id_header not in ("from", "p-asserted-identity",
                                    "p-preferred-identity", "disabled"):
            raise ValueError("invalid VOICE_AGENT_HT813_CALLER_ID_HEADER")
        ht_port = _number(env, "VOICE_AGENT_HT813_FXO_SIP_PORT", "5062", int)
        sip_port = _number(env, "VOICE_AGENT_HT813_LOCAL_SIP_PORT", "5060", int)
        rtp_port = _number(env, "VOICE_AGENT_HT813_LOCAL_RTP_PORT", "4000", int)
        inbound_sip_port = _number(env, "VOICE_AGENT_HT813_INBOUND_SIP_PORT", "5061", int)
        inbound_rtp_port = _number(env, "VOICE_AGENT_HT813_INBOUND_RTP_PORT", "4002", int)
        if any(not 1 <= value <= 65535 for value in
               (ht_port, sip_port, rtp_port, inbound_sip_port, inbound_rtp_port)):
            raise ValueError("invalid HT813 port")
        if inbound_enabled and (sip_port == inbound_sip_port or rtp_port == inbound_rtp_port):
            raise ValueError("inbound and outbound HT813 ports must differ")
        configured = policy is not None or inbound_enabled
        ht_host = _required(env, "VOICE_AGENT_HT813_HOST") if configured else None
        local_host = _required(env, "VOICE_AGENT_HT813_LOCAL_IPV4") if configured else None
        user = _required(env, "VOICE_AGENT_HT813_SIP_USER_ID") if configured else None
        return cls(
            host=env.get("VOICE_AGENT_API_HOST", "127.0.0.1"), port=port,
            web_token=_secret(env, "VOICE_AGENT_WEB_ACCESS_TOKEN"),
            stt_model=stt_model, tts_speed=speed,
            task_model=_required(env, "VOICE_AGENT_TASK_MODEL"),
            task_key=_secret(env, "VOICE_AGENT_TASK_API_KEY"),
            task_url=_required(env, "VOICE_AGENT_TASK_API_BASE_URL"),
            task_approved_host=_required(env, "VOICE_AGENT_TASK_APPROVED_HOST"),
            timeouts=timeouts, buffer_capacity=capacity,
            ht813_host=ht_host, ht813_port=ht_port, ht813_local_host=local_host,
            ht813_local_sip_port=sip_port, ht813_local_rtp_port=rtp_port,
            ht813_user=user, ht813_password=env.get("VOICE_AGENT_HT813_SIP_PASSWORD") or None,
            allowed_numbers=policy,
            ht813_inbound_enabled=inbound_enabled,
            ht813_inbound_sip_port=inbound_sip_port,
            ht813_inbound_rtp_port=inbound_rtp_port,
            ht813_caller_id_header=caller_id_header,
            recordings_dir=Path(env.get("VOICE_AGENT_RECORDINGS_DIR", "./data/recordings")),
            transcripts_dir=Path(env.get("VOICE_AGENT_TRANSCRIPTS_DIR", "./data/transcripts")),
            calls_dir=Path(env.get("VOICE_AGENT_CALLS_DIR", "./data/calls")),
            deletion_audit_path=Path(env.get("VOICE_AGENT_DELETION_AUDIT_LOG", "./data/deletion-audit.jsonl")),
            retention_sweep_interval_s=sweep_interval,
            data_encryption_key=data_key,
            stt_endpoint=stt_endpoint, tts_endpoint=tts_endpoint,
            otel_endpoint=otel_endpoint,
            metrics_host=metrics_host, metrics_port=metrics_port,
            turn_boundary=TurnBoundary(
                _number(env, "VOICE_AGENT_HT813_VAD_ENERGY", "400", int),
                _number(env, "VOICE_AGENT_HT813_VAD_SILENCE_MS", "800", int),
                _number(env, "VOICE_AGENT_HT813_MAX_UTTERANCE_MS", "15000", int),
            ),
        )
