"""Headless tests for the file manager backend (queue §2): the path-scoping
guard, size formatting, listing, and operation planning/execution."""
import pytest

from foundationhub import fileops
from foundationhub.fileops import (Entry, InvalidName, NameExists, ScopeError,
                            dir_size, do_copy, do_delete, do_move,
                            do_new_dir, do_rename, enforce_scope,
                            format_size, is_text_file, list_dir, rel_path,
                            safe_name)


# ── path-scoping guard ────────────────────────────────────────────────────────

def test_enforce_scope_allows_root_itself(tmp_path):
    assert enforce_scope(tmp_path, tmp_path) == tmp_path.resolve()


def test_enforce_scope_allows_nested_path(tmp_path):
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert enforce_scope(tmp_path, child) == child.resolve()


def test_enforce_scope_blocks_parent_escape(tmp_path):
    with pytest.raises(ScopeError):
        enforce_scope(tmp_path, tmp_path.parent)


def test_enforce_scope_blocks_dotdot_walk(tmp_path):
    escaped = tmp_path / ".." / ".." / "etc"
    with pytest.raises(ScopeError):
        enforce_scope(tmp_path, escaped)


def test_rel_path_root_is_slash(tmp_path):
    assert rel_path(tmp_path, tmp_path) == "/"


def test_rel_path_nested(tmp_path):
    child = tmp_path / "notes" / "x"
    assert rel_path(tmp_path, child) == "/notes/x"


# ── size formatting ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 * 1024, "1.0 MB"),
    (int(12.3 * 1024 * 1024), "12.3 MB"),
    (5 * 1024 ** 3, "5.0 GB"),
])
def test_format_size(n, expected):
    assert format_size(n) == expected


def test_dir_size_sums_nested_files(tmp_path):
    (tmp_path / "a.txt").write_text("12345")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("1234567890")
    assert dir_size(tmp_path) == 15


def test_dir_size_missing_dir_is_zero(tmp_path):
    assert dir_size(tmp_path / "nope") == 0


# ── listing ────────────────────────────────────────────────────────────────

def test_list_dir_dirs_first_then_alphabetical(tmp_path):
    (tmp_path / "zeta.txt").write_text("x")
    (tmp_path / "alpha.txt").write_text("x")
    (tmp_path / "beta_dir").mkdir()
    entries = list_dir(tmp_path)
    assert [e.path.name for e in entries] == ["beta_dir", "alpha.txt", "zeta.txt"]
    assert entries[0].is_dir and not entries[1].is_dir


def test_list_dir_missing_dir_is_empty(tmp_path):
    assert list_dir(tmp_path / "nope") == []


def test_is_text_file():
    from pathlib import Path
    assert is_text_file(Path("notes.md"))
    assert is_text_file(Path("a/b.txt"))
    assert not is_text_file(Path("photo.png"))
    assert not is_text_file(Path("no_extension"))


# ── operation planning ────────────────────────────────────────────────────────

def test_safe_name_strips_separators():
    assert safe_name("a/b\\c") == "abc"


def test_safe_name_rejects_empty_and_dots():
    with pytest.raises(InvalidName):
        safe_name("   ")
    with pytest.raises(InvalidName):
        safe_name(".")
    with pytest.raises(InvalidName):
        safe_name("..")


def test_do_new_dir_creates(tmp_path):
    target = do_new_dir(tmp_path, "sub")
    assert target.is_dir()
    assert target == tmp_path / "sub"


def test_do_new_dir_collision_raises(tmp_path):
    (tmp_path / "sub").mkdir()
    with pytest.raises(NameExists):
        do_new_dir(tmp_path, "sub")


def test_do_rename_moves_file(tmp_path):
    src = tmp_path / "old.md"
    src.write_text("hi")
    target = do_rename(src, "new.md")
    assert not src.exists()
    assert target.read_text() == "hi"


def test_do_rename_collision_raises(tmp_path):
    (tmp_path / "old.md").write_text("hi")
    (tmp_path / "new.md").write_text("taken")
    with pytest.raises(NameExists):
        do_rename(tmp_path / "old.md", "new.md")


def test_do_copy_file(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hi")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    target = do_copy(src, dest_dir)
    assert src.exists()                # original untouched
    assert target.read_text() == "hi"


def test_do_copy_dir(tmp_path):
    src = tmp_path / "srcdir"
    src.mkdir()
    (src / "f.md").write_text("x")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    target = do_copy(src, dest_dir)
    assert (target / "f.md").read_text() == "x"


def test_do_copy_collision_raises(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hi")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "a.md").write_text("taken")
    with pytest.raises(NameExists):
        do_copy(src, dest_dir)


def test_do_move_file(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hi")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    target = do_move(src, dest_dir)
    assert not src.exists()
    assert target.read_text() == "hi"


def test_do_delete_file(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("hi")
    do_delete(f)
    assert not f.exists()


def test_do_delete_dir(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "f.md").write_text("x")
    do_delete(d)
    assert not d.exists()
