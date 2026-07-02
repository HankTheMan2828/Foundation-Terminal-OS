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

# Pure-stdlib + ctypes, so a plain copy is enough; pip (when present) wires the
# real console script, otherwise install_py_dist shims `foundationmedia` onto
# PATH so Launch() still resolves it.
install_py_dist "$REPO_ROOT/media" foundationmedia=foundationmedia

c_ok "in-house media player installed — cmus/mpv stay retired -> foundationmedia"
