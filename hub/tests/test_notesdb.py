"""Headless tests for the notes database: tag parsing, slugs, query parsing,
listing, search, and the Work/Personal section layout (queue §1, feedback #8)."""
from pathlib import Path

from foundationhub import notesdb
from foundationhub.notesdb import (SECTION_PERSONAL, SECTION_WORK, SECTIONS,
                                   extract_tags, is_journal, journal_path,
                                   list_all, list_dated, list_journal,
                                   list_notes, migrate_legacy, note_path,
                                   parse_query, search, slugify)


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


# ── note_path (per section — feedback #8) ─────────────────────────────────────

def test_note_path_slugs_under_section_dir(tmp_path):
    assert note_path(tmp_path, SECTION_WORK, "My Grand Plan") \
        == tmp_path / SECTION_WORK / "my-grand-plan.md"


def test_note_path_honors_section(tmp_path):
    p = note_path(tmp_path, SECTION_PERSONAL, "Diary")
    assert p == tmp_path / SECTION_PERSONAL / "diary.md"


def test_note_path_is_path_safe(tmp_path):
    p = note_path(tmp_path, SECTION_WORK, "../../etc/passwd")
    assert p.parent == tmp_path / SECTION_WORK
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
    """A populated two-section tree: Work notes + a Work dated entry, and a
    Personal note + a Personal journal page."""
    work = notesdb.section_dir(root, SECTION_WORK)
    work_dated = notesdb.dated_dir(root, SECTION_WORK)
    personal = notesdb.section_dir(root, SECTION_PERSONAL)
    personal_journal = notesdb.journal_dir(root, SECTION_PERSONAL)
    for d in (work, work_dated, personal, personal_journal):
        d.mkdir(parents=True, exist_ok=True)
    (work / "reactor.md").write_text(
        "# Reactor\n\ncheck coolant #maintenance #reactor\n", encoding="utf-8")
    (work / "recipes.md").write_text(
        "# Recipes\n\niguana-on-a-stick\n", encoding="utf-8")
    (work_dated / "2026-06-30-0900.md").write_text(
        "# standup\n\nfixed the water chip #maintenance\n", encoding="utf-8")
    (personal / "diary.md").write_text(
        "# Diary\n\nprivate coolant thoughts #me\n", encoding="utf-8")
    (personal_journal / "2026-06-29.md").write_text(
        "# 2026-06-29\n\nold page #journal\n", encoding="utf-8")
    (personal_journal / "2026-07-01.md").write_text(
        "# 2026-07-01\n\nquiet day #journal\n", encoding="utf-8")
    return root


def test_list_notes_alphabetical_per_section(tmp_path):
    root = _make_tree(tmp_path)
    assert [p.stem for p in list_notes(root, SECTION_WORK)] == ["reactor", "recipes"]
    assert [p.stem for p in list_notes(root, SECTION_PERSONAL)] == ["diary"]


def test_list_dated_newest_first(tmp_path):
    root = _make_tree(tmp_path)
    assert [p.stem for p in list_dated(root, SECTION_WORK)] == ["2026-06-30-0900"]


def test_list_journal_newest_first(tmp_path):
    root = _make_tree(tmp_path)
    assert [p.stem for p in list_journal(root, SECTION_PERSONAL)] \
        == ["2026-07-01", "2026-06-29"]


def test_listing_missing_dirs_is_empty(tmp_path):
    assert list_notes(tmp_path, SECTION_WORK) == []
    assert list_journal(tmp_path, SECTION_PERSONAL) == []
    assert list_dated(tmp_path, SECTION_WORK) == []
    assert list_all(tmp_path, SECTION_WORK) == []


# ── unified list (the reworked Notes screen) ─────────────────────────────────

def test_journal_path_lands_in_section_journal_dir(tmp_path):
    assert journal_path(tmp_path, SECTION_PERSONAL, "2026-07-09") \
        == tmp_path / SECTION_PERSONAL / "journal" / "2026-07-09.md"


def test_is_journal_distinguishes_journal_pages_from_plain_notes(tmp_path):
    root = _make_tree(tmp_path)
    (note,) = list_notes(root, SECTION_PERSONAL)          # diary.md
    (page, _older) = list_journal(root, SECTION_PERSONAL)  # newest first
    assert is_journal(page) is True
    assert is_journal(note) is False


def test_list_all_gathers_notes_and_journal_newest_first(tmp_path):
    root = _make_tree(tmp_path)
    # Personal has a plain note plus two journal pages — all three, most
    # recently edited first (mtime order, which _make_tree writes ascending).
    stems = [p.stem for p in list_all(root, SECTION_PERSONAL)]
    assert set(stems) == {"diary", "2026-06-29", "2026-07-01"}
    # every path is a real file under the section, journal pages included
    assert all(p.is_file() for p in list_all(root, SECTION_PERSONAL))


def test_list_all_orders_by_mtime_newest_first(tmp_path):
    import os
    import time
    root = notesdb.section_dir(tmp_path, SECTION_WORK)
    root.mkdir(parents=True)
    old = root / "old.md"
    new = root / "new.md"
    old.write_text("x", encoding="utf-8")
    new.write_text("y", encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))
    assert [p.stem for p in list_all(tmp_path, SECTION_WORK)] == ["new", "old"]


def test_search_work_only_by_default_excludes_personal(tmp_path):
    root = _make_tree(tmp_path)
    # "#me" only exists in a Personal note; a Work-only search must miss it.
    assert search(root, "#me", (SECTION_WORK,)) == []
    hits = search(root, "#me", SECTIONS)
    assert {h.path.stem for h in hits} == {"diary"}
    assert hits[0].section == SECTION_PERSONAL


def test_search_spans_notes_and_dated_within_a_section(tmp_path):
    root = _make_tree(tmp_path)
    hits = search(root, "#maintenance", (SECTION_WORK,))
    # matches the Work note AND the Work dated entry (rglob over the section)
    assert {h.path.stem for h in hits} == {"reactor", "2026-06-30-0900"}
    assert {h.section for h in hits} == {SECTION_WORK}


def test_search_free_text_case_insensitive(tmp_path):
    root = _make_tree(tmp_path)
    hits = search(root, "IGUANA", (SECTION_WORK,))
    assert [h.path.stem for h in hits] == ["recipes"]


def test_search_terms_and_tags_are_anded(tmp_path):
    root = _make_tree(tmp_path)
    assert [h.path.stem for h in search(root, "#maintenance coolant", (SECTION_WORK,))] \
        == ["reactor"]
    assert search(root, "#maintenance iguana", (SECTION_WORK,)) == []


def test_search_empty_query_returns_nothing(tmp_path):
    root = _make_tree(tmp_path)
    assert search(root, "   ", SECTIONS) == []


def test_search_snippet_shows_matching_line(tmp_path):
    root = _make_tree(tmp_path)
    (hit,) = search(root, "coolant", (SECTION_WORK,))
    assert "coolant" in hit.snippet


# ── one-time migration from the pre-#8 flat layout ───────────────────────────

def test_migrate_legacy_moves_flat_tree_into_sections(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "reactor.md").write_text("x", encoding="utf-8")
    (tmp_path / "dated").mkdir()
    (tmp_path / "dated" / "2026-06-30-0900.md").write_text("x", encoding="utf-8")
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "2026-07-01.md").write_text("x", encoding="utf-8")

    migrate_legacy(tmp_path)

    assert [p.stem for p in list_notes(tmp_path, SECTION_WORK)] == ["reactor"]
    assert [p.stem for p in list_dated(tmp_path, SECTION_WORK)] == ["2026-06-30-0900"]
    assert [p.stem for p in list_journal(tmp_path, SECTION_PERSONAL)] == ["2026-07-01"]
    # old dirs are gone
    assert not (tmp_path / "notes").exists()
    assert not (tmp_path / "journal").exists()


def test_migrate_legacy_is_idempotent_and_nondestructive(tmp_path):
    _make_tree(tmp_path)   # already in the new layout
    before = {p.stem for p in list_notes(tmp_path, SECTION_WORK)}
    migrate_legacy(tmp_path)
    migrate_legacy(tmp_path)
    assert {p.stem for p in list_notes(tmp_path, SECTION_WORK)} == before
