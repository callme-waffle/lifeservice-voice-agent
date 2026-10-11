"""VOIC-FEAT-001 M6-S1-T4: finite phone utterance boundaries without external media."""

from uuid import uuid4
import pytest

from voice_agent.channels.ht813.turns import SpeechTurnDetector, TurnBoundary
from voice_agent.contracts.media import AudioChunk, INTERNAL_AUDIO_FORMAT


def frame(session_id, sequence, sample):
    return AudioChunk(session_id, sequence, sample.to_bytes(2, "little", signed=True) * 320,
                      INTERNAL_AUDIO_FORMAT)


def test_voic_feat_001_m6_s1_t4_silence_ends_only_utterance():
    """Given speech then silence, when threshold passes, then one finite turn is emitted."""
    sid = uuid4()
    detector = SpeechTurnDetector(TurnBoundary(400, 100, 1000))
    assert detector.feed(frame(sid, 0, 0)) is None
    assert detector.feed(frame(sid, 1, 1000)) is None
    result = None
    for i in range(2, 7):
        result = detector.feed(frame(sid, i, 0))
    assert result is not None
    assert [chunk.sequence for chunk in result] == [1, 2, 3, 4, 5, 6]
    assert detector.feed(frame(sid, 7, 0)) is None
    assert detector.feed(frame(sid, 8, 1000)) is None


def test_voic_feat_001_m6_s1_t4_max_length_bounds_continuous_speech():
    """Given continuous speech, when maximum length passes, then buffer is emitted and reset."""
    sid = uuid4()
    detector = SpeechTurnDetector(TurnBoundary(400, 100, 120))
    result = None
    for i in range(6):
        result = detector.feed(frame(sid, i, 1000))
    assert result is not None
    assert len(result) == 6
    assert detector.feed(frame(sid, 6, 0)) is None


def test_voic_feat_001_m6_s1_t4_rejects_unbounded_or_invalid_threshold():
    """Given invalid boundary values, when configured, then fail before a call starts."""
    for options in ((0, 800, 15000), (400, 50, 15000), (400, 800, 800), (400, 800, 61000)):
        with pytest.raises(ValueError):
            TurnBoundary(*options)
