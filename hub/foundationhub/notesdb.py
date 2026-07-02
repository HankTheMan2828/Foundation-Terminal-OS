"""Notes database (BUILD-QUEUE §1): tag parsing, scanning, search.

Pure stdlib, no curses — the notes screens compose these functions and the
tests exercise them headlessly. Notes are plain `.md` files on disk
(portable, greppable, quota-friendly): `journal/YYYY-MM-DD.md` for the dated
journal, `notes/<slug>.md` for tagged notes. Tags are inline `#tag` tokens
in the body; there is no sidecar index to corrupt — every lookup re-reads
the files, which stay small by nature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

JOURNAL_DIR = "journal"
NOTES_DIR = "notes"

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


def list_journal(user_dir: Path) -> list[Path]:
    """Journal entries, newest first (date-stamped names sort that way)."""
    d = user_dir / JOURNAL_DIR
    if not d.is_dir():
        return []
    return sorted(d.glob("*.md"), key=lambda p: p.name, reverse=True)


def list_notes(user_dir: Path) -> list[Path]:
    """Tagged notes, alphabetical."""
    d = user_dir / NOTES_DIR
    if not d.is_dir():
        return []
    return sorted(d.glob("*.md"), key=lambda p: p.name)


def note_tags(path: Path) -> list[str]:
    try:
        return extract_tags(path.read_text(encoding="utf-8"))
    except OSError:
        return []


@dataclass
class Hit:
    """One matching file with a one-line snippet for the results list."""
    path: Path
    kind: str          # "journal" | "note"
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


def search(user_dir: Path, query: str) -> list[Hit]:
    """AND-match `query` across journal + notes. Every `#tag` must be in the
    file's tag set and every term a substring of its text (case-insensitive)."""
    tags, terms = parse_query(query)
    if not tags and not terms:
        return []
    hits: list[Hit] = []
    for kind, paths in (("journal", list_journal(user_dir)),
                        ("note", list_notes(user_dir))):
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            lower = text.lower()
            file_tags = extract_tags(text)
            if all(t in file_tags for t in tags) and \
               all(t in lower for t in terms):
                hits.append(Hit(path, kind, _snippet(text, tags, terms)))
    return hits
