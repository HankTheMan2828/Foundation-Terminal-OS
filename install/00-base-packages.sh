#!/usr/bin/env bash
# 00 — install the package set (spec §1, §11.1).
source "$(dirname "$0")/common.sh"
require_root
c_step "Base packages"

mapfile -t PKGS < <(sed -E 's/#.*$//; s/[[:space:]]+$//; /^[[:space:]]*$/d' "$REPO_ROOT/install/packages.txt")
c_info "installing ${#PKGS[@]} packages from packages.txt"
pac "${PKGS[@]}"

# Enable the services the later scripts rely on (idempotent).
if is_arch; then
  systemctl enable NetworkManager.service bluetooth.service \
    power-profiles-daemon.service 2>/dev/null || true
  # seatd: libseat backend for Programs → WEB ACCESS (sway/cage kiosk).
  # Harmless when the runtime prefers logind (getty session) instead.
  systemctl enable seatd.service 2>/dev/null || true
fi
c_ok "base packages done"
