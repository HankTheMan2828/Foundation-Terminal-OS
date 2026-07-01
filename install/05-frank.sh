#!/usr/bin/env bash
# 05 — install Frank as an ISOLATED system daemon (spec §6, §11.9).
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

# --- lock state file: frank writes, root reads, operator DENIED (spec §6) ---
install -o frank -g frank -m 0640 /dev/null /var/lib/frank/lockout.state

# --- root enforcer: applies lockouts the operator cannot bypass (spec §6) ---
install -Dm0755 -o root -g root "$REPO_ROOT/system/usr/local/bin/frank-enforcer" /usr/local/bin/frank-enforcer
install -Dm0755 -o root -g root "$REPO_ROOT/system/usr/local/bin/frank-locker" /usr/local/bin/frank-locker

# --- services ---
# frank-ledger.service is NOT installed here: it pipes the ledger to a second
# display on keyboard detach, which only exists as a concept on hardware
# profiles that have one. A profile providing that feature installs its own
# frank-ledger.service (see profiles/zenbook-duo-2024/system/etc/systemd/system/).
install_file "etc/systemd/system/frankd.service" "/etc/systemd/system/frankd.service" 0644
install_file "etc/systemd/system/frank-enforcer.service" "/etc/systemd/system/frank-enforcer.service" 0644
if is_arch; then
  systemctl daemon-reload
  systemctl enable --now frankd.service 2>/dev/null || true
  systemctl enable --now frank-enforcer.service 2>/dev/null || true
fi

# --- verify isolation (spec §6 / docs/INSTALL.md §4) ---
# The operator must have NO power over Frank: cannot read its config/data/lock
# state, cannot stop any Frank service, cannot influence detection/enforcement.
c_step "Isolation checks (all must be DENIED)"
fail=0
chk_denied() {  # description ; command...
  local desc="$1"; shift
  if sudo -u "$OPERATOR" "$@" >/dev/null 2>&1; then
    c_warn "operator CAN $desc"; fail=1
  else
    c_ok "$desc: denied"
  fi
}
chk_denied "read config.toml"     cat /etc/frank/config.toml
chk_denied "read incidents.db"    cat /var/lib/frank/incidents.db
chk_denied "read lockout.state"   cat /var/lib/frank/lockout.state
if is_arch; then
  chk_denied "stop frankd"          systemctl stop frankd.service
  chk_denied "stop frank-enforcer"  systemctl stop frank-enforcer.service
fi
# No sudoers/polkit path may grant the operator control over any Frank unit.
if sudo -u "$OPERATOR" sudo -n systemctl stop frankd.service >/dev/null 2>&1; then
  c_warn "operator has a sudo path to stop frankd"; fail=1
else
  c_ok "no operator sudo path to Frank: confirmed"
fi
if [[ $fail -ne 0 ]]; then
  c_warn "ISOLATION BROKEN — the operator has power over Frank. See docs/ARCHITECTURE.md"; exit 1
fi
c_ok "Frank installed and isolated — operator has no power over it"
