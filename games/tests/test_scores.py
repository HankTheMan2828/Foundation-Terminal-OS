"""Score persistence: plain functions over an explicit path (no notion of
"the active user" needed for the test)."""
from foundation_arcade import scores


def test_load_scores_missing_file_is_empty(tmp_path):
    assert scores.load_scores(tmp_path / "nope.json") == {}


def test_record_score_creates_file_and_records_first_score(tmp_path):
    path = tmp_path / "users" / "alice" / "games" / "scores.json"
    best = scores.record_score(path, "SNAKE", 42)
    assert best == 42
    assert path.exists()
    assert scores.best_score(path, "SNAKE") == 42


def test_record_score_only_beats_previous_best(tmp_path):
    path = tmp_path / "scores.json"
    scores.record_score(path, "SNAKE", 50)
    assert scores.record_score(path, "SNAKE", 30) == 50   # lower score ignored
    assert scores.record_score(path, "SNAKE", 90) == 90   # higher score wins
    assert scores.best_score(path, "SNAKE") == 90


def test_scores_are_per_game(tmp_path):
    path = tmp_path / "scores.json"
    scores.record_score(path, "SNAKE", 10)
    scores.record_score(path, "2048", 2048)
    data = scores.load_scores(path)
    assert data == {"SNAKE": 10, "2048": 2048}


def test_active_username_env_var(monkeypatch):
    monkeypatch.setenv("FOUNDATIONHUB_USER", "bob")
    assert scores.active_username() == "bob"


def test_active_username_falls_back_to_guest(monkeypatch, tmp_path):
    monkeypatch.delenv("FOUNDATIONHUB_USER", raising=False)
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVE_USER", str(tmp_path / "missing"))
    assert scores.active_username() == "guest"
