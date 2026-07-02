#!/usr/bin/env bash
# 09 — install the in-house media player (BUILD-QUEUE §4). A standalone program,
# not a Hub screen (hybrid model): installed like the Hub itself, then launched
# by Programs → MEDIA via Launch(["foundationmedia"]).
#
# Playback backend (operator-approved hybrid, OPEN-QUESTIONS.md §10): the
# in-house core is pure-stdlib WAV/AIFF decode + ctypes ALSA output (alsa-lib);
# ffmpeg is an optional broad-format decode ENGINE under the in-house UI —
# without it the player still runs, WAV/AIFF-only (the Pocket8086-tier story).
source "$(dirname "$0")/common.sh"
require_root
c_step "Media: install the in-house player (foundationmedia)"

pac python alsa-lib ffmpeg

# Pure-stdlib + ctypes, so a plain copy is enough; pip keeps it upgradeable and
# wires up the `foundationmedia` console script that Launch() resolves on PATH.
if is_arch && command -v pip >/dev/null 2>&1; then
  pip install --break-system-packages "$REPO_ROOT/media" || \
    cp -r "$REPO_ROOT/media/foundationmedia" /usr/lib/python3*/site-packages/ 2>/dev/null || true
fi

c_ok "in-house media player installed — cmus/mpv stay retired -> foundationmedia"
