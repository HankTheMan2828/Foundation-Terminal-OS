#!/usr/bin/env bash
# 06 — CRT visual theme + retro soundscape (spec §8, §10, §11.10).
source "$(dirname "$0")/common.sh"
require_root
c_step "Theme + sound"

# Console CRT look (spec §2): the VT font and phosphor palette are applied
# per-session by foundationhub-session (setfont + VT palette escapes) — a
# kernel console feature, no display stack involved. Nothing to install here
# beyond the font package (also in packages.txt; kept for standalone runs).
pac terminus-font || true

# Sound: install the per-session sound daemon + assets (spec §8).
if [[ -d "$REPO_ROOT/sounds" ]]; then
  install -Dm0755 "$REPO_ROOT/sounds/foundationhub-sound" /usr/local/bin/foundationhub-sound 2>/dev/null || true
  install -d /usr/share/foundationhub/sounds
  cp -n "$REPO_ROOT"/sounds/assets/* /usr/share/foundationhub/sounds/ 2>/dev/null || true
  c_ok "sound daemon + assets installed (assets are placeholders — see sounds/README.md)"
fi

cat <<'EOF'
  NOTE: sound/visual assets are placeholders in v1. Boot chimes, ambient hum,
  error buzzes, and the scanline/glow tuning are a dedicated later pass
  (spec §11.10). Everything is wired; the .wav files are stubs. [TODO]
EOF
c_ok "theme + sound scaffolding installed"
