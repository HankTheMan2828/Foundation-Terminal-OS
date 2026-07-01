#!/usr/bin/env bash
# 04 — Zenbook Duo hardware glue (spec §7, §11.6). Ports the community project's
# kernel/udev/sysfs pieces; reimplements the GNOME session-watcher glue against
# wlr-randr/cage.
source "$(dirname "$0")/common.sh"
require_root
c_step "Zenbook Duo hardware adaptations"

pac iio-sensor-proxy libwacom brightnessctl power-profiles-daemon

# Helper scripts live under /usr/local/lib/zenhub (referenced by the Hub's
# session.HW_BIN and by the hardware services).
install -d /usr/local/lib/zenhub
for f in duo-screen-toggle duo-watch-displays duo-keyboard-detach \
         backlight-sync duo-battery-limit; do
  install -Dm0755 "$REPO_ROOT/hardware/$f" "/usr/local/lib/zenhub/$f"
  c_ok "installed /usr/local/lib/zenhub/$f"
done

# udev: emit a single keyboard detach/attach event consumed by BOTH display
# topology and Frank's ledger (spec §7). And the eDP-2 backlight naming.
install -Dm0644 "$REPO_ROOT/hardware/udev/90-zenbook-duo.rules" \
  /etc/udev/rules.d/90-zenbook-duo.rules
c_ok "installed udev rules"

# Battery charge limiter (GNOME-agnostic, ports directly).
install -Dm0644 "$REPO_ROOT/hardware/systemd/duo-battery-limit.service" \
  /etc/systemd/system/duo-battery-limit.service
# Display/rotation watcher against cage (replaces the GNOME session watcher).
install -Dm0644 "$REPO_ROOT/hardware/systemd/duo-hardware.service" \
  /etc/systemd/system/duo-hardware.service

if is_arch; then
  udevadm control --reload-rules || true
  systemctl daemon-reload
  systemctl enable duo-battery-limit.service duo-hardware.service 2>/dev/null || true
fi

cat <<'EOF'
  NOTE(hardware): backlight sync uses backlight=card1-eDP-2-backlight — verify
  the sysfs name on YOUR unit with:  ls /sys/class/backlight/
  and adjust hardware/backlight-sync if it differs. [TODO(hardware)]
EOF
c_ok "hardware glue installed (verify on device)"
