#!/usr/bin/env bash
# 03 — Plymouth text theme + strip quiet/rhgb so the real boot log shows
# (spec §3, §11.4). No fictional splash — real kernel/systemd messages only.
source "$(dirname "$0")/common.sh"
require_root
c_step "Boot: text Plymouth + GRUB param cleanup"

pac plymouth grub

# Plymouth: the built-in *text* theme (not a graphical splash) — real messages
# stay visible and unmodified (spec §3).
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  plymouth-set-default-theme -R details || plymouth-set-default-theme details || true
  c_ok "plymouth theme -> details (text, real log visible)"
fi

# Remove quiet and rhgb from GRUB_CMDLINE_LINUX_DEFAULT (spec §3).
GRUB_DEF=/etc/default/grub
if [[ -f "$GRUB_DEF" ]]; then
  cp -n "$GRUB_DEF" "$GRUB_DEF.foundationhub.bak" || true
  sed -i -E 's/\bquiet\b//g; s/\brhgb\b//g; s/  +/ /g; s/" /"/; s/ "/"/' "$GRUB_DEF"
  c_ok "stripped quiet/rhgb from $GRUB_DEF"
  if is_arch; then grub-mkconfig -o /boot/grub/grub.cfg; fi
else
  c_warn "$GRUB_DEF not found — if you use systemd-boot, edit the kernel cmdline there"
fi
c_ok "boot messages will now print unmodified"
