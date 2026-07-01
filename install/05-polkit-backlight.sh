#!/usr/bin/env bash
# 05 — replace the community project's blanket NOPASSWD sudo on /usr/bin/env
# (a broad privilege-escalation hole) with a properly SCOPED polkit rule limited
# to backlight brightness (spec §7, §11.7).
source "$(dirname "$0")/common.sh"
require_root
c_step "Security fix: scoped backlight polkit rule (no NOPASSWD sudo)"

pac brightnessctl polkit

# Scoped polkit rule: operator's group may set brightness via the
# org.freedesktop.login1 / brightnessctl path only — nothing else.
install_file "etc/polkit-1/rules.d/50-zenbook-backlight.rules" \
  "/etc/polkit-1/rules.d/50-zenbook-backlight.rules" 0644

# Actively remove the dangerous sudoers rule if a prior/community install left it.
if grep -rslE 'NOPASSWD:\s*/usr/bin/env' /etc/sudoers /etc/sudoers.d/ 2>/dev/null; then
  c_warn "found NOPASSWD /usr/bin/env sudo rule(s) — removing (privilege hole)"
  grep -rlE 'NOPASSWD:\s*/usr/bin/env' /etc/sudoers.d/ 2>/dev/null | while read -r f; do
    c_info "removing $f"; rm -f "$f"
  done
fi

c_ok "backlight privilege is now scoped via polkit; blanket sudo hole removed"
