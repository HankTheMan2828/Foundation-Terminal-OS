#!/usr/bin/env bash
# 00 — install the package set (spec §1, §11.1).
source "$(dirname "$0")/common.sh"
require_root
c_step "Base packages"

mapfile -t PKGS < <(grep -vE '^\s*(#|$)' "$REPO_ROOT/install/packages.txt")
c_info "installing ${#PKGS[@]} packages from packages.txt"
pac "${PKGS[@]}"

# Enable the services the later scripts rely on (idempotent).
if is_arch; then
  systemctl enable seatd.service NetworkManager.service bluetooth.service \
    power-profiles-daemon.service 2>/dev/null || true
fi
c_ok "base packages done"
