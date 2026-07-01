"""Entry point: ``python -m zenhub``.

Because the Hub is the login shell (spec §4), this must be robust: any unhandled
error should restore the terminal and exit cleanly (which logs the session out)
rather than leaving a broken screen or — worse — dropping to a shell.

Boot lands on the LOGIN screen (docs/USERS.md), not the Hub. Setting
ZENHUB_USER=<name> skips login and enters the Hub as that account — the dev
shortcut, and the hook for a future real per-user session start
[TODO(hardware)].
"""
from __future__ import annotations

import curses
import os
import sys

from . import session, theme
from .app import App
from .screens import build_home


def _main(stdscr) -> None:
    theme.init(stdscr)
    preset = os.environ.get("ZENHUB_USER")
    if preset:
        from .accounts import Registry
        session.set_active_account(Registry().get(preset))
        root = build_home
    else:
        from .screens.login import build_entry
        root = build_entry
    App(stdscr, root).run()


def main() -> int:
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # never leave a half-drawn screen on the login shell
        sys.stderr.write(f"zenhub exited: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
