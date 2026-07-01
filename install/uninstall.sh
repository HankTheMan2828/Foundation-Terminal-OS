#!/usr/bin/env bash
# Reverse the risky changes so you can recover a normal system (docs/INSTALL.md).
# Run as root from a rescue shell (Ctrl-Alt-F2 or live USB).
#   --purge   also delete /var/lib/frank (incident data). Off by default.
source "$(dirname "$0")/common.sh"
require_root
c_step "Uninstall / recover"

PURGE=0; [[ "${1:-}" == "--purge" ]] && PURGE=1

# 1) Give the operator a real shell back (spec §4 reversal).
if id "$OPERATOR" >/dev/null 2>&1; then
  chsh -s /bin/bash "$OPERATOR" && c_ok "restored $OPERATOR shell -> /bin/bash"
fi

# 2) Disable autologin + kiosk.
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
c_ok "removed tty1 autologin drop-in"

# 3) Stop + mask Frank (spec §6 process is normally unkillable from a session;
#    this runs as root from rescue, which is the intended recovery path).
if is_arch; then
  systemctl disable --now frankd.service frank-enforcer.service frank-ledger.service 2>/dev/null || true
  # Release any console lock the enforcer was holding, restore tty1 autologin.
  pkill -f /usr/local/bin/frank-locker 2>/dev/null || true
  systemctl start getty@tty1.service 2>/dev/null || true
  systemctl daemon-reload
fi
c_ok "stopped Frank services (this is the root/rescue recovery path, not an in-session one)"

# 4) Optionally purge incident data.
if [[ $PURGE -eq 1 ]]; then
  rm -rf /var/lib/frank && c_warn "purged /var/lib/frank (incident data gone)"
else
  c_info "kept /var/lib/frank (pass --purge to delete)"
fi

c_ok "recovery complete. multi-user.target still set; run 'systemctl set-default graphical.target' only if you install a DE."
