#!/usr/bin/env bash
# 02 — cage + kitty kiosk, autologin, boot to multi-user (spec §2, §4, §11.3).
source "$(dirname "$0")/common.sh"
require_root
c_step "Kiosk layer: cage + kitty, autologin"

pac cage kitty wlr-randr seatd

# Boot to multi-user.target — NO display manager, NO graphical.target (spec §2).
if is_arch; then
  systemctl set-default multi-user.target
  c_ok "default target -> multi-user.target"
fi

# Create the operator account if missing.
if ! id "$OPERATOR" >/dev/null 2>&1; then
  c_info "creating operator user '$OPERATOR'"
  useradd -m -G video,input,seat,wheel "$OPERATOR" || useradd -m "$OPERATOR"
fi

# getty autologin (spec §4 — decided: autologin straight to Hub).
install_file "etc/systemd/system/getty@tty1.service.d/autologin.conf" \
  "/etc/systemd/system/getty@tty1.service.d/autologin.conf" 0644
# Substitute the operator name into the drop-in.
sed -i "s/@OPERATOR@/$OPERATOR/g" \
  /etc/systemd/system/getty@tty1.service.d/autologin.conf

# The session wrapper that becomes the login shell in step 06.
install_file "usr/local/bin/foundationhub-session" "/usr/local/bin/foundationhub-session" 0755

if is_arch; then systemctl daemon-reload; fi
c_ok "kiosk layer configured (login shell wired in step 06)"
