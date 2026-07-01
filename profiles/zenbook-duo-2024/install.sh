#!/usr/bin/env bash
# Hardware profile: Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor Lake.
# Invoked by install/07-hardware-profile.sh when HARDWARE_PROFILE=zenbook-duo-2024.
# See README.md in this directory for what this profile targets and why.
set -euo pipefail
PROFILE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../install/common.sh
source "$PROFILE_ROOT/../../install/common.sh"
require_root
c_step "Hardware profile: zenbook-duo-2024"

# --- profile-specific packages ---
mapfile -t PKGS < <(grep -vE '^\s*(#|$)' "$PROFILE_ROOT/packages.txt")
c_info "installing ${#PKGS[@]} profile packages"
pac "${PKGS[@]}"

# --- kernel caveat: known i915 regression on the bottom panel (eDP-2) ---
# Ported from the community reference (alesya-h/zenbook-duo-2024-ux8406ma-linux):
# eDP-2 has a known i915 regression on mainline 6.9+; last confirmed-good was
# 6.8.12. install/01-kernel.sh already pins linux-lts generically; this profile
# just adds the manual verification gate, since only THIS device needs it.
cat <<'EOF'

  ┌─ MANUAL GATE (profile: zenbook-duo-2024) ─────────────────────────────────┐
  │ Before continuing, confirm the BOTTOM panel (eDP-2) actually works on the  │
  │ installed kernel. From inside a cage session (after install/02) run:       │
  │                                                                            │
  │     wlr-randr        # must list BOTH eDP-1 and eDP-2, no glitching        │
  │                                                                            │
  │ If eDP-2 is missing/glitchy, this lts point release has the i915 bug.      │
  │ Pin a known-good kernel (target 6.8.12) from the Arch Linux Archive:       │
  │                                                                            │
  │   1) https://archive.archlinux.org/packages/l/linux-lts/                   │
  │   2) pacman -U https://archive.../linux-lts-<good-version>-x86_64.pkg.tar.zst │
  │   3) keep IgnorePkg = linux linux-lts   in /etc/pacman.conf                │
  │                                                                            │
  │ Do NOT continue on a kernel where the second screen is broken.             │
  └────────────────────────────────────────────────────────────────────────────┘
EOF

# --- hardware helper scripts, referenced by the Hub via ZENHUB_HW_BIN (spec §7) ---
install -d /usr/local/lib/zenhub
for f in duo-screen-toggle duo-watch-displays duo-keyboard-detach \
         backlight-sync duo-battery-limit; do
  install -Dm0755 "$PROFILE_ROOT/hardware/$f" "/usr/local/lib/zenhub/$f"
  c_ok "installed /usr/local/lib/zenhub/$f"
done

# --- udev: keyboard detach/attach + eDP-2 backlight naming ---
install -Dm0644 "$PROFILE_ROOT/system/etc/udev/rules.d/90-zenbook-duo.rules" \
  /etc/udev/rules.d/90-zenbook-duo.rules
c_ok "installed udev rules"

# --- scoped polkit rule for backlight (replaces any blanket NOPASSWD sudo hole) ---
install -Dm0644 "$PROFILE_ROOT/system/etc/polkit-1/rules.d/50-zenbook-backlight.rules" \
  /etc/polkit-1/rules.d/50-zenbook-backlight.rules
c_ok "installed /etc/polkit-1/rules.d/50-zenbook-backlight.rules"
if grep -rslE 'NOPASSWD:\s*/usr/bin/env' /etc/sudoers /etc/sudoers.d/ 2>/dev/null; then
  c_warn "found NOPASSWD /usr/bin/env sudo rule(s) — removing (privilege hole)"
  grep -rlE 'NOPASSWD:\s*/usr/bin/env' /etc/sudoers.d/ 2>/dev/null | while read -r f; do
    c_info "removing $f"; rm -f "$f"
  done
fi
c_ok "backlight privilege is now scoped via polkit; blanket sudo hole removed"

# --- systemd services: display topology, battery limit, and the ledger's
#     second-screen delivery (frank-ledger.service needs frankd already
#     installed — this profile step runs after the core, see run-all.sh) ---
for svc in duo-battery-limit duo-hardware frank-ledger; do
  install -Dm0644 "$PROFILE_ROOT/system/etc/systemd/system/$svc.service" \
    "/etc/systemd/system/$svc.service"
  c_ok "installed /etc/systemd/system/$svc.service"
done

if is_arch; then
  udevadm control --reload-rules || true
  systemctl daemon-reload
  systemctl enable duo-battery-limit.service duo-hardware.service frank-ledger.service 2>/dev/null || true
fi

cat <<'EOF'
  NOTE(hardware): backlight sync uses backlight=card1-eDP-2-backlight — verify
  the sysfs name on YOUR unit with:  ls /sys/class/backlight/
  and adjust this profile's hardware/backlight-sync if it differs. [TODO(hardware)]
  NOTE(hardware): the detachable BT keyboard's VID:PID in
  this profile's system/etc/udev/rules.d/90-zenbook-duo.rules is a
  placeholder (0b05:XXXX) — fill in the real ids from `udevadm monitor` while
  docking/undocking.
EOF
c_ok "zenbook-duo-2024 profile installed (verify on device)"
