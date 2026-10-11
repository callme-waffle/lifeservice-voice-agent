"""VOIC-FEAT-001 package bootstrap tests."""


def test_voic_feat_001_orchestrator_package_is_importable() -> None:
    """Given the approved package layout, when imported, then its version is exposed."""
    import voice_agent

    assert voice_agent.__version__ == "0.1.0"
