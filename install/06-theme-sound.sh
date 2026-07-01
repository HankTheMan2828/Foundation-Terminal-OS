#!/usr/bin/env bash
# 06 — CRT visual theme + retro soundscape (spec §8, §10, §11.10).
source "$(dirname "$0")/common.sh"
require_root
c_step "Theme + sound"

# kitty CRT config (amber default, scanline/glow) already installed to
# /etc/zenhub/kitty.conf by step 06; refresh it here in case theme changed.
install_file "etc/zenhub/kitty.conf" "/etc/zenhub/kitty.conf" 0644

# Optional: bitmap font for the phosphor look (spec §2).
pac terminus-font || true

# Sound: install the per-session sound daemon + assets (spec §8).
if [[ -d "$REPO_ROOT/sounds" ]]; then
  install -Dm0755 "$REPO_ROOT/sounds/zenhub-sound" /usr/local/bin/zenhub-sound 2>/dev/null || true
  install -d /usr/share/zenhub/sounds
  cp -n "$REPO_ROOT"/sounds/assets/* /usr/share/zenhub/sounds/ 2>/dev/null || true
  c_ok "sound daemon + assets installed (assets are placeholders — see sounds/README.md)"
fi

cat <<'EOF'
  NOTE: sound/visual assets are placeholders in v1. Boot chimes, ambient hum,
  error buzzes, and the scanline/glow tuning are a dedicated later pass
  (spec §11.10). Everything is wired; the .wav files are stubs. [TODO]
EOF
c_ok "theme + sound scaffolding installed"
