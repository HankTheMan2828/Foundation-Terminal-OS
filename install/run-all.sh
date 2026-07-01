#!/usr/bin/env bash
# Run every install step in order (spec §11). Idempotent; safe to re-run.
# For the FIRST install, prefer running steps individually so you can hit the
# manual second-screen gate in step 01 (see docs/INSTALL.md).
source "$(dirname "$0")/common.sh"
require_root

c_warn "This turns THIS machine into a no-shell kiosk with an overseer."
c_warn "Read docs/INSTALL.md first. Keep a root shell on tty2 as a safety net."
read -rp "Continue? [y/N] " ans
[[ "${ans,,}" == "y" ]] || { c_info "aborted"; exit 0; }

for step in \
  00-base-packages 01-kernel-lts 02-cage-kiosk 03-plymouth-grub \
  04-hardware-zenbook 05-polkit-backlight 06-hub 07-frank 08-theme-sound; do
  "$REPO_ROOT/install/$step.sh"
done

c_step "Done"
c_ok "Reboot to boot straight into the Home Hub."
c_info "Verify Frank isolation: docs/INSTALL.md §4."
