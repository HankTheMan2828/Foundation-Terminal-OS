#!/usr/bin/env bash
# 10 — update system (docs/UPDATE-SYSTEM.md; feedback item 11).
# Three pieces, none of them a daemon:
#   * /etc/foundation-release   — version identity (what this machine runs)
#   * /etc/foundation-update.conf — per-machine transport policy (no-clobber)
#   * foundation-update         — the ROOT update helper (network path), plus
#                                 its polkit grant, same scoped-pkexec pattern
#                                 as foundationhub-account
source "$(dirname "$0")/common.sh"
require_root
c_step "Update system: version identity + transport policy + root helper"

# --- version identity (docs/UPDATE-SYSTEM.md §2) -----------------------------
# VERSION is stamped into the repo tree by image/build-iso.sh (and into the
# network payload by CI). A dev-tree install falls back to git, then to an
# honest "unversioned".
_ver="unversioned"; _built=""
if [[ -f "$REPO_ROOT/VERSION" ]]; then
  _ver="$(sed -n 's/^version=//p' "$REPO_ROOT/VERSION" | head -1)"
  _built="$(sed -n 's/^built=//p' "$REPO_ROOT/VERSION" | head -1)"
elif git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  _ver="dev-$(git -C "$REPO_ROOT" describe --tags --always 2>/dev/null || echo unknown)"
fi
[[ -n "$_ver" ]] || _ver="unversioned"

RELEASE=/etc/foundation-release
_action="installed"
_profile="$HARDWARE_PROFILE"
_history=""
if [[ -e "$RELEASE" ]]; then
  _action="updated"
  # An update never re-asks the profile question — reuse what was recorded.
  [[ -n "$_profile" ]] || _profile="$(sed -n 's/^profile=//p' "$RELEASE" | head -1)"
  _history="$(grep '^history=' "$RELEASE" || true)"
fi
{
  printf 'version=%s\n' "$_ver"
  [[ -n "$_built" ]] && printf 'built=%s\n' "$_built"
  printf 'profile=%s\n' "$_profile"
  [[ -n "$_history" ]] && printf '%s\n' "$_history"
  printf 'history=%s %s %s\n' "$_action" "$(date -u +%Y-%m-%d)" "$_ver"
} > "$RELEASE"
chmod 0644 "$RELEASE"
c_ok "$RELEASE: $_ver ($_action)"

# --- transport policy (docs/UPDATE-SYSTEM.md §3) -----------------------------
# No-clobber: the policy is a per-machine choice; an update never loosens or
# tightens it behind the operator's back.
if [[ ! -e /etc/foundation-update.conf ]]; then
  install_file "etc/foundation-update.conf" "/etc/foundation-update.conf" 0644
else
  c_ok "transport policy preserved: $(sed -n 's/^transports *= *//p' /etc/foundation-update.conf | head -1)"
fi

# --- network-path helper (docs/UPDATE-SYSTEM.md §5) --------------------------
# Root-owned fixed logic; the Hub reaches it only via pkexec under the scoped
# polkit rule, and the helper itself revalidates the technician setup code.
install_file "usr/local/bin/foundation-update" "/usr/local/bin/foundation-update" 0755
install -d -m 0755 /etc/polkit-1/rules.d
install_file "etc/polkit-1/rules.d/50-foundation-update.rules" \
             "/etc/polkit-1/rules.d/50-foundation-update.rules" 0644
# Staging area for downloads (root-owned; never operator-writable).
install -d -o root -g root -m 0700 /var/lib/foundation-update

c_ok "update system installed (no daemon — updates run only when asked)"
