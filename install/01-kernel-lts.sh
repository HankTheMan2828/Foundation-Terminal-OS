#!/usr/bin/env bash
# 01 — pin linux-lts and gate on the second-screen check (spec §1, §11.2).
#
# The Zenbook Duo bottom panel (eDP-2) has a known i915 regression on 6.9+;
# last confirmed-good mainline was 6.8.12. linux-lts avoids chasing this. If the
# current lts point release STILL shows the bug, pin a known-good build from the
# Arch Linux Archive (instructions printed below).
source "$(dirname "$0")/common.sh"
require_root
c_step "Kernel: linux-lts (pinned)"

pac linux-lts linux-lts-headers

# Pin linux-lts against accidental replacement by the mainline `linux` package.
if is_arch && ! grep -q '^IgnorePkg.*linux\b' /etc/pacman.conf; then
  c_info "adding IgnorePkg=linux to /etc/pacman.conf (keeps you on lts)"
  sed -i 's/^#\?IgnorePkg\s*=.*/IgnorePkg = linux/' /etc/pacman.conf || \
    echo 'IgnorePkg = linux' >> /etc/pacman.conf
fi

cat <<'EOF'

  ┌─ MANUAL GATE (spec §11.2) ────────────────────────────────────────────────┐
  │ Before continuing, boot linux-lts and confirm the BOTTOM panel works.      │
  │ From inside a cage session (after step 02) run:                            │
  │                                                                            │
  │     wlr-randr        # must list BOTH eDP-1 and eDP-2, no glitching        │
  │                                                                            │
  │ If eDP-2 is missing/glitchy, this lts point release has the i915 bug.      │
  │ Pin a known-good kernel (target 6.8.12) from the Arch Linux Archive:       │
  │                                                                            │
  │   1) Find a good build at https://archive.archlinux.org/packages/l/linux-lts/ │
  │   2) pacman -U https://archive.../linux-lts-<good-version>-x86_64.pkg.tar.zst │
  │   3) keep IgnorePkg = linux linux-lts   in /etc/pacman.conf                │
  │                                                                            │
  │ Do NOT build the rest on a kernel where the second screen is broken.       │
  └────────────────────────────────────────────────────────────────────────────┘
EOF
c_ok "linux-lts installed and pinned"
