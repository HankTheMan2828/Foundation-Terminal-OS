"""The Hub's read-only view of the games' system-wide records.

The arcade board is written by games/foundation_arcade/scores.py to
/var/lib/foundationhub/highscores.json, and chess's win/loss/draw tally by
games/foundation_chess/stats.py to chess.json (both separate distributions
from the Hub); this only checks the Hub's independent reader over those same
on-disk JSON shapes.
"""
import json

import foundationhub.highscores as highscores


def test_load_board_missing_file_is_empty(tmp_path):
    assert highscores.load_board(tmp_path / "nope.json") == {}


def test_load_board_reads_score_and_name(tmp_path):
    path = tmp_path / "highscores.json"
    path.write_text(json.dumps({"SNAKE": {"score": 42, "name": "alice"}}))
    assert highscores.load_board(path) == {"SNAKE": {"score": 42, "name": "alice"}}


def test_load_board_ignores_malformed_entries(tmp_path):
    path = tmp_path / "highscores.json"
    path.write_text(json.dumps({
        "SNAKE": {"score": 10, "name": "alice"},
        "BAD": "not a dict",
        "2048": {"score": "oops"},
    }))
    assert highscores.load_board(path) == {"SNAKE": {"score": 10, "name": "alice"}}


def test_scores_path_uses_state_env(monkeypatch, tmp_path):
    monkeypatch.setattr(highscores, "STATE_DIR", tmp_path)
    assert highscores.scores_path() == tmp_path / "highscores.json"


def test_chess_path_uses_state_env(monkeypatch, tmp_path):
    monkeypatch.setattr(highscores, "STATE_DIR", tmp_path)
    assert highscores.chess_path() == tmp_path / "chess.json"


def test_load_chess_record_missing_file_is_zeroed(tmp_path):
    assert highscores.load_chess_record(tmp_path / "nope.json") == {
        "wins": 0, "losses": 0, "draws": 0}


def test_load_chess_record_reads_machine_wide_tally(tmp_path):
    path = tmp_path / "chess.json"
    path.write_text(json.dumps({"wins": 3, "losses": 1, "draws": 2}))
    assert highscores.load_chess_record(path) == {"wins": 3, "losses": 1, "draws": 2}
