"""File manager backend (BUILD-QUEUE §2): the path-scoping guard, size
formatting, directory listing, and operation planning/execution. Pure
stdlib, no curses — `screens/files.py` composes these and the tests
exercise them headlessly.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Suffixes the in-house editor (queue §1) can sanely open. Extensionless
# files are left unopened rather than guessed at — the file manager is not
# in the business of sniffing binaries.
TEXT_SUFFIXES = {".md", ".txt", ".log", ".cfg", ".conf", ".json", ".py",
                  ".sh", ".yaml", ".yml", ".toml", ".ini", ".csv"}

_UNITS = ("B", "KB", "MB", "GB", "TB")


class ScopeError(Exception):
    """Attempted to leave the account's own data space."""


class FileOpError(Exception):
    """An operation was rejected before touching disk (bad name, collision)."""


class InvalidName(FileOpError):
    """The typed name has no usable content once path separators/dots strip."""


class NameExists(FileOpError):
    """The target name is already taken in that directory."""


# ── scope guard ───────────────────────────────────────────────────────────────

def enforce_scope(root: Path, path: Path) -> Path:
    """Resolve `path` and refuse it if it falls outside `root`. Never a
    system-wide browser — the operator has no business above their own
    space, and this catches both '..' walks and symlink escapes."""
    root_r = root.resolve()
    path_r = path.resolve()
    try:
        path_r.relative_to(root_r)
    except ValueError:
        raise ScopeError(f"outside account space: {path}") from None
    return path_r


def rel_path(root: Path, cwd: Path) -> str:
    """Display path relative to the account's root, always starting at '/'."""
    if cwd == root:
        return "/"
    return "/" + cwd.relative_to(root).as_posix()


# ── listing ──────────────────────────────────────────────────────────────────

@dataclass
class Entry:
    path: Path
    is_dir: bool
    size: int          # bytes; 0 for directories (not recursively summed)
    mtime: float


def list_dir(path: Path) -> list[Entry]:
    """Directories first, then files, each alphabetical (case-insensitive)."""
    entries: list[Entry] = []
    try:
        items = list(path.iterdir())
    except OSError:
        return []
    for p in items:
        try:
            st = p.stat()
        except OSError:
            continue
        is_dir = p.is_dir()
        entries.append(Entry(p, is_dir, 0 if is_dir else st.st_size, st.st_mtime))
    entries.sort(key=lambda e: (not e.is_dir, e.path.name.lower()))
    return entries


def dir_size(path: Path) -> int:
    """Recursive size in bytes, best-effort (unreadable entries are skipped
    rather than raising — a quota readout must never crash the screen)."""
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def format_size(n: int) -> str:
    size = float(n)
    unit_i = 0
    while size >= 1024 and unit_i < len(_UNITS) - 1:
        size /= 1024
        unit_i += 1
    if unit_i == 0:
        return f"{int(size)} {_UNITS[unit_i]}"
    return f"{size:.1f} {_UNITS[unit_i]}"


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


# ── operation planning + execution ───────────────────────────────────────────

def safe_name(name: str) -> str:
    """Sanitize a typed file/dir name: no path separators, no bare dots.
    Raises FileOpError if nothing usable remains — this is what stops a
    rename/new-dir prompt from being used as a path-escape hatch."""
    name = name.strip().replace("/", "").replace("\\", "")
    if not name or name in (".", ".."):
        raise InvalidName(name)
    return name


def plan_target(directory: Path, name: str) -> Path:
    return directory / safe_name(name)


def do_new_dir(directory: Path, name: str) -> Path:
    target = plan_target(directory, name)
    if target.exists():
        raise NameExists(name)
    target.mkdir(parents=True)
    return target


def do_rename(path: Path, name: str) -> Path:
    target = plan_target(path.parent, name)
    if target.exists():
        raise NameExists(name)
    path.rename(target)
    return target


def do_copy(path: Path, dest_dir: Path) -> Path:
    target = dest_dir / path.name
    if target.exists():
        raise NameExists(path.name)
    if path.is_dir():
        shutil.copytree(path, target)
    else:
        shutil.copy2(path, target)
    return target


def do_move(path: Path, dest_dir: Path) -> Path:
    target = dest_dir / path.name
    if target.exists():
        raise NameExists(path.name)
    shutil.move(str(path), str(target))
    return target


def do_delete(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
