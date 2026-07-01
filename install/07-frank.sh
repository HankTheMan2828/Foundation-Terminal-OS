#!/usr/bin/env bash
# 07 — install Frank as an ISOLATED system daemon (spec §6, §11.9).
# The operator must not be able to read Frank's config/logs, edit thresholds
# (beyond the one sensitivity knob via IPC), or kill the process.
source "$(dirname "$0")/common.sh"
require_root
c_step "Frank: overseer daemon + isolation"

pac python

# Dedicated system user, no login, own home. This is the core of isolation.
if ! id frank >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/frank --create-home --shell /usr/sbin/nologin frank
  c_ok "created system user 'frank'"
fi

# Install the daemon package.
if is_arch && command -v pip >/dev/null 2>&1; then
  pip install --break-system-packages "$REPO_ROOT/frank" || \
    cp -r "$REPO_ROOT/frank/frankd" /usr/lib/python3*/site-packages/ 2>/dev/null || true
fi

# --- config: root:frank, operator CANNOT read (spec §6) ---
install -d -o root -g frank -m 0750 /etc/frank
install -d -o root -g frank -m 0750 /etc/frank/rules.d
install -o root -g frank -m 0640 "$REPO_ROOT/system/etc/frank/config.toml" /etc/frank/config.toml
for r in "$REPO_ROOT"/system/etc/frank/rules.d/*.toml; do
  install -o root -g frank -m 0640 "$r" "/etc/frank/rules.d/$(basename "$r")"
done
# Frank's Mistral key (root:frank, operator can't read). Empty -> offline mode.
[[ -e /etc/frank/secrets.env ]] || \
  install -o root -g frank -m 0640 /dev/null /etc/frank/secrets.env

# --- state: frank:frank 0700; incidents.db + ledger frank-only (spec §6) ---
install -d -o frank -g frank -m 0700 /var/lib/frank
install -d -o frank -g frank -m 0755 /run/frank 2>/dev/null || true

# --- services ---
install_file "etc/systemd/system/frankd.service" "/etc/systemd/system/frankd.service" 0644
install_file "etc/systemd/system/frank-ledger.service" "/etc/systemd/system/frank-ledger.service" 0644
if is_arch; then
  systemctl daemon-reload
  systemctl enable --now frankd.service 2>/dev/null || true
  systemctl enable frank-ledger.service 2>/dev/null || true
fi

# --- verify isolation (spec §6 / docs/INSTALL.md §4) ---
c_step "Isolation checks (all must be DENIED)"
fail=0
sudo -u "$OPERATOR" cat /etc/frank/config.toml    >/dev/null 2>&1 && { c_warn "operator CAN read config.toml"; fail=1; } || c_ok "config.toml: denied"
sudo -u "$OPERATOR" cat /var/lib/frank/incidents.db >/dev/null 2>&1 && { c_warn "operator CAN read incidents.db"; fail=1; } || c_ok "incidents.db: denied"
if [[ $fail -ne 0 ]]; then
  c_warn "ISOLATION BROKEN — see docs/ARCHITECTURE.md 'Frank isolation'"; exit 1
fi
c_ok "Frank installed and isolated"
