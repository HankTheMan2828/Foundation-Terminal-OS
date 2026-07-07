#!/usr/bin/env bash
# 01 — pin linux-lts (spec §1).
#
# linux-lts is the generic default: a locked-down kiosk benefits from a slower,
# more predictable kernel cadence than mainline `linux`. Any device-specific
# kernel caveats (known regressions, required pins to a particular point
# release, manual verification gates) belong to a hardware profile, not here —
# see profiles/$HARDWARE_PROFILE/README.md if one is selected (step 07).
source "$(dirname "$0")/common.sh"
require_root
c_step "Kernel: linux-lts (pinned)"

# linux-lts-headers intentionally NOT installed (2026-07-07, size): this fixed
# appliance compiles no out-of-tree/DKMS modules at runtime, so headers (~200 MB
# installed) bought nothing. A hardware profile that must build a module installs
# them itself. Keep this in sync with install/packages.txt.
pac linux-lts

# Pin linux-lts against accidental replacement by the mainline `linux` package.
if is_arch && ! grep -q '^IgnorePkg.*linux\b' /etc/pacman.conf; then
  c_info "adding IgnorePkg=linux to /etc/pacman.conf (keeps you on lts)"
  sed -i 's/^#\?IgnorePkg\s*=.*/IgnorePkg = linux/' /etc/pacman.conf || \
    echo 'IgnorePkg = linux' >> /etc/pacman.conf
fi

if [[ -n "$HARDWARE_PROFILE" ]]; then
  c_info "HARDWARE_PROFILE=$HARDWARE_PROFILE — check profiles/$HARDWARE_PROFILE/README.md for any kernel-specific gates before continuing"
fi
c_ok "linux-lts installed and pinned"
