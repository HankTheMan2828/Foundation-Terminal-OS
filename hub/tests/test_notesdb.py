"""Headless tests for the notes database: tag parsing, slugs, query parsing,
and search across a temp per-user tree (queue §1)."""
from pathlib import Path

from foundationhub import notesdb
from foundationhub.notesdb import (extract_tags, list_journal, list_notes,
                            note_path, parse_query, search, slugify)


# ── tag parsing ───────────────────────────────────────────────────────────────

def test_extract_basic_tags():
    assert extract_tags("remember #vault and #science") == ["vault", "science"]


def test_tags_deduped_in_first_seen_order():
    assert extract_tags("#b #a #b #a") == ["b", "a"]


def test_tags_lowercased():
    assert extract_tags("#Vault #VAULT") == ["vault"]


def test_markdown_headings_are_not_tags():
    assert extract_tags("# Title\n## Section\n#real") == ["real"]


def test_mid_word_hash_is_not_a_tag():
    assert extract_tags("foo#bar c#") == []


def test_tag_allows_dash_underscore_digits():
    assert extract_tags("#note-2 #a_b") == ["note-2", "a_b"]


def test_tag_after_punctuation_counts():
    assert extract_tags("(see #this), #that.") == ["this", "that"]


# ── slugify ───────────────────────────────────────────────────────────────────

def test_slugify_spaces_and_case():
    assert slugify("My Grand Plan") == "my-grand-plan"


def test_slugify_strips_path_hostile_chars():
    assert slugify("../../etc/passwd") == "etc-passwd"
    assert "/" not in slugify("a/b\\c")
    assert ".." not in slugify("a..b")


def test_slugify_never_empty():
    assert slugify("") == "note"
    assert slugify("!!!") == "note"


def test_slugify_collapses_dashes():
    assert slugify("a  --  b") == "a-b"


# ── note_path (shared by the Notes Area + Tagged Notes — feedback #5) ─────────

def test_note_path_slugs_under_notes_dir(tmp_path):
    assert note_path(tmp_path, "My Grand Plan") \
        == tmp_path / notesdb.NOTES_DIR / "my-grand-plan.md"


def test_note_path_is_path_safe(tmp_path):
    p = note_path(tmp_path, "../../etc/passwd")
    assert p.parent == tmp_path / notesdb.NOTES_DIR
    assert p.name == "etc-passwd.md"


# ── query parsing ─────────────────────────────────────────────────────────────

def test_parse_query_splits_tags_and_terms():
    assert parse_query("water #vault chip") == (["vault"], ["water", "chip"])


def test_parse_query_lowercases():
    assert parse_query("#Vault Chip") == (["vault"], ["chip"])


def test_parse_query_bare_hash_is_a_term():
    tags, terms = parse_query("#")
    assert tags == [] and terms == ["#"]


# ── listing + search ──────────────────────────────────────────────────────────

def _make_tree(root: Path) -> Path:
    journal = root / notesdb.JOURNAL_DIR
    notes = root / notesdb.NOTES_DIR
    journal.mkdir(parents=True)
    notes.mkdir(parents=True)
    (journal / "2026-06-30.md").write_text(
        "# 2026-06-30\n\nfixed the water chip #maintenance\n", encoding="utf-8")
    (journal / "2026-07-01.md").write_text(
        "# 2026-07-01\n\nquiet day #journal\n", encoding="utf-8")
    (notes / "reactor.md").write_text(
        "# Reactor\n\ncheck coolant #maintenance #reactor\n", encoding="utf-8")
    (notes / "recipes.md").write_text(
        "# Recipes\n\niguana-on-a-stick\n", encoding="utf-8")
    return root


def test_list_journal_newest_first(tmp_path):
    root = _make_tree(tmp_path)
    assert [p.stem for p in list_journal(root)] == ["2026-07-01", "2026-06-30"]


def test_list_notes_alphabetical(tmp_path):
    root = _make_tree(tmp_path)
    assert [p.stem for p in list_notes(root)] == ["reactor", "recipes"]


def test_listing_missing_dirs_is_empty(tmp_path):
    assert list_journal(tmp_path) == []
    assert list_notes(tmp_path) == []


def test_search_by_tag_spans_journal_and_notes(tmp_path):
    root = _make_tree(tmp_path)
    hits = search(root, "#maintenance")
    assert {h.path.stem for h in hits} == {"2026-06-30", "reactor"}
    assert {h.kind for h in hits} == {"journal", "note"}


def test_search_free_text_case_insensitive(tmp_path):
    root = _make_tree(tmp_path)
    hits = search(root, "IGUANA")
    assert [h.path.stem for h in hits] == ["recipes"]


def test_search_terms_and_tags_are_anded(tmp_path):
    root = _make_tree(tmp_path)
    assert [h.path.stem for h in search(root, "#maintenance coolant")] \
        == ["reactor"]
    assert search(root, "#maintenance iguana") == []


def test_search_empty_query_returns_nothing(tmp_path):
    root = _make_tree(tmp_path)
    assert search(root, "   ") == []


def test_search_snippet_shows_matching_line(tmp_path):
    root = _make_tree(tmp_path)
    (hit,) = search(root, "coolant")
    assert "coolant" in hit.snippet


def test_search_tag_only_snippet_shows_tag_line(tmp_path):
    root = _make_tree(tmp_path)
    hits = search(root, "#reactor")
    assert "#reactor" in hits[0].snippet
