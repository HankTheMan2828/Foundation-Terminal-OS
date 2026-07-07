#!/usr/bin/env bash
# create-foundation-usb.sh — make a Foundation TerminalOS install USB on
# Linux or macOS. Counterpart of Create-FoundationUSB.ps1 (Windows).
#
#   sudo ./create-foundation-usb.sh                # auto-finds/downloads the ISO
#   sudo ./create-foundation-usb.sh path/to.iso    # use a specific ISO
#
# Only removable/USB disks are ever offered — never the disk the running
# system lives on — and the write is gated behind typing ERASE in full.
set -euo pipefail

GITHUB_REPO="HankTheMan2828/Foundation-Terminal-OS"

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
  echo "  This writes the Foundation TerminalOS installer onto a USB stick."
  echo "  Everything currently on that stick will be erased."
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

echo
c_warn "EVERYTHING on $DEV will be destroyed."
read -rp "> type ERASE (all caps) to continue, anything else aborts: " confirm
[[ "$confirm" == "ERASE" ]] || { c_info "aborted — nothing was touched"; exit 0; }

# ── 3. write the image ───────────────────────────────────────────────────────
c_info "writing the installer (this takes a few minutes — do not unplug)…"
if [[ "$OS" == "Darwin" ]]; then
  diskutil unmountDisk force "$DEV" >/dev/null
  rdev="${DEV/\/dev\//\/dev\/r}"          # raw device is much faster on macOS
  dd if="$ISO" of="$rdev" bs=4m
  c_info "flushing everything to the stick (can take a minute — do NOT unplug)…"
  sync
  diskutil eject "$DEV" >/dev/null || true
else
  # unmount anything auto-mounted from the stick
  for part in $(lsblk -lnpo NAME "$DEV" | tail -n +2); do
    umount "$part" 2>/dev/null || true
  done
  dd if="$ISO" of="$DEV" bs=4M status=progress conv=fsync
  c_info "flushing everything to the stick (can take a minute — do NOT unplug)…"
  sync
fi

# ── 4. stage Frank's local AI onto the stick (best-effort) ───────────────────
# Frank runs a small LOCAL model (BitNet b1.58 2B4T, ~1.2 GB) too big to bake
# into the ISO (GitHub's 2 GiB asset cap). Drop it onto a FAT32 data partition
# labelled FOUNDATIONAI in the stick's free space; the OS installer stages it
# from there, so a fully-offline install already has the model. BEST-EFFORT: any
# failure is non-fatal — the target builds/fetches the model online instead.
# Skip with FOUNDATION_NO_MODEL=1.
MODEL_URL="${FOUNDATION_MODEL_URL:-https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf/resolve/main/ggml-model-i2_s.gguf}"
stage_ai() {
  [[ "${FOUNDATION_NO_MODEL:-0}" == "1" ]] && { c_info "FOUNDATION_NO_MODEL=1 — not staging the AI model."; return 0; }
  if [[ "$OS" != "Linux" ]]; then
    c_warn "AI-model staging is Linux-only for now; on macOS the target fetches the model online."
    return 0
  fi
  command -v parted >/dev/null 2>&1 && command -v mkfs.fat >/dev/null 2>&1 || {
    c_warn "parted/mkfs.fat not found — skipping AI staging (target fetches online)."; return 0; }
  local model="$SCRIPT_DIR/model.gguf"
  if [[ ! -f "$model" ]]; then
    c_info "downloading the AI model (~1.2 GB) to stage on the stick…"
    curl -fL --progress-bar -o "$model" "$MODEL_URL" || {
      c_warn "model download failed — skipping AI staging (target fetches online)."; return 0; }
  fi
  local start_mib=$(( ISO_BYTES / 1024 / 1024 + 8 ))   # just past the ISO image
  c_info "creating a data partition (FOUNDATIONAI) on the stick…"
  parted -s "$DEV" -- mkpart primary fat32 "${start_mib}MiB" 100% 2>/dev/null || {
    c_warn "could not add a data partition — skipping AI staging (target fetches online)."; return 0; }
  sync; partprobe "$DEV" 2>/dev/null || true; sleep 2
  local part; part="$(lsblk -lnpo NAME "$DEV" | tail -1)"
  mkfs.fat -F32 -n FOUNDATIONAI "$part" >/dev/null 2>&1 || {
    c_warn "could not format the data partition — skipping AI staging."; return 0; }
  local mnt; mnt="$(mktemp -d)"
  mount "$part" "$mnt" 2>/dev/null || { c_warn "could not mount the data partition — skipping AI staging."; rmdir "$mnt"; return 0; }
  cp "$model" "$mnt/model.gguf" && c_ok "staged the AI model onto the stick (partition FOUNDATIONAI)."
  # A prebuilt bitnet.cpp llama-server dropped next to this script rides along too.
  [[ -f "$SCRIPT_DIR/llama-server" ]] && cp "$SCRIPT_DIR/llama-server" "$mnt/llama-server"
  sync; umount "$mnt" 2>/dev/null || true; rmdir "$mnt" 2>/dev/null || true
}
stage_ai

echo
c_ok "All done — it is now safe to unplug the stick."
echo
c_ok "Your Foundation TerminalOS install USB is ready. Next steps:"
echo
echo "  1. Unplug the stick and plug it into the computer you want to turn"
echo "     into Foundation TerminalOS."
echo "  2. Turn that computer on while tapping its boot-menu key (usually"
echo "     F12, F11, Esc, F2, or Del — it flashes on screen at power-on)."
echo "  3. Pick the USB stick from the boot menu."
echo "  4. Follow the on-screen installer. The one destructive step — wiping"
echo "     that computer's disk — is gated behind typing ERASE, same as here."
echo
echo "  WARNING: the installer turns that computer into a locked-down,"
echo "  no-shell kiosk with an always-on overseer. Not for a machine you"
echo "  still need as a normal PC."
