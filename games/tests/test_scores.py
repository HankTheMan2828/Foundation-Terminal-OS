"""Score persistence: plain functions over an explicit path (no notion of
"the active user" needed for the test). System-wide only — one file, one
entry per game, never split by user."""
from foundation_arcade import scores


def test_load_scores_missing_file_is_empty(tmp_path):
    assert scores.load_scores(tmp_path / "nope.json") == {}


def test_record_score_creates_file_and_records_first_score(tmp_path):
    path = tmp_path / "highscores.json"
    best = scores.record_score(path, "SNAKE", 42, name="alice")
    assert best == 42
    assert path.exists()
    assert scores.best_score(path, "SNAKE") == 42
    assert scores.best_entry(path, "SNAKE") == {"score": 42, "name": "alice"}


def test_record_score_only_beats_previous_best(tmp_path):
    path = tmp_path / "scores.json"
    scores.record_score(path, "SNAKE", 50, name="alice")
    assert scores.record_score(path, "SNAKE", 30, name="bob") == 50   # lower score ignored
    assert scores.best_entry(path, "SNAKE")["name"] == "alice"        # attribution unchanged
    assert scores.record_score(path, "SNAKE", 90, name="bob") == 90   # higher score wins
    assert scores.best_score(path, "SNAKE") == 90
    assert scores.best_entry(path, "SNAKE")["name"] == "bob"


def test_scores_are_per_game_not_per_user(tmp_path):
    path = tmp_path / "scores.json"
    scores.record_score(path, "SNAKE", 10, name="alice")
    scores.record_score(path, "2048", 2048, name="bob")
    data = scores.load_scores(path)
    assert data == {
        "SNAKE": {"score": 10, "name": "alice"},
        "2048": {"score": 2048, "name": "bob"},
    }


def test_record_score_defaults_name_to_active_user(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDATIONHUB_USER", "carol")
    path = tmp_path / "scores.json"
    scores.record_score(path, "SNAKE", 5)
    assert scores.best_entry(path, "SNAKE") == {"score": 5, "name": "carol"}


def test_active_username_env_var(monkeypatch):
    monkeypatch.setenv("FOUNDATIONHUB_USER", "bob")
    assert scores.active_username() == "bob"


def test_active_username_falls_back_to_guest(monkeypatch, tmp_path):
    monkeypatch.delenv("FOUNDATIONHUB_USER", raising=False)
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVE_USER", str(tmp_path / "missing"))
    assert scores.active_username() == "guest"
