"""Notes database (BUILD-QUEUE §1): tag parsing, scanning, search.

Pure stdlib, no curses — the notes screens compose these functions and the
tests exercise them headlessly. Notes are plain `.md` files on disk
(portable, greppable, quota-friendly).

Layout (feedback #8 — Home Hub IA rework): notes are split by *purpose* into
two sections, each its own folder under the account's data dir so they show up
as two clean folders in the File Manager:

    work/<slug>.md            plain Work notes (named on creation)
    work/dated/<stamp>.md     Work dated entries (timestamped, many per day)
    personal/<slug>.md        plain Personal notes
    personal/journal/DATE.md  Personal journal (one page per day)

Tags are inline `#tag` tokens in the body; there is no sidecar index to
corrupt — every lookup re-reads the files, which stay small by nature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ── Purpose-based sections (feedback #8) ─────────────────────────────────────
SECTION_WORK = "work"
SECTION_PERSONAL = "personal"
SECTIONS = (SECTION_WORK, SECTION_PERSONAL)

# Per-section subfolders for the two dated features, kept apart from the plain
# notes that sit directly in the section dir: Work gets timestamped entries
# (several per day), Personal gets the one-page-per-day journal.
DATED_SUBDIR = "dated"
JOURNAL_SUBDIR = "journal"

# Legacy (pre-#8) flat folders, migrated once into the sections above.
_LEGACY_NOTES = "notes"
_LEGACY_DATED = "dated"
_LEGACY_JOURNAL = "journal"

# A tag is `#word` where the `#` starts a token: not mid-word (`foo#bar`) and
# not a markdown heading run (`##`). Heading lines like `# Title` don't match
# because the tag body must start alphanumeric, not a space.
_TAG_RE = re.compile(r"(?<![\w#])#([A-Za-z0-9][\w-]*)")

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def extract_tags(text: str) -> list[str]:
    """All `#tag` tokens in order of first appearance, lowercased, deduped."""
    seen: list[str] = []
    for m in _TAG_RE.finditer(text):
        tag = m.group(1).lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def slugify(name: str) -> str:
    """A display name → a safe `.md` stem. Never empty, never a path escape."""
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "note"


def parse_query(query: str) -> tuple[list[str], list[str]]:
    """Split a search query into (tags, free-text terms). `#tag` tokens match
    the tag index; everything else is a case-insensitive substring term."""
    tags: list[str] = []
    terms: list[str] = []
    for token in query.split():
        if token.startswith("#") and len(token) > 1:
            tags.append(token[1:].lower())
        else:
            terms.append(token.lower())
    return tags, terms


# ── section paths ─────────────────────────────────────────────────────────────
def section_dir(user_dir: Path, section: str) -> Path:
    """The folder holding one section's plain notes (also the File Manager's
    visible `work/` or `personal/` folder)."""
    return user_dir / section


def dated_dir(user_dir: Path, section: str) -> Path:
    """Where a section's timestamped dated entries live (Work uses this)."""
    return section_dir(user_dir, section) / DATED_SUBDIR


def journal_dir(user_dir: Path, section: str) -> Path:
    """Where a section's one-per-day journal lives (Personal uses this)."""
    return section_dir(user_dir, section) / JOURNAL_SUBDIR


def note_path(user_dir: Path, section: str, name: str) -> Path:
    """The `.md` path a note with display `name` maps to inside `section`: a
    slugged stem under the section dir. Path-safe by construction (slugify
    strips escapes), and `section` is a fixed constant, never user input."""
    return section_dir(user_dir, section) / f"{slugify(name)}.md"


# ── listing ───────────────────────────────────────────────────────────────────
def _list_md(d: Path, *, newest_first: bool) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted(d.glob("*.md"), key=lambda p: p.name, reverse=newest_first)


def list_notes(user_dir: Path, section: str) -> list[Path]:
    """A section's plain notes, alphabetical."""
    return _list_md(section_dir(user_dir, section), newest_first=False)


def list_dated(user_dir: Path, section: str) -> list[Path]:
    """A section's dated entries, newest first (stamped names sort that way)."""
    return _list_md(dated_dir(user_dir, section), newest_first=True)


def list_journal(user_dir: Path, section: str) -> list[Path]:
    """A section's journal pages, newest first (date-stamped names sort so)."""
    return _list_md(journal_dir(user_dir, section), newest_first=True)


def note_tags(path: Path) -> list[str]:
    try:
        return extract_tags(path.read_text(encoding="utf-8"))
    except OSError:
        return []


# ── search ────────────────────────────────────────────────────────────────────
@dataclass
class Hit:
    """One matching file with a one-line snippet for the results list."""
    path: Path
    section: str       # "work" | "personal" — which section the file lives in
    snippet: str


def _snippet(text: str, tags: list[str], terms: list[str]) -> str:
    """First line that shows *why* this file matched; else its first content."""
    needles = [t for t in terms] + [f"#{t}" for t in tags]
    lines = text.splitlines()
    for needle in needles:
        for line in lines:
            if needle in line.lower():
                return line.strip()
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def search(user_dir: Path, query: str, sections=SECTIONS) -> list[Hit]:
    """AND-match `query` across the given sections (all of a section's `.md`
    files — plain notes plus its dated/journal subfolder). Every `#tag` must be
    in the file's tag set and every term a substring of its text
    (case-insensitive). `sections` lets Notes Search scope Work-only by default
    and opt into Personal (feedback #8)."""
    tags, terms = parse_query(query)
    if not tags and not terms:
        return []
    hits: list[Hit] = []
    for section in sections:
        base = section_dir(user_dir, section)
        for path in sorted(base.rglob("*.md"), key=lambda p: str(p)):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            lower = text.lower()
            file_tags = extract_tags(text)
            if all(t in file_tags for t in tags) and \
               all(t in lower for t in terms):
                hits.append(Hit(path, section, _snippet(text, tags, terms)))
    return hits


# ── one-time migration from the pre-#8 flat layout ───────────────────────────
def migrate_legacy(user_dir: Path) -> None:
    """Move a pre-rework flat tree into the Work/Personal sections, once.

    Old scratch/tagged `notes/` and timestamped `dated/` were the general
    (non-personal) area → Work. The one-per-day `journal/` was the Personal
    File → Personal. Each move only runs when the source exists and the target
    does not, so it is idempotent and never clobbers real data.
    """
    moves = [
        (user_dir / _LEGACY_NOTES, section_dir(user_dir, SECTION_WORK)),
        (user_dir / _LEGACY_DATED, dated_dir(user_dir, SECTION_WORK)),
        (user_dir / _LEGACY_JOURNAL, journal_dir(user_dir, SECTION_PERSONAL)),
    ]
    for src, dst in moves:
        if src.is_dir() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)
            except OSError:
                pass
