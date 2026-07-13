#!/usr/bin/env bash
# create-foundation-usb.sh — make a Foundation TerminalOS install USB on
# Linux or macOS. Counterpart of Create-FoundationUSB.ps1 (Windows).
#
#   sudo ./create-foundation-usb.sh                # auto-finds/downloads the ISO
#   sudo ./create-foundation-usb.sh path/to.iso    # use a specific ISO
#   FOUNDATION_NO_MODEL=1 sudo ./create-foundation-usb.sh   # ISO only / no AI
#   FOUNDATION_FORCE_FULL=1 sudo ./create-foundation-usb.sh # always full wipe
#
# Stick-aware modes (probes before writing):
#   full     — wipe-style rewrite of ISO + AI sidecar
#   iso_only — rewrite ISO with conv=notrunc; leave AI past 2 GiB
#   ai_only  — write AI sidecar only
#   skip     — ISO (+ AI if required) already match
#
# Only removable/USB disks are ever offered — never the disk the running
# system lives on — and writes are gated (ERASE / UPDATE / STAGE).
set -euo pipefail

GITHUB_REPO="HankTheMan2828/Foundation-Terminal-OS"
STAGE_OFFSET=2147483648    # 2 GiB — must match Create-FoundationUSB.ps1 + foundation-install
STAGE_HDR=1048576          # 1 MiB header region (keeps every dd write 1 MiB-aligned)

c_info() { printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
c_ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[1;31m[!]\033[0m %s\n' "$*"; }

banner() {
  printf '\033[1;33m'
  cat <<'EOF'
  ┌──────────────────────────────────────────────────────────────┐
  │          FOUNDATION  TERMINALOS  —  USB  CREATOR             │
  │                  "From the Foundation."                      │
  └──────────────────────────────────────────────────────────────┘
EOF
  printf '\033[0m'
  echo "  This prepares a Foundation TerminalOS install USB."
  echo "  It probes the stick first: full wipe only when needed;"
  echo "  otherwise it updates just the ISO and/or AI sidecar."
  echo "  This computer itself is NOT touched — only the USB stick."
  echo
}

[[ $EUID -eq 0 ]] || { c_warn "run me with sudo (raw disk writes need root)"; exit 1; }
OS="$(uname -s)"
banner

# ── 1. find the ISO ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
find_iso() {
  local given="${1:-}" cand
  if [[ -n "$given" ]]; then
    [[ -f "$given" ]] || { c_warn "ISO not found at: $given"; exit 1; }
    printf '%s\n' "$given"; return
  fi
  for dir in "$SCRIPT_DIR" "$SCRIPT_DIR/../../image/out" "${SUDO_USER:+/home/$SUDO_USER/Downloads}" "$HOME/Downloads"; do
    [[ -n "$dir" && -d "$dir" ]] || continue
    cand="$(ls -t "$dir"/foundation-terminalos-*.iso 2>/dev/null | head -1 || true)"
    [[ -n "$cand" ]] && { printf '%s\n' "$cand"; return; }
  done
  c_info "No installer ISO found on this computer." >&2
  read -rp "> download the latest release now? [Y/n]: " ans
  [[ "${ans,,}" == n* ]] && { c_warn "nothing to write — pass an ISO path as the first argument"; exit 1; }
  # the release list (not /latest, which 404s on a repo with no releases yet)
  local json url
  json="$(curl -fsSL "https://api.github.com/repos/$GITHUB_REPO/releases")" || {
    c_warn "could not reach GitHub — check your internet connection, or download"
    c_warn "the ISO manually from the Releases page and pass its path as an argument"
    exit 1
  }
  url="$(printf '%s' "$json" \
         | grep -o '"browser_download_url": *"[^"]*\.iso"' | head -1 | cut -d'"' -f4 || true)"
  [[ -n "$url" ]] || {
    if [[ "$(printf '%s' "$json" | tr -d '[:space:]')" == "[]" ]]; then
      c_warn "the project hasn't published a release yet, so there is no ISO to download"
    else
      c_warn "no GitHub release of $GITHUB_REPO has an ISO attached"
    fi
    c_warn "a maintainer publishes one by pushing a TerminalOS-v* tag (CI attaches the ISO);"
    c_warn "until then, build it with image/build-iso.sh and pass its path as an argument"
    exit 1
  }
  cand="$SCRIPT_DIR/$(basename "$url")"
  c_info "downloading $(basename "$url") …" >&2
  curl -fL --progress-bar -o "$cand" "$url" >&2
  printf '%s\n' "$cand"
}

ISO="$(find_iso "${1:-}")"
ISO_BYTES="$(stat -c %s "$ISO" 2>/dev/null || stat -f %z "$ISO")"
c_ok "installer image: $ISO ($((ISO_BYTES / 1024 / 1024)) MB)"
echo

# ── 2. pick the USB stick ────────────────────────────────────────────────────
declare -a DEVS LABELS
if [[ "$OS" == "Darwin" ]]; then
  while read -r id; do
    [[ -n "$id" ]] || continue
    DEVS+=("/dev/$id")
    LABELS+=("/dev/$id  $(diskutil info "$id" | awk -F': +' '/Disk Size/{print $2; exit}')  $(diskutil info "$id" | awk -F': +' '/Device \/ Media Name/{print $2; exit}')")
  done < <(diskutil list external physical | awk '/^\/dev\//{sub("/dev/",""); print $1}')
else
  # removable or USB-attached whole disks only; never the disk holding /
  root_disk="$(lsblk -no pkname "$(findmnt -no SOURCE / 2>/dev/null)" 2>/dev/null | head -1 || true)"
  while read -r name rm tran size model; do
    [[ -n "$name" ]] || continue
    [[ "$(basename "$name")" == "$root_disk" ]] && continue
    [[ "$rm" == "1" || "$tran" == "usb" ]] || continue
    DEVS+=("$name")
    LABELS+=("$name  $size  ${model:-}")
  done < <(lsblk -dpno NAME,RM,TRAN,SIZE,MODEL,TYPE | awk '$NF == "disk" {NF--; print}')
fi

((${#DEVS[@]})) || { c_warn "no USB stick found — plug one in (8 GB or larger) and rerun"; exit 1; }
c_info "USB sticks on this computer (internal drives are never listed):"
echo
i=1; for l in "${LABELS[@]}"; do echo "  $i) $l"; i=$((i + 1)); done
echo

DEV=""
while [[ -z "$DEV" ]]; do
  read -rp "> write to stick # (1-${#DEVS[@]}, or q to quit): " pick
  [[ "$pick" == "q" ]] && { c_info "aborted — nothing was touched"; exit 0; }
  if [[ "$pick" =~ ^[0-9]+$ ]] && ((pick >= 1 && pick <= ${#DEVS[@]})); then
    DEV="${DEVS[$((pick - 1))]}"
  fi
done

# ── 3. probe stick ───────────────────────────────────────────────────────────
MODEL_URL="${FOUNDATION_MODEL_URL:-https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf/resolve/main/ggml-model-i2_s.gguf}"
AI_MODEL="$SCRIPT_DIR/model.gguf"
AI_RUNTIME="$SCRIPT_DIR/ai-runtime.tar.gz"
AI_SERVER="$SCRIPT_DIR/llama-server"
REQUIRE_AI=1
[[ "${FOUNDATION_NO_MODEL:-0}" == "1" ]] && REQUIRE_AI=0
STAGE_AI=0
STAGE_SERVER=""

_is_gzip_file() {
  [[ -f "$1" ]] || return 1
  local m; m="$(dd if="$1" bs=1 count=2 2>/dev/null || true)"
  [[ "$m" == $'\x1f\x8b' ]]
}

file_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }

# Raw device path for macOS (faster + needed for probe consistency)
if [[ "$OS" == "Darwin" ]]; then
  WRITE_DEV="${DEV/\/dev\//\/dev\/r}"
else
  WRITE_DEV="$DEV"
fi

_digest() {
  # stdin → short digest (md5sum on Linux, md5 on macOS, cksum fallback)
  if command -v md5sum >/dev/null 2>&1; then
    md5sum | awk '{print $1}'
  elif command -v md5 >/dev/null 2>&1; then
    md5 -q
  else
    cksum | awk '{print $1"-"$2}'
  fi
}

probe_iso_match() {
  # head + tail 1 MiB (or half ISO if tiny)
  local chunk=1048576
  (( ISO_BYTES >= 2 * chunk )) || chunk=$(( ISO_BYTES / 2 ))
  (( chunk >= 512 )) || chunk=512
  local head_iso head_dev tail_iso tail_dev
  head_iso="$(dd if="$ISO" bs="$chunk" count=1 2>/dev/null | _digest)"
  head_dev="$(dd if="$WRITE_DEV" bs="$chunk" count=1 2>/dev/null | _digest)"
  tail_iso="$(dd if="$ISO" bs=1 skip=$((ISO_BYTES - chunk)) count="$chunk" 2>/dev/null | _digest)"
  tail_dev="$(dd if="$WRITE_DEV" bs=1 skip=$((ISO_BYTES - chunk)) count="$chunk" 2>/dev/null | _digest)"
  [[ -n "$head_iso" && "$head_iso" == "$head_dev" && -n "$tail_iso" && "$tail_iso" == "$tail_dev" ]]
}

probe_ai() {
  # sets AI_PRESENT=0/1 AI_MATCH=0/1 AI_NOTE=...
  AI_PRESENT=0
  AI_MATCH=0
  AI_NOTE="no FOUNDATIONAI2 header at 2 GiB"
  local rb mo ms so ss magic
  rb="$(dd if="$WRITE_DEV" bs=4096 skip=$(( STAGE_OFFSET / 4096 )) count=1 2>/dev/null | tr -d '\000' || true)"
  if [[ "$rb" != FOUNDATIONAI2* ]]; then
    return 0
  fi
  AI_PRESENT=1
  mo="$(printf '%s\n' "$rb" | awk -F= '/^model_offset=/{print $2; exit}')"
  ms="$(printf '%s\n' "$rb" | awk -F= '/^model_size=/{print $2; exit}')"
  so="$(printf '%s\n' "$rb" | awk -F= '/^server_offset=/{print $2; exit}')"
  ss="$(printf '%s\n' "$rb" | awk -F= '/^server_size=/{print $2; exit}')"
  magic="$(dd if="$WRITE_DEV" bs=1 skip="${mo:-0}" count=4 2>/dev/null || true)"
  local gz
  gz="$(dd if="$WRITE_DEV" bs=1 skip="${so:-0}" count=2 2>/dev/null || true)"
  if [[ "$magic" != "GGUF" || "$gz" != $'\x1f\x8b' ]]; then
    AI_NOTE="header present but payload magic failed"
    return 0
  fi
  if (( REQUIRE_AI == 0 )); then
    AI_MATCH=1
    AI_NOTE="present (FOUNDATION_NO_MODEL — not restaging)"
    return 0
  fi
  if [[ -f "$AI_MODEL" ]] && _is_gzip_file "$AI_RUNTIME"; then
    local lms lss
    lms="$(file_size "$AI_MODEL")"
    lss="$(file_size "$AI_RUNTIME")"
    if [[ "$ms" == "$lms" && "$ss" == "$lss" ]]; then
      AI_MATCH=1
      AI_NOTE="matches local AI (model $((ms / 1024 / 1024)) MB + runtime)"
    else
      AI_NOTE="present but size mismatch (stick model=$ms local=$lms)"
    fi
  else
    AI_NOTE="present and readable (local AI files not ready to compare)"
  fi
}

c_info "probing the stick (what is already there)…"
ISO_MATCH=0
ISO_NOTE="not a matching Foundation ISO (blank or other)"
if probe_iso_match; then
  ISO_MATCH=1
  ISO_NOTE="matches local ISO (head+tail 1 MB)"
else
  # weak ISO9660 marker
  sig="$(dd if="$WRITE_DEV" bs=1 skip=32769 count=5 2>/dev/null || true)"
  if [[ "$sig" == "CD001" ]]; then
    ISO_NOTE="different ISO present — will rewrite"
  fi
fi
probe_ai
echo "  ISO: $ISO_NOTE"
echo "  AI:  $AI_NOTE"
echo

# ── decide mode ──────────────────────────────────────────────────────────────
MODE=full
if [[ "${FOUNDATION_FORCE_FULL:-0}" == "1" ]]; then
  MODE=full
  c_info "FOUNDATION_FORCE_FULL=1 — full wipe + rewrite"
elif (( REQUIRE_AI == 0 )); then
  if (( ISO_MATCH == 1 )); then MODE=skip; else MODE=iso_only; fi
else
  if (( ISO_MATCH == 1 && AI_MATCH == 1 )); then MODE=skip
  elif (( ISO_MATCH == 1 && AI_MATCH == 0 )); then MODE=ai_only
  elif (( ISO_MATCH == 0 && AI_MATCH == 1 )); then MODE=iso_only
  else MODE=full
  fi
fi

case "$MODE" in
  skip)
    c_ok "stick already has this ISO"
    if (( REQUIRE_AI == 1 )); then c_ok "and a matching AI sidecar — nothing to write."
    else c_ok "(FOUNDATION_NO_MODEL) — nothing to write."
    fi
    echo
    c_ok "Your Foundation TerminalOS install USB is ready (unchanged)."
    echo "Force a full rewrite with FOUNDATION_FORCE_FULL=1."
    exit 0
    ;;
  iso_only)
    c_info "Mode: ISO-ONLY — rewrite installer, keep AI sidecar past 2 GiB."
    c_warn "Stick $DEV ISO will be rewritten; free-space AI (if any) is preserved."
    read -rp "> type UPDATE (all caps) to continue, anything else aborts: " confirm
    [[ "$confirm" == "UPDATE" ]] || { c_info "aborted — nothing was touched"; exit 0; }
    ;;
  ai_only)
    c_info "Mode: AI-ONLY — keep existing ISO, stage/refresh AI sidecar only."
    c_warn "AI sidecar will be written at 2 GiB on $DEV (ISO not wiped)."
    read -rp "> type STAGE (all caps) to continue, anything else aborts: " confirm
    [[ "$confirm" == "STAGE" ]] || { c_info "aborted — nothing was touched"; exit 0; }
    ;;
  *)
    MODE=full
    c_info "Mode: FULL — write ISO + stage AI (if required)."
    c_warn "EVERYTHING on $DEV will be destroyed."
    read -rp "> type ERASE (all caps) to continue, anything else aborts: " confirm
    [[ "$confirm" == "ERASE" ]] || { c_info "aborted — nothing was touched"; exit 0; }
    ;;
esac

# ── prepare AI when needed ───────────────────────────────────────────────────
fail_ai() {
  c_warn "$*"
  c_warn "Local AI is required for a full offline install (Hub ASSISTANT + Frank)."
  c_warn "Fix the problem, or set FOUNDATION_NO_MODEL=1 only if the target already has AI."
  exit 1
}

prepare_ai() {
  if (( REQUIRE_AI == 0 )); then
    c_info "FOUNDATION_NO_MODEL=1 — not staging the AI."
    return 0
  fi
  if [[ ! -f "$AI_MODEL" ]]; then
    c_info "downloading the AI model (~1.2 GB) to stage on the stick…"
    curl -fL --progress-bar -o "$AI_MODEL" "$MODEL_URL" || fail_ai "model download failed"
  fi
  if ! _is_gzip_file "$AI_RUNTIME"; then
    local surl="${FOUNDATION_AI_SERVER_URL:-}" json
    if [[ -z "$surl" ]]; then
      json="$(curl -fsSL "https://api.github.com/repos/$GITHUB_REPO/releases" 2>/dev/null || true)"
      surl="$(printf '%s' "$json" | grep -o '"browser_download_url": *"[^"]*foundation-ai-runtime[^"]*\.tar\.gz"' \
        | grep -v sha256 | head -1 | cut -d'"' -f4 || true)"
      [[ -n "$surl" ]] || surl="$(printf '%s' "$json" \
        | grep -o '"browser_download_url": *"[^"]*foundation-ai-llama-server[^"]*\.tar\.gz"' \
        | grep -v sha256 | head -1 | cut -d'"' -f4 || true)"
      [[ -n "$surl" ]] || surl="$(printf '%s' "$json" \
        | grep -o '"browser_download_url": *"[^"]*foundation-ai-llama-server[^"]*"' \
        | grep -v sha256 | grep -v '\.tar\.gz' | head -1 | cut -d'"' -f4 || true)"
    fi
    [[ -n "$surl" ]] || fail_ai "no foundation-ai-runtime on any release (wait for build-ai-binary CI)"
    local dest="$AI_RUNTIME"
    [[ "$surl" == *.tar.gz* ]] || dest="$AI_SERVER"
    c_info "downloading the AI runtime…"
    curl -fL --progress-bar -o "$dest" "$surl" || { rm -f "$dest"; fail_ai "runtime download failed"; }
  fi
  if [[ -f "$AI_SERVER" ]] && ! _is_gzip_file "$AI_RUNTIME"; then
    c_warn "legacy bare llama-server ELF present; delete it and re-run to fetch the runtime tarball"
  fi
  if _is_gzip_file "$AI_RUNTIME"; then STAGE_SERVER="$AI_RUNTIME"
  else fail_ai "AI runtime tarball missing (foundation-ai-runtime-*.tar.gz from the release)"
  fi
  (( ISO_BYTES < STAGE_OFFSET )) || fail_ai "ISO exceeds the 2 GiB staging offset"
  local magic
  magic="$(dd if="$AI_MODEL" bs=1 count=4 2>/dev/null || true)"
  [[ "$magic" == "GGUF" ]] || fail_ai "model is not a GGUF file (magic='$magic')"
  local msize ssize
  msize=$(file_size "$AI_MODEL")
  ssize=$(file_size "$STAGE_SERVER")
  (( ssize > 0 )) || fail_ai "AI runtime missing or empty"
  local stick_bytes=""
  stick_bytes="$(lsblk -bndo SIZE "$DEV" 2>/dev/null | head -1 || true)"
  if [[ "$stick_bytes" =~ ^[0-9]+$ ]]; then
    local need=$(( STAGE_OFFSET + STAGE_HDR + msize + ssize + 1048576 ))
    (( stick_bytes >= need )) || fail_ai "stick too small to stage AI (need ~$((need / 1024 / 1024)) MB)"
  fi
  STAGE_AI=1
  c_ok "AI ready to stage (model $((msize / 1024 / 1024)) MB + runtime)"
}

if [[ "$MODE" == "full" || "$MODE" == "ai_only" ]]; then
  prepare_ai
elif [[ "$MODE" == "iso_only" ]]; then
  if (( REQUIRE_AI == 1 && AI_MATCH == 1 )); then
    c_ok "keeping existing AI sidecar on the stick"
  elif (( REQUIRE_AI == 1 && AI_PRESENT == 1 )); then
    c_info "AI sidecar present; ISO-only mode leaves it as-is"
  elif (( REQUIRE_AI == 1 )); then
    c_warn "no usable AI sidecar on this stick and mode is ISO-only"
    c_warn "re-run without FOUNDATION_NO_MODEL for a full write if you need AI staged"
  fi
fi

write_ai_sidecar() {
  (( STAGE_AI == 1 )) || return 0
  [[ -n "$STAGE_SERVER" && -f "$STAGE_SERVER" ]] || return 0
  local msize ssize
  msize=$(file_size "$AI_MODEL")
  ssize=$(file_size "$STAGE_SERVER")
  local model_off=$(( STAGE_OFFSET + STAGE_HDR ))
  local srv_off=$(( model_off + ( (msize + STAGE_HDR - 1) / STAGE_HDR ) * STAGE_HDR ))
  local hdr="FOUNDATIONAI2
model_offset=$model_off
model_size=$msize
server_offset=$srv_off
server_size=$ssize
"
  local BS=1M; [[ "$OS" == "Darwin" ]] && BS=1m
  c_info "staging the AI into the stick's free space (raw-offset, no partition)…"
  { printf '%s' "$hdr"; head -c $(( STAGE_HDR - ${#hdr} )) /dev/zero; } \
    | dd of="$WRITE_DEV" bs="$BS" seek=$(( STAGE_OFFSET / 1048576 )) count=1 conv=notrunc 2>/dev/null
  dd if="$AI_MODEL" of="$WRITE_DEV" bs="$BS" seek=$(( model_off / 1048576 )) conv=notrunc 2>/dev/null \
    && c_ok "staged the AI model onto the stick ($msize bytes)."
  dd if="$STAGE_SERVER" of="$WRITE_DEV" bs="$BS" seek=$(( srv_off / 1048576 )) conv=notrunc 2>/dev/null \
    && c_ok "staged the AI runtime onto the stick ($ssize bytes)."
  sync
  local rb magic
  rb="$(dd if="$WRITE_DEV" bs=4096 skip=$(( STAGE_OFFSET / 4096 )) count=1 2>/dev/null | tr -d '\000')"
  if [[ "$rb" != FOUNDATIONAI2* ]]; then
    fail_ai "AI sidecar verification failed — FOUNDATIONAI2 header missing after write"
  fi
  magic="$(dd if="$WRITE_DEV" bs=1 skip="$model_off" count=4 2>/dev/null || true)"
  [[ "$magic" == "GGUF" ]] || fail_ai "AI sidecar verification failed — GGUF magic missing at model_offset"
  magic="$(dd if="$WRITE_DEV" bs=1 skip="$srv_off" count=2 2>/dev/null || true)"
  [[ "$magic" == $'\x1f\x8b' ]] || fail_ai "AI sidecar verification failed — runtime is not gzip at server_offset"
  c_ok "AI sidecar verified on the stick (model + runtime tarball)"
}

# ── 4. write ─────────────────────────────────────────────────────────────────
if [[ "$OS" == "Darwin" ]]; then
  diskutil unmountDisk force "$DEV" >/dev/null 2>&1 || true
else
  for part in $(lsblk -lnpo NAME "$DEV" 2>/dev/null | tail -n +2); do
    umount "$part" 2>/dev/null || true
  done
fi

if [[ "$MODE" == "ai_only" ]]; then
  write_ai_sidecar
elif [[ "$MODE" == "iso_only" ]]; then
  c_info "writing the installer in-place (conv=notrunc — AI region preserved)…"
  if [[ "$OS" == "Darwin" ]]; then
    dd if="$ISO" of="$WRITE_DEV" bs=4m conv=notrunc
  else
    dd if="$ISO" of="$WRITE_DEV" bs=4M status=progress conv=notrunc,fsync
  fi
  c_info "flushing…"
  sync
  if (( AI_PRESENT == 1 )); then
    rb="$(dd if="$WRITE_DEV" bs=4096 skip=$(( STAGE_OFFSET / 4096 )) count=1 2>/dev/null | tr -d '\000' || true)"
    if [[ "$rb" == FOUNDATIONAI2* ]]; then
      c_ok "existing AI sidecar still intact after ISO-only rewrite"
    else
      c_warn "AI sidecar no longer verifies after ISO rewrite — re-run full or stage AI"
    fi
  fi
else
  # full
  c_info "writing the installer (this takes a few minutes — do not unplug)…"
  if [[ "$OS" == "Darwin" ]]; then
    dd if="$ISO" of="$WRITE_DEV" bs=4m
  else
    dd if="$ISO" of="$WRITE_DEV" bs=4M status=progress conv=fsync
  fi
  c_info "flushing everything to the stick (can take a minute — do NOT unplug)…"
  sync
  write_ai_sidecar
fi

[[ "$OS" == "Darwin" ]] && { diskutil eject "$DEV" >/dev/null 2>&1 || true; }

echo
c_ok "All done — it is now safe to unplug the stick."
echo
case "$MODE" in
  ai_only)  c_ok "Mode used: AI-ONLY (ISO kept)." ;;
  iso_only) c_ok "Mode used: ISO-ONLY (AI sidecar preserved when present)." ;;
  *)        c_ok "Mode used: FULL write." ;;
esac
c_ok "Your Foundation TerminalOS install USB is ready. Next steps:"
echo
echo "  1. Unplug the stick and plug it into the computer you want to turn"
echo "     into Foundation TerminalOS."
echo "  2. Turn that computer on while tapping its boot-menu key (usually"
echo "     F12, F11, Esc, F2, or Del — it flashes on screen at power-on)."
echo "  3. Pick the USB stick from the boot menu."
echo "  4. Follow the on-screen installer. UPDATE refreshes an existing"
echo "     install; INSTALL / ERASE wipes a disk for a fresh machine."
echo
echo "  WARNING: the installer turns that computer into a locked-down,"
echo "  no-shell kiosk with an always-on overseer. Not for a machine you"
echo "  still need as a normal PC."
