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

# FOUNDATION_UPDATE=1: this run is refreshing an existing install (UPDATE mode,
# docs/UPDATE-SYSTEM.md §4) — steps must refresh code/units but NO-CLOBBER any
# machine or user state (Frank state, tuned configs, Settings choices).
is_update() { [[ "${FOUNDATION_UPDATE:-0}" == "1" ]]; }

# Install packages idempotently. No-op (with a note) off Arch so scripts can be
# dry-read / partially exercised elsewhere. FOUNDATION_OFFLINE=1 (set by the
# flashable-ISO installer, image/) means every package was already laid down by
# pacstrap from the ISO's embedded repo — just verify instead of hitting the
# network.
pac() {
  if ! is_arch; then
    c_warn "not Arch (no pacman) — would install: $*"; return 0
  fi
  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    local missing=()
    local p
    for p in "$@"; do pacman -Qq "$p" >/dev/null 2>&1 || missing+=("$p"); done
    if ((${#missing[@]})); then
      c_warn "offline install: not present and cannot fetch: ${missing[*]}"
      c_warn "add them to the ISO's package list (image/) and rebuild"
    fi
    return 0
  fi
  pacman -S --needed --noconfirm "$@"
}

# Install one of the repo's pure-stdlib Python distributions. pip when it's
# available and works (wires real console-script entry points); otherwise copy
# the package(s) into site-packages and shim each console script with a
# `python -m` wrapper on PATH — so an offline install (the flashable ISO) ends
# up with the exact same commands available as an online one.
install_py_dist() {  # srcdir  [script-name=module ...]
  local src="$1"; shift
  if ! is_arch; then
    c_warn "not Arch — would install python dist: $src"; return 0
  fi
  if command -v pip >/dev/null 2>&1 && \
     pip install --break-system-packages "$src"; then
    c_ok "pip installed $(basename "$src")"
    return 0
  fi
  local sitedir
  sitedir="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  local pair name module pkg
  for pair in "$@"; do
    name="${pair%%=*}"; module="${pair#*=}"
    pkg="${module%%.*}"   # the module may be dotted (frankd.daemon); the
                          # directory to copy is its top-level package
    rm -rf "${sitedir:?}/$pkg"
    cp -r "$src/$pkg" "$sitedir/"
    printf '#!/bin/sh\nexec python -m %s "$@"\n' "$module" > "/usr/local/bin/$name"
    chmod 0755 "/usr/local/bin/$name"
    c_ok "copied $pkg -> $sitedir (shim: /usr/local/bin/$name)"
  done
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
