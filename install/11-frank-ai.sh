#!/usr/bin/env bash
# 11 — Frank's LOCAL AI sensor (BitNet b1.58 2B4T via bitnet.cpp).
#
# Operator decision (2026-07-06 / 2026-07-11): the AI runs locally, period —
# installed WITH the OS, no cloud for the Hub Assistant, no per-machine choice
# (docs/FRANK-LOCAL-AI.md). This step lays down the inference server
# (bitnet.cpp's `llama-server`), the model GGUF, and frank-ai.service on
# 127.0.0.1:8080 — shared by Frank's LocalSifter / ModelAdvisor *and* the Hub
# Assistant.
#
# Offline path (the real one): foundation-install stages model+binary from the
# USB raw-offset sidecar into $REPO_ROOT/vendor/{models,bitnet}/. We copy those
# into place. On UPDATE, if the USB was written with -NoModel, we still keep
# whatever is already under /var/lib/frank/models and /usr/local/lib/foundation-ai,
# and we can recover staged copies from $REPO_ROOT.prev/vendor (previous payload).
# Online fallback (build/fetch) only when FOUNDATION_OFFLINE is unset — never on
# a network-less mini PC install/update.
#
# Sensor semantics for Frank are unchanged: readings become findings only
# through the Overseer's Rulebook. Missing assets → ExecConditions keep the
# service idle; rules still run.
source "$(dirname "$0")/common.sh"
require_root
c_step "Frank: local AI sensor (BitNet b1.58 2B4T) + Hub Assistant endpoint"

AI_LIB=/usr/local/lib/foundation-ai
BIN="$AI_LIB/llama-server"
MODEL=/var/lib/frank/models/model.gguf

# Prefer the live payload's vendor tree; fall back to the pre-update tree so a
# -NoModel USB refresh still re-lays assets that were staged on an earlier install.
STAGED_BIN=""
STAGED_MODEL=""
for cand in \
  "$REPO_ROOT/vendor/bitnet/llama-server" \
  "$REPO_ROOT.prev/vendor/bitnet/llama-server"
do
  if [[ -f "$cand" ]]; then STAGED_BIN="$cand"; break; fi
done
for cand in \
  "$REPO_ROOT/vendor/models/model.gguf" \
  "$REPO_ROOT.prev/vendor/models/model.gguf"
do
  if [[ -f "$cand" ]]; then STAGED_MODEL="$cand"; break; fi
done

# microsoft/bitnet-b1.58-2B-4T-gguf -> the i2_s (1-bit) weight, ~1.2 GB.
: "${FRANK_MODEL_URL:=https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf/resolve/main/ggml-model-i2_s.gguf}"
: "${FRANK_MODEL_SHA256:=}"                 # optional integrity check
: "${FRANK_BITNET_REPO:=https://github.com/microsoft/BitNet}"

install -d -o root -g root -m 0755 "$AI_LIB"
# Model lives under Frank's own state dir, frank:frank 0700 — the operator can't
# read it any more than the rest of Frank's data (spec §6 isolation).
# frank user is created in 05-frank (runs before this step).
if id frank >/dev/null 2>&1; then
  install -d -o frank -g frank -m 0700 /var/lib/frank/models
else
  install -d -m 0700 /var/lib/frank/models
  c_warn "user 'frank' missing — model dir root-owned until 05-frank is re-run"
fi

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

# Gzip magic (foundation-ai-runtime tarball from CI).
_is_gzip() {
  [[ -f "$1" ]] || return 1
  local magic
  magic="$(dd if="$1" bs=1 count=2 2>/dev/null || true)"
  [[ "$magic" == $'\x1f\x8b' ]]
}

_file_size() {
  stat -c %s "$1" 2>/dev/null || stat -f %z "$1" 2>/dev/null || echo 0
}

# Install runtime from a staged blob: gzipped tarball (preferred — binary +
# libllama/libggml) or a bare ELF (legacy; usually fails without .so files).
_install_runtime_blob() {
  local staged="$1"
  if _is_gzip "$staged"; then
    # Wipe prior partial runtime so old bare-ELF installs pick up libs.
    find "$AI_LIB" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
    if ! tar -xzf "$staged" -C "$AI_LIB" 2>/dev/null; then
      c_warn "failed to extract AI runtime tarball from $staged"
      return 1
    fi
    # Tarball may nest llama-server at top level (CI layout).
    if [[ ! -x "$BIN" ]]; then
      local found
      found="$(find "$AI_LIB" -name llama-server -type f 2>/dev/null | head -1 || true)"
      if [[ -n "$found" && "$found" != "$BIN" ]]; then
        install -m 0755 "$found" "$BIN"
      fi
    fi
    chmod 0755 "$BIN" 2>/dev/null || true
    # World-readable libs so User=frank can dlopen them; tree stays root-owned.
    find "$AI_LIB" -type f -name 'lib*.so*' -exec chmod 0644 {} + 2>/dev/null || true
    local so_n
    so_n="$(find "$AI_LIB" -maxdepth 1 -name 'lib*.so*' 2>/dev/null | wc -l | tr -d ' ')"
    c_ok "AI runtime tarball -> $AI_LIB (llama-server + ${so_n} shared libs)"
    return 0
  fi
  if _is_elf "$staged"; then
    # Bare ELF is never enough (needs libllama/libggml). Refuse so we don't
    # paper over a broken install.
    c_warn "staged bare ELF llama-server (no libs) — refusing; need runtime tarball"
    return 1
  fi
  c_warn "staged server at $staged is neither gzip runtime nor ELF — ignoring"
  return 1
}

# Runtime is usable only if the binary exists AND at least one private .so is
# present (or ldd reports no missing libllama — we check for lib*.so* files).
_runtime_ok() {
  [[ -x "$BIN" ]] && _is_elf "$BIN" || return 1
  # Bare ELF with system-only deps would pass; BitNet always needs libllama.
  local so_n
  so_n="$(find "$AI_LIB" -maxdepth 1 -name 'lib*.so*' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "${so_n:-0}" -ge 1 ]]
}

# ── the inference server runtime ─────────────────────────────────────────────
# Staged blob preferred (USB update can repair/upgrade). When nothing staged,
# keep a working installed runtime (network update / -NoModel USB).
lay_down_server() {
  # Prefer tarball names in vendor/, then legacy bare llama-server path.
  local blob=""
  for cand in \
    "$REPO_ROOT/vendor/bitnet/runtime.tar.gz" \
    "$REPO_ROOT/vendor/bitnet/llama-server.tar.gz" \
    "$REPO_ROOT/vendor/bitnet/llama-server" \
    "$REPO_ROOT.prev/vendor/bitnet/runtime.tar.gz" \
    "$REPO_ROOT.prev/vendor/bitnet/llama-server.tar.gz" \
    "$REPO_ROOT.prev/vendor/bitnet/llama-server"
  do
    if [[ -f "$cand" ]]; then blob="$cand"; break; fi
  done
  # STAGED_BIN from the loop at top may still point at llama-server path.
  if [[ -z "$blob" && -n "$STAGED_BIN" && -f "$STAGED_BIN" ]]; then
    blob="$STAGED_BIN"
  fi

  if [[ -n "$blob" ]]; then
    if _install_runtime_blob "$blob"; then
      if _runtime_ok; then return 0; fi
      c_warn "runtime installed but libllama/libggml missing — Assistant will stay offline"
      return 0
    fi
  fi
  if _runtime_ok; then
    c_ok "AI runtime already present (kept): $AI_LIB"
    return 0
  fi
  if [[ -x "$BIN" ]] && _is_elf "$BIN"; then
    c_warn "llama-server present but shared libs missing under $AI_LIB"
    c_warn "re-stage foundation-ai-runtime tarball from the release USB"
  fi
  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    c_warn "offline install and no staged AI runtime"
    c_warn "USB must carry foundation-ai-runtime (USB creator stages it);"
    c_warn "frank-ai.service + Hub Assistant stay idle until then — rules still run"
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
  if cmake -S "$src" -B "$src/build" -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1 \
     && cmake --build "$src/build" --config Release -j --target llama-server >/dev/null 2>&1; then
    local built; built="$(find "$src/build" -name llama-server -type f 2>/dev/null | head -1 || true)"
    if [[ -n "$built" && -x "$built" ]]; then
      install -m 0755 "$built" "$BIN"
      find "$src/build" -type f \( -name 'libllama.so*' -o -name 'libggml*.so*' \) \
        -exec cp -a {} "$AI_LIB/" \; 2>/dev/null || true
      c_ok "built AI runtime -> $AI_LIB"
      return 0
    fi
  fi
  c_warn "bitnet.cpp build did not produce a usable runtime — sensor stays idle"
  c_warn "verify the build for this toolchain (docs/FRANK-LOCAL-AI.md); re-run to retry"
}
lay_down_server

# ── the model GGUF ───────────────────────────────────────────────────────────
# Install from stage when target is missing/invalid, or when sizes differ
# (repair / model swap). Same-size keep avoids re-copying ~1.2 GB on every
# -NoModel update that still has prev vendor lying around.
lay_down_model() {
  if [[ -f "$MODEL" ]] && ! _is_gguf "$MODEL"; then
    c_warn "existing model at $MODEL is not GGUF — removing"
    rm -f "$MODEL"
  fi

  if [[ -n "$STAGED_MODEL" && -f "$STAGED_MODEL" ]]; then
    if ! _is_gguf "$STAGED_MODEL"; then
      c_warn "staged model at $STAGED_MODEL is not a GGUF — ignoring it"
    else
      local need=1
      if [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; then
        local a b
        a="$(_file_size "$MODEL")"
        b="$(_file_size "$STAGED_MODEL")"
        if [[ "$a" == "$b" && "$a" != "0" ]]; then
          c_ok "model already present (same size as stage): $MODEL"
          need=0
        fi
      fi
      if (( need )); then
        if id frank >/dev/null 2>&1; then
          install -o frank -g frank -m 0600 "$STAGED_MODEL" "$MODEL"
        else
          install -m 0600 "$STAGED_MODEL" "$MODEL"
        fi
        c_ok "model from stage -> $MODEL"
      fi
      return 0
    fi
  fi

  if [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; then
    c_ok "model already present (kept): $MODEL"
    return 0
  fi

  if [[ "${FOUNDATION_OFFLINE:-0}" == "1" ]]; then
    c_warn "offline install and no staged model — sensor/Assistant idle until placed"
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
  if id frank >/dev/null 2>&1; then
    install -o frank -g frank -m 0600 "$tmp" "$MODEL"
  else
    install -m 0600 "$tmp" "$MODEL"
  fi
  rm -f "$tmp"
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

if is_arch && systemctl daemon-reload 2>/dev/null; then
  systemctl enable frank-ai.service 2>/dev/null || true
  # Start when assets are present (live system). Inside install chroot this is
  # a no-op / fails quietly — first boot picks up the wants-symlink.
  if _runtime_ok && [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; then
    systemctl restart frank-ai.service 2>/dev/null \
      || systemctl start frank-ai.service 2>/dev/null \
      || true
  fi
  if systemctl is-active --quiet frank-ai.service 2>/dev/null; then
    c_ok "frank-ai.service is active (127.0.0.1:8080)"
  else
    c_info "frank-ai enabled; not active in this context (normal in installer chroot)"
  fi
fi

# Default Hub Assistant config: local endpoint only (never a cloud key).
# 04-hub may create an empty aichat.env first — fill empty/missing only so
# technician URL/model overrides survive updates.
AICHAT_ENV=/etc/foundationhub/aichat.env
if [[ ! -e "$AICHAT_ENV" || ! -s "$AICHAT_ENV" ]]; then
  install -d -m 0755 /etc/foundationhub
  cat > "$AICHAT_ENV" <<'EOF'
# Hub Assistant — LOCAL model only (no cloud keys, no online fallback).
# Defaults match frank-ai.service; uncomment to override:
# FOUNDATIONHUB_AI_URL=http://127.0.0.1:8080/v1/chat/completions
# FOUNDATIONHUB_AI_MODEL=bitnet-b1.58-2B-4T
EOF
  if id "${OPERATOR:-operator}" >/dev/null 2>&1; then
    chown "root:${OPERATOR:-operator}" "$AICHAT_ENV" 2>/dev/null || true
  fi
  chmod 0640 "$AICHAT_ENV"
  c_ok "wrote $AICHAT_ENV (local-only defaults)"
fi

# Operator-readable status for Hub System Status (session.local_ai_health).
_write_ai_status() {
  local state="$1" detail="$2"
  local dir=/var/lib/foundationhub
  install -d -m 0755 "$dir" 2>/dev/null || true
  cat > "$dir/ai-status" <<EOF
# Written by install/11-frank-ai.sh — Hub Settings → SYSTEM STATUS reads this.
state=$state
detail=$detail
bin=$BIN
model=$MODEL
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)
EOF
  chmod 0644 "$dir/ai-status" 2>/dev/null || true
}

if _runtime_ok && [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; then
  c_ok "local AI assets in place: runtime under $AI_LIB + $MODEL"
  c_ok "on boot, frank-ai.service serves OpenAI-compat chat on 127.0.0.1:8080"
  c_ok "Hub ASSISTANT + Frank's sensor both use that endpoint (offline, no cloud)"
  _write_ai_status "ready" "runtime+model installed; service starts on boot"
else
  c_warn "frank-ai.service enabled but IDLE — runtime and/or model incomplete"
  c_warn "Hub ASSISTANT will report 'local model not reachable' until fixed"
  c_info "missing:"
  miss_bits=""
  if ! _runtime_ok; then
    c_info "  - AI runtime (llama-server + libllama.so + libggml.so under $AI_LIB)"
    miss_bits="${miss_bits}runtime "
  fi
  if ! { [[ -f "$MODEL" ]] && _is_gguf "$MODEL"; }; then
    c_info "  - model GGUF ($MODEL)"
    miss_bits="${miss_bits}model "
  fi
  c_info "fix: rewrite the USB with the Foundation USB creator (NOT Rufus/"
  c_info "      Etcher) WITHOUT -NoModel, then UPDATE (docs/FRANK-LOCAL-AI.md)."
  c_info "      Confirm the creator prints 'AI sidecar verified' before unplugging."
  # Trim trailing space so Hub shows "missing: runtime model" cleanly.
  miss_bits="${miss_bits%"${miss_bits##*[![:space:]]}"}"
  _write_ai_status "idle" "missing: ${miss_bits:-unknown}"
fi
c_ok "Frank local AI step complete"
