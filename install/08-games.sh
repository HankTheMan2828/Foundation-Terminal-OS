#!/usr/bin/env bash
# 08 — install the in-house game programs (BUILD-QUEUE §5). Standalone programs,
# not Hub screens (hybrid model): installed like the Hub itself, then launched
# by Recreation via Launch([...]). One `games/` distribution ships every game
# program as its own package + console script (see games/pyproject.toml):
#   foundation-arcade (§5 item 1)   foundation-chess (§5 item 2, retires gnuchess)
source "$(dirname "$0")/common.sh"
require_root
c_step "Recreation: install the in-house game programs"

pac python

# Pure-stdlib, so a plain copy is enough; pip (when present) wires the real
# console scripts, otherwise install_py_dist shims foundation-arcade /
# foundation-chess onto PATH so recreation.toml's Launch() names still resolve.
install_py_dist "$REPO_ROOT/games" \
  foundation-arcade=foundation_arcade foundation-chess=foundation_chess

# Game records: ONE system-wide store per game (operator correction
# 2026-07-04, applies to the arcade's high scores AND chess's win/loss/draw
# tally alike) — lives under /var/lib, outside any account's quota'd
# ~/.local/share/foundationhub space, so it never shows up in a user's
# files. Owned by the operator (the single Linux user hosting sessions,
# see hub/foundationhub/session.py) so games can write to it directly.
install -d -o "$OPERATOR" -g "$OPERATOR" -m 0755 /var/lib/foundationhub

c_ok "in-house games installed — gnuchess retired -> foundation-chess"
