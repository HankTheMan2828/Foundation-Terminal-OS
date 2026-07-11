#!/usr/bin/env bash
# 11 — Frank's LOCAL AI sensor (BitNet b1.58 2B4T via bitnet.cpp).
#
# Operator decision (2026-07-06): the AI runs locally, period — installed WITH
# the OS, no per-machine choice (docs/FRANK-LOCAL-AI.md). This step lays down the
# inference server (bitnet.cpp's `llama-server`), the model GGUF, and the
# frank-ai.service that serves them on 127.0.0.1, which Frank's LocalSifter /
# ModelAdvisor *and* the Hub's on-device Assistant share.
#
# Offline path (the real one): foundation-install stages model+binary from the
# USB raw-offset sidecar into $REPO_ROOT/vendor/{models,bitnet}/. We copy those
# into place. Online fallback: build/fetch if not staged (never fires on a
# network-less mini PC).
#
# It stays a SENSOR for Frank: readings become findings only through the
# Overseer's Rulebook. If binary or model is missing, ExecConditions keep the
# service idle and the rules keep running.
source "$(dirname "$0")/common.sh"
require_root
c_step "Frank: local AI sensor (BitNet b1.58 2B4T)"

AI_LIB=/usr/local/lib/foundation-ai
BIN="$AI_LIB/llama-server"
MODEL=/var/lib/frank/models/model.gguf

STAGED_BIN="$REPO_ROOT/vendor/bitnet/llama-server"
STAGED_MODEL="$REPO_ROOT/vendor/models/model.gguf"
# microsoft/bitnet-b1.58-2B-4T-gguf -> the i2_s (1-bit) weight, ~1.2 GB.
: "${FRANK_MODEL_URL:=https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf/resolve/main/ggml-model-i2_s.gguf}"
: "${FRANK_MODEL_SHA256:=}"                 # optional integrity check
: "${FRANK_BITNET_REPO:=https://github.com/microsoft/BitNet}"

install -d -o root -g root -m 0755 "$AI_LIB"
# Model lives under Frank's own state dir, frank:frank 0700 — the operator can't
# read it any more than the rest of Frank's data (spec §6 isolation).
install -d -o frank -g frank -m 0700 /var/lib/frank/models

_is_gguf() {
  [[ -f "$1" ]] || return 1
  local magic
  magic="$(dd if="$1" bs=1 count=4 2>/dev/null || true)"
  [[ "$magic" == "GGUF" ]]
}

_is_elf() {
  [[ -f "$1" ]] || return 1
  local magic
  magic="$(dd if="$1" bs=1 count=4 2>/dev/null || true)"
  [[ "$magic" == $'\x7fELF' ]]
}

# ── the inference server binary ──────────────────────────────────────────────
lay_down_server() {
  if [[ -x "$BIN" ]] && _is_elf "$BIN"; then
    c_ok "llama-server already present: $BIN"; return 0
  fi
  if [[ -f "$STAGED_BIN" ]]; then
    if ! _is_elf "$STAGED_BIN"; then
      c_warn "staged binary at $STAGED_BIN is not an ELF — ignoring it"
    else
      install -m 0755 "$STAGED_BIN" "$BIN"
      # World-executable so User=frank can run it; tree stays root-owned.
      chmod 0755 "$BIN"
      c_ok "staged llama-server -> $BIN"
      return 0
    fi
  fi
  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    c_warn "offline install and no staged binary at $STAGED_BIN"
    c_warn "USB must carry foundation-ai-llama-server (USB creator stages it);"
    c_warn "sensor idle until then — rules still run"
    return 0
  fi
  # Online: build bitnet.cpp from source. Heavy but one-time. [TODO(hardware)]:
  # verify the exact build invocation on the target toolchain.
  pac git cmake clang
  local src="/opt/bitnet-src"
  c_info "building bitnet.cpp from $FRANK_BITNET_REPO (one-time, a few minutes)…"
  if [[ ! -d "$src/.git" ]]; then
    git clone --depth 1 --recursive "$FRANK_BITNET_REPO" "$src" || {
      c_warn "clone failed — sensor stays idle; re-run to retry"; return 0; }
  fi
  if command -v pip >/dev/null 2>&1; then
    pip install --break-system-packages -r "$src/requirements.txt" 2>/dev/null || true
  fi
  # bitnet.cpp builds the llama.cpp fork (which yields llama-server) via cmake.
  if cmake -S "$src" -B "$src/build" -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1 \
     && cmake --build "$src/build" --config Release -j --target llama-server >/dev/null 2>&1; then
    local built; built="$(find "$src/build" -name llama-server -type f 2>/dev/null | head -1 || true)"
    if [[ -n "$built" ]] && _is_elf "$built"; then
      install -m 0755 "$built" "$BIN"; c_ok "built llama-server -> $BIN"; return 0
    fi
  fi
  c_warn "bitnet.cpp build did not produce llama-server — sensor stays idle"
  c_warn "verify the build for this toolchain (docs/FRANK-LOCAL-AI.md); re-run to retry"
}
lay_down_server

# ── the model GGUF ───────────────────────────────────────────────────────────
lay_down_model() {
  if [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; then
    c_ok "model already present: $MODEL"; return 0
  fi
  # Corrupt leftover from a partial install — replace if we have a staged copy.
  if [[ -f "$MODEL" ]] && ! _is_gguf "$MODEL"; then
    c_warn "existing model at $MODEL is not GGUF — will replace if staged"
    rm -f "$MODEL"
  fi
  if [[ -f "$STAGED_MODEL" ]]; then
    if ! _is_gguf "$STAGED_MODEL"; then
      c_warn "staged model at $STAGED_MODEL is not a GGUF — ignoring it"
    else
      install -o frank -g frank -m 0600 "$STAGED_MODEL" "$MODEL"
      c_ok "staged model -> $MODEL"
      return 0
    fi
  fi
  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    c_warn "offline install and no staged model at $STAGED_MODEL — sensor idle until placed"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then pac curl; fi
  c_info "fetching BitNet model from $FRANK_MODEL_URL (~1.2 GB)…"
  local tmp; tmp="$(mktemp)"
  if ! curl -fL --retry 3 -o "$tmp" "$FRANK_MODEL_URL"; then
    c_warn "model fetch failed — sensor stays idle; re-run to retry"; rm -f "$tmp"; return 0
  fi
  if [[ -n "$FRANK_MODEL_SHA256" ]]; then
    if ! echo "$FRANK_MODEL_SHA256  $tmp" | sha256sum -c - >/dev/null 2>&1; then
      c_warn "model checksum MISMATCH — refusing to install it"; rm -f "$tmp"; return 1
    fi
    c_ok "model checksum verified"
  fi
  if ! _is_gguf "$tmp"; then
    c_warn "downloaded file is not a GGUF — refusing to install it"; rm -f "$tmp"; return 1
  fi
  install -o frank -g frank -m 0600 "$tmp" "$MODEL"; rm -f "$tmp"
  c_ok "installed model -> $MODEL"
}
lay_down_model

# ── the service (loopback-bound, RAM-capped, frank-only) ─────────────────────
install_file "etc/systemd/system/frank-ai.service" "/etc/systemd/system/frank-ai.service" 0644

# Enable for boot the same way 05-frank does: drop the wants-symlink by hand so
# it works inside the installer chroot (no running systemd manager).
install -d /etc/systemd/system/multi-user.target.wants
ln -sfn /etc/systemd/system/frank-ai.service \
  /etc/systemd/system/multi-user.target.wants/frank-ai.service
c_ok "frank-ai.service enabled for multi-user.target"

if is_arch && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload 2>/dev/null || true
  # Best-effort start on a live system (not the install chroot).
  systemctl enable --now frank-ai.service 2>/dev/null || true
fi

if [[ -x "$BIN" && -f "$MODEL" ]] && _is_elf "$BIN" && _is_gguf "$MODEL"; then
  c_ok "local AI assets in place: $BIN + $MODEL"
  c_ok "on boot, frank-ai.service serves OpenAI-compat chat on 127.0.0.1:8080"
  c_info "Hub ASSISTANT + Frank's sensor both use that endpoint"
else
  c_info "frank-ai.service enabled but idle until binary+model are both valid"
  c_info "missing:"
  [[ -x "$BIN" ]] && _is_elf "$BIN" || c_info "  - server binary ($BIN)"
  [[ -f "$MODEL" ]] && _is_gguf "$MODEL" || c_info "  - model GGUF ($MODEL)"
fi
c_ok "Frank local AI step complete"
