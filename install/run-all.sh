#!/usr/bin/env bash
# Run every install step in order (spec §11). Idempotent; safe to re-run.
# For the FIRST install, prefer running steps individually so you can hit any
# manual gates a hardware profile prints (see docs/INSTALL.md).
#
# Steps 00-06 are the generic core — no device assumed. Step 07 is the optional
# hardware profile (see docs/PROFILES.md); set HARDWARE_PROFILE=<name> to apply
# one, e.g.:  HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh
source "$(dirname "$0")/common.sh"
require_root

c_warn "This turns THIS machine into a no-shell kiosk with an overseer."
c_warn "Read docs/INSTALL.md first. Keep a root shell on tty2 as a safety net."
if [[ -n "$HARDWARE_PROFILE" ]]; then
  c_info "hardware profile: $HARDWARE_PROFILE"
else
  c_info "no hardware profile selected — generic core only (see docs/PROFILES.md)"
fi
read -rp "Continue? [y/N] " ans
[[ "${ans,,}" == "y" ]] || { c_info "aborted"; exit 0; }

for step in \
  00-base-packages 01-kernel 02-cage-kiosk 03-plymouth-grub \
  04-hub 05-frank 06-theme-sound 07-hardware-profile; do
  "$REPO_ROOT/install/$step.sh"
done

c_step "Done"
c_ok "Reboot to boot straight into the Home Hub."
c_info "Verify Frank isolation: docs/INSTALL.md §4."
