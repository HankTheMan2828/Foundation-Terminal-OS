#!/usr/bin/env bash
# 07 — optional hardware profile (see docs/PROFILES.md).
#
# The generic core (steps 00-06) targets no specific device. This step layers
# device-specific glue (display topology, backlight, battery, detach handling,
# udev/polkit rules, etc.) on top, ONLY if HARDWARE_PROFILE names one under
# profiles/. Runs last so profile glue can assume the core (Hub, Frank) is
# already installed.
source "$(dirname "$0")/common.sh"
require_root
c_step "Hardware profile"

if [[ -z "$HARDWARE_PROFILE" ]]; then
  c_info "no HARDWARE_PROFILE set — generic core only, no device-specific glue installed"
  c_info "to target a specific device: HARDWARE_PROFILE=<name> $0   (see profiles/, docs/PROFILES.md)"
  exit 0
fi

if [[ ! -x "$PROFILE_DIR/install.sh" ]]; then
  c_warn "HARDWARE_PROFILE=$HARDWARE_PROFILE but $PROFILE_DIR/install.sh is missing or not executable"
  exit 1
fi

c_info "applying hardware profile: $HARDWARE_PROFILE"
"$PROFILE_DIR/install.sh"
c_ok "hardware profile '$HARDWARE_PROFILE' applied"
