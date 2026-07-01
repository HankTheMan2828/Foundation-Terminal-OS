#!/usr/bin/env bash
# Shared helpers for the installer scripts. Sourced, not run directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

# The operator account the kiosk logs into (spec §4). Override: OPERATOR=name ...
OPERATOR="${OPERATOR:-operator}"
export OPERATOR

# Optional hardware profile (see profiles/, docs/PROFILES.md). Empty = generic
# core only, no device-specific glue installed. Override: HARDWARE_PROFILE=name ...
HARDWARE_PROFILE="${HARDWARE_PROFILE:-}"
export HARDWARE_PROFILE
PROFILE_DIR=""
[[ -n "$HARDWARE_PROFILE" ]] && PROFILE_DIR="$REPO_ROOT/profiles/$HARDWARE_PROFILE"
export PROFILE_DIR

c_info()  { printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
c_ok()    { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
c_warn()  { printf '\033[1;31m[!]\033[0m %s\n' "$*"; }
c_step()  { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    c_warn "must run as root: sudo $0"; exit 1
  fi
}

is_arch() { command -v pacman >/dev/null 2>&1; }

# Install packages idempotently. No-op (with a note) off Arch so scripts can be
# dry-read / partially exercised elsewhere.
pac() {
  if ! is_arch; then
    c_warn "not Arch (no pacman) — would install: $*"; return 0
  fi
  pacman -S --needed --noconfirm "$@"
}

# Copy a file from system/ tree onto / preserving intended perms.
install_file() {  # src(relative to system/) dest mode owner group
  local rel="$1" dest="$2" mode="${3:-0644}" owner="${4:-root}" group="${5:-root}"
  local src="$REPO_ROOT/system/$rel"
  install -Dm"$mode" -o "$owner" -g "$group" "$src" "$dest"
  c_ok "installed $dest ($mode $owner:$group)"
}

# Same, but from the active hardware profile's system/ tree (profiles/$HARDWARE_PROFILE/system/).
install_profile_file() {  # src(relative to profile's system/) dest mode owner group
  local rel="$1" dest="$2" mode="${3:-0644}" owner="${4:-root}" group="${5:-root}"
  if [[ -z "$PROFILE_DIR" ]]; then
    c_warn "install_profile_file called with no HARDWARE_PROFILE set — skipping $dest"; return 0
  fi
  local src="$PROFILE_DIR/system/$rel"
  install -Dm"$mode" -o "$owner" -g "$group" "$src" "$dest"
  c_ok "installed $dest ($mode $owner:$group) [profile: $HARDWARE_PROFILE]"
}
