"""Root-only config for the local sensor + negotiable lockouts parses correctly
and keeps safe defaults (docs/FRANK-LOCAL-AI.md)."""
from frankd import config


def test_defaults():
    cfg = config.FrankConfig()
    assert cfg.sift.backend == "local"            # AI runs locally, installed w/ OS
    assert cfg.negotiation.enabled is True
    assert cfg.negotiation.floor_fraction == 0.5


def test_sift_and_negotiation_sections_parse(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[sift]\n'
        'backend = "local"\n'
        'base_url = "http://127.0.0.1:9000/v1/chat/completions"\n'
        'model = "bitnet-b1.58-2B-4T"\n'
        'confidence_threshold = 0.7\n'
        '[negotiation]\n'
        'enabled = false\n'
        'max_attempts = 5\n'
        'min_served_fraction = 0.2\n'
        'floor_fraction = 0.4\n'
        'per_attempt_reduction_fraction = 0.3\n'
    )
    cfg = config.load(p)
    assert cfg.sift.backend == "local"
    assert cfg.sift.model == "bitnet-b1.58-2B-4T"
    assert cfg.sift.confidence_threshold == 0.7
    assert cfg.negotiation.enabled is False
    assert cfg.negotiation.max_attempts == 5
    assert cfg.negotiation.min_served_fraction == 0.2
    assert cfg.negotiation.floor_fraction == 0.4
    assert cfg.negotiation.per_attempt_reduction_fraction == 0.3
