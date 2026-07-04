#!/usr/bin/env bash
# 02 — kernel-console kiosk + autologin, boot to multi-user (spec §2, §4, §11.3).
#
# There is deliberately NO display stack here: no compositor, no graphical
# terminal, no GPU/DRM requirement. The Hub runs with curses directly on the
# kernel VT. A hardware profile whose device glue needs a display stack
# installs its own on top (see docs/PROFILES.md).
source "$(dirname "$0")/common.sh"
require_root
c_step "Console kiosk: autologin straight to the kernel VT"

# Boot to multi-user.target — NO display manager, NO graphical.target (spec §2).
if is_arch; then
  systemctl set-default multi-user.target
  c_ok "default target -> multi-user.target"
fi

# Create the operator account if missing.
if ! id "$OPERATOR" >/dev/null 2>&1; then
  c_info "creating operator user '$OPERATOR'"
  useradd -m -G video,input,wheel "$OPERATOR" || useradd -m "$OPERATOR"
fi

# Console text size (feedback #1). Persist the machine's font face where both
# the session wrapper (reads it at login) and the Hub's Functions > TEXT SIZE
# (rewrites it live) can reach it. Operator-owned so the in-Hub change sticks
# across reboots without a root helper. Default is the 2× face; the flashable
# ISO installer overrides FOUNDATION_CONSOLE_FONT from its setup question.
install -d -m0755 /etc/foundationhub
if is_update && [[ -e /etc/foundationhub/console-font ]]; then
  # UPDATE mode (docs/UPDATE-SYSTEM.md §4): the machine's TEXT SIZE choice is
  # state, not payload — it survives.
  c_ok "console text size preserved: $(cat /etc/foundationhub/console-font)"
else
  _font="${FOUNDATION_CONSOLE_FONT:-ter-v32b}"
  printf '%s\n' "$_font" > /etc/foundationhub/console-font
  chmod 0644 /etc/foundationhub/console-font
  chown "$OPERATOR" /etc/foundationhub/console-font 2>/dev/null || true
  c_ok "console text size -> $_font (Settings > TEXT SIZE can change it)"
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
c_ok "console kiosk configured (login shell wired in step 06)"
