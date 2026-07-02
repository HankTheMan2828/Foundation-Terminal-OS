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

# Pure-stdlib, so a plain copy is enough; pip keeps it upgradeable and wires up
# the console scripts (foundation-arcade, foundation-chess) that recreation.toml
# names and Launch() resolves on PATH.
if is_arch && command -v pip >/dev/null 2>&1; then
  pip install --break-system-packages "$REPO_ROOT/games" || \
    for pkg in foundation_arcade foundation_chess; do
      cp -r "$REPO_ROOT/games/$pkg" /usr/lib/python3*/site-packages/ 2>/dev/null || true
    done
fi

c_ok "in-house games installed — gnuchess retired -> foundation-chess"
