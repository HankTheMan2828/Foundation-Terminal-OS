#!/usr/bin/env bash
# Reverse this profile's changes. Called by install/uninstall.sh when
# HARDWARE_PROFILE=zenbook-duo-2024 is set; safe to run standalone as root too.
set -euo pipefail
PROFILE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../install/common.sh
source "$PROFILE_ROOT/../../install/common.sh"
require_root
c_step "Reversing hardware profile: zenbook-duo-2024"

if is_arch; then
  systemctl disable --now duo-battery-limit.service duo-hardware.service frank-ledger.service 2>/dev/null || true
  systemctl daemon-reload
fi
rm -f /etc/systemd/system/duo-battery-limit.service /etc/systemd/system/duo-hardware.service \
      /etc/systemd/system/frank-ledger.service
rm -f /etc/udev/rules.d/90-zenbook-duo.rules
rm -f /etc/polkit-1/rules.d/50-zenbook-backlight.rules
rm -f /usr/local/lib/zenhub/duo-screen-toggle /usr/local/lib/zenhub/duo-watch-displays \
      /usr/local/lib/zenhub/duo-keyboard-detach /usr/local/lib/zenhub/backlight-sync \
      /usr/local/lib/zenhub/duo-battery-limit
is_arch && udevadm control --reload-rules || true

c_ok "zenbook-duo-2024 profile glue removed (generic core untouched)"
