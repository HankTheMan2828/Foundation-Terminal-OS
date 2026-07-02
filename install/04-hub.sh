#!/usr/bin/env bash
# 04 — install foundationhub and make it the operator's LOGIN SHELL (spec §4, §11.8).
source "$(dirname "$0")/common.sh"
require_root
c_step "Home Hub: install foundationhub, set as login shell"

pac python

# Install the Hub package. Pure-stdlib, so a plain copy onto the system path is
# enough; pip (when present) keeps it upgradeable.
install_py_dist "$REPO_ROOT/hub" foundationhub=foundationhub

# Config + data dirs (recreation list, AI Chat key file).
install -d -o root -g root -m 0755 /etc/foundationhub
install_file "etc/foundationhub/recreation.toml" "/etc/foundationhub/recreation.toml" 0644

# Record where the repo actually lives so nothing has to assume a clone path —
# helpers (foundationhub-account) search this before falling back to the
# conventional /opt/terminal-os.
echo "$REPO_ROOT" > /etc/foundationhub/install-root
chmod 0644 /etc/foundationhub/install-root
c_ok "recorded install root: $REPO_ROOT"

# ── Multi-user login (docs/USERS.md) ─────────────────────────────────────────
# Account registry: root writes (via foundationhub-account), the Hub only reads.
# Bootstrapped empty -> the login screen offers NEW OPERATOR REGISTRATION.
if [[ ! -e /etc/foundationhub/users.json ]]; then
  install -o root -g "$OPERATOR" -m 0640 /dev/null /etc/foundationhub/users.json 2>/dev/null || \
  install -o root -g root -m 0640 /dev/null /etc/foundationhub/users.json
fi
# Root-only provisioning helper + the polkit grant scoped to exactly it.
install_file "usr/local/bin/foundationhub-account" "/usr/local/bin/foundationhub-account" 0755
install -d -m 0755 /etc/polkit-1/rules.d
install_file "etc/polkit-1/rules.d/50-foundationhub-account.rules" \
             "/etc/polkit-1/rules.d/50-foundationhub-account.rules" 0644
# /run/foundationhub (active-user publication for Frank's per-user attribution).
install_file "etc/tmpfiles.d/foundationhub.conf" "/etc/tmpfiles.d/foundationhub.conf" 0644
systemd-tmpfiles --create /etc/tmpfiles.d/foundationhub.conf 2>/dev/null || true
# AI Chat key file (operator-readable, separate from Frank's key). Empty by
# default -> AI Chat runs in the clearly-labelled offline state (spec §5).
if [[ ! -e /etc/foundationhub/aichat.env ]]; then
  install -o root -g "$OPERATOR" -m 0640 /dev/null /etc/foundationhub/aichat.env 2>/dev/null || \
  install -o root -g root -m 0640 /dev/null /etc/foundationhub/aichat.env
fi

# Session wrapper must already be installed by step 02.
[[ -x /usr/local/bin/foundationhub-session ]] || \
  install_file "usr/local/bin/foundationhub-session" "/usr/local/bin/foundationhub-session" 0755

# Register the shell and set it (spec §4). After this the operator has NO bash.
grep -qx /usr/local/bin/foundationhub-session /etc/shells || \
  echo /usr/local/bin/foundationhub-session >> /etc/shells
chsh -s /usr/local/bin/foundationhub-session "$OPERATOR"
c_ok "login shell for '$OPERATOR' -> /usr/local/bin/foundationhub-session"

cat <<'EOF'
  SAFETY: keep a root shell on tty2 (Ctrl-Alt-F2) until you trust the kiosk.
  To revert:  chsh -s /bin/bash <operator>   (from any root shell)
EOF
