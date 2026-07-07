#!/usr/bin/env bash
# 11 — Frank's LOCAL AI sensor (IBM Granite Guardian).
#
# Operator decision (2026-07-06): the AI runs locally, period — installed WITH
# the OS, no per-machine choice (docs/FRANK-AI-GUARDIAN.md). This step lays down
# the inference runtime + the Guardian model + the frank-ai.service that serves
# it on 127.0.0.1, which Frank's LocalGuardianSifter/GuardianAdvisor use.
#
# It stays a SENSOR: its readings become findings only through the Overseer's
# deterministic Rulebook, so a small model can't decide guilt or severity — and
# if the model can't be laid down here, Frank's sensor safely reads nothing and
# the rules keep running (the service's ExecCondition guards on the file).
source "$(dirname "$0")/common.sh"
require_root
c_step "Frank: local AI sensor (Granite Guardian)"

# The local OpenAI-compatible inference server (provides `llama-server`).
pac llama.cpp

# Model lives under Frank's own state dir, frank:frank 0700 — the operator can't
# read it any more than the rest of Frank's data (spec §6 isolation).
install -d -o frank -g frank -m 0700 /var/lib/frank/models
MODEL=/var/lib/frank/models/guardian.gguf

# Where the model comes from. A quantized ~2-3B Guardian GGUF is ~1.5-2.5 GB —
# too big to bake into the ISO's offline repo without blowing GitHub's 2 GiB
# release-asset limit (see the build-iso history), so the DEFAULT is
# fetch-on-install from a configurable URL. An OFFLINE install must pre-stage the
# GGUF (image/ ships it separately, or drop it at $STAGED before running this).
STAGED="$REPO_ROOT/vendor/models/guardian.gguf"
: "${FRANK_GUARDIAN_MODEL_URL:=}"     # set to a GGUF URL to fetch on install
: "${FRANK_GUARDIAN_MODEL_SHA256:=}"  # optional integrity check

lay_down_model() {
  if [[ -f "$MODEL" ]]; then
    c_ok "Guardian model already present: $MODEL"; return 0
  fi
  if [[ -f "$STAGED" ]]; then
    install -o frank -g frank -m 0600 "$STAGED" "$MODEL"
    c_ok "staged Guardian model -> $MODEL"; return 0
  fi
  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    c_warn "offline install and no staged model at $STAGED"
    c_warn "Frank's AI sensor will be inactive until the GGUF is placed there"
    return 0
  fi
  if [[ -z "$FRANK_GUARDIAN_MODEL_URL" ]]; then
    c_warn "no FRANK_GUARDIAN_MODEL_URL set and no staged model — skipping fetch"
    c_warn "set FRANK_GUARDIAN_MODEL_URL=<gguf-url> and re-run, or stage $STAGED"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then pac curl; fi
  c_info "fetching Guardian model from $FRANK_GUARDIAN_MODEL_URL"
  local tmp; tmp="$(mktemp)"
  if ! curl -fL --retry 3 -o "$tmp" "$FRANK_GUARDIAN_MODEL_URL"; then
    c_warn "model fetch failed — sensor stays inactive; re-run to retry"
    rm -f "$tmp"; return 0
  fi
  if [[ -n "$FRANK_GUARDIAN_MODEL_SHA256" ]]; then
    if ! echo "$FRANK_GUARDIAN_MODEL_SHA256  $tmp" | sha256sum -c - >/dev/null 2>&1; then
      c_warn "model checksum MISMATCH — refusing to install it"; rm -f "$tmp"; return 1
    fi
    c_ok "model checksum verified"
  fi
  install -o frank -g frank -m 0600 "$tmp" "$MODEL"; rm -f "$tmp"
  c_ok "installed Guardian model -> $MODEL"
}
lay_down_model

# The service (bound to loopback, RAM-capped, frank-only). ExecCondition makes it
# a no-op when the model isn't present, so this is safe to enable regardless.
install_file "etc/systemd/system/frank-ai.service" "/etc/systemd/system/frank-ai.service" 0644
if is_arch; then
  systemctl daemon-reload
  systemctl enable --now frank-ai.service 2>/dev/null || true
  if [[ -f "$MODEL" ]]; then
    c_ok "frank-ai.service enabled; Guardian serving on 127.0.0.1:8080"
  else
    c_info "frank-ai.service enabled but idle until a model is placed at $MODEL"
  fi
fi
c_ok "Frank local AI step complete"
