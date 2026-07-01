#!/usr/bin/env bash
# 04 — install zenhub and make it the operator's LOGIN SHELL (spec §4, §11.8).
source "$(dirname "$0")/common.sh"
require_root
c_step "Home Hub: install zenhub, set as login shell"

pac python

# Install the Hub package. Pure-stdlib, so a plain copy onto the system path is
# enough; using pip keeps it upgradeable.
if is_arch && command -v pip >/dev/null 2>&1; then
  pip install --break-system-packages "$REPO_ROOT/hub" || \
    cp -r "$REPO_ROOT/hub/zenhub" /usr/lib/python3*/site-packages/ 2>/dev/null || true
fi

# Config + data dirs (recreation list, kitty include, AI Chat key file).
install -d -o root -g root -m 0755 /etc/zenhub
install_file "etc/zenhub/recreation.toml" "/etc/zenhub/recreation.toml" 0644
install_file "etc/zenhub/kitty.conf"       "/etc/zenhub/kitty.conf"       0644

# ── Multi-user login (docs/USERS.md) ─────────────────────────────────────────
# Account registry: root writes (via zenhub-account), the Hub only reads.
# Bootstrapped empty -> the login screen offers NEW OPERATOR REGISTRATION.
if [[ ! -e /etc/zenhub/users.json ]]; then
  install -o root -g "$OPERATOR" -m 0640 /dev/null /etc/zenhub/users.json 2>/dev/null || \
  install -o root -g root -m 0640 /dev/null /etc/zenhub/users.json
fi
# Root-only provisioning helper + the polkit grant scoped to exactly it.
install_file "usr/local/bin/zenhub-account" "/usr/local/bin/zenhub-account" 0755
install -d -m 0755 /etc/polkit-1/rules.d
install_file "etc/polkit-1/rules.d/50-zenhub-account.rules" \
             "/etc/polkit-1/rules.d/50-zenhub-account.rules" 0644
# /run/zenhub (active-user publication for Frank's per-user attribution).
install_file "etc/tmpfiles.d/zenhub.conf" "/etc/tmpfiles.d/zenhub.conf" 0644
systemd-tmpfiles --create /etc/tmpfiles.d/zenhub.conf 2>/dev/null || true
# AI Chat key file (operator-readable, separate from Frank's key). Empty by
# default -> AI Chat runs in the clearly-labelled offline state (spec §5).
if [[ ! -e /etc/zenhub/aichat.env ]]; then
  install -o root -g "$OPERATOR" -m 0640 /dev/null /etc/zenhub/aichat.env 2>/dev/null || \
  install -o root -g root -m 0640 /dev/null /etc/zenhub/aichat.env
fi

# Session wrapper must already be installed by step 02.
[[ -x /usr/local/bin/zenhub-session ]] || \
  install_file "usr/local/bin/zenhub-session" "/usr/local/bin/zenhub-session" 0755

# Register the shell and set it (spec §4). After this the operator has NO bash.
grep -qx /usr/local/bin/zenhub-session /etc/shells || \
  echo /usr/local/bin/zenhub-session >> /etc/shells
chsh -s /usr/local/bin/zenhub-session "$OPERATOR"
c_ok "login shell for '$OPERATOR' -> /usr/local/bin/zenhub-session"

cat <<'EOF'
  SAFETY: keep a root shell on tty2 (Ctrl-Alt-F2) until you trust the kiosk.
  To revert:  chsh -s /bin/bash <operator>   (from any root shell)
EOF
