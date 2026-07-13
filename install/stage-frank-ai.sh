#!/usr/bin/env bash
# stage-frank-ai.sh — copy Frank's local AI from a USB FOUNDATIONAI2 sidecar
# into a target tree's vendor/ (for install/11-frank-ai.sh).
#
# Usage (from the live installer shell, or during foundation-install):
#   bash /opt/terminal-os/install/stage-frank-ai.sh /mnt/opt/terminal-os
#   bash stage-frank-ai.sh /path/to/dest/repo [preferred_disk_name]
#
# Scans ALL whole-disk block devices for the FOUNDATIONAI2 header at the
# fixed 2 GiB offset (does not rely only on archiso bootmnt). That is what
# left installs as "idle: missing: runtime model" when bootmnt detection
# missed the stick or the stick had AI but the wrong disk was probed.
set -euo pipefail

STAGE_OFFSET=2147483648   # 2 GiB — keep in sync with USB creators + foundation-install

c_info()  { printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
c_ok()    { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
c_warn()  { printf '\033[1;31m[!]\033[0m %s\n' "$*"; }

DEST="${1:-}"
PREFER="${2:-}"

[[ -n "$DEST" && -d "$DEST" ]] || {
  c_warn "usage: $0 /path/to/dest/repo [disk_name e.g. sdb]"
  exit 1
}

# Return 0 if $1 (whole disk path) has FOUNDATIONAI2 at STAGE_OFFSET.
_has_ai_header() {
  local disk="$1" hdr
  [[ -b "$disk" ]] || return 1
  hdr="$(dd if="$disk" bs=4096 skip=$((STAGE_OFFSET / 4096)) count=1 2>/dev/null | tr -d '\000' || true)"
  [[ "$hdr" == FOUNDATIONAI2* ]]
}

# Print whole-disk names to try (prefer first, then USB, then every disk).
_candidate_disks() {
  local name tran typ seen="|"
  if [[ -n "$PREFER" ]]; then
    name="${PREFER#/dev/}"
    echo "$name"
    seen="${seen}${name}|"
  fi
  # USB whole disks first
  while read -r name typ tran; do
    [[ "$typ" == "disk" ]] || continue
    [[ "$seen" == *"|$name|"* ]] && continue
    if [[ "${tran:-}" == "usb" ]]; then
      echo "$name"
      seen="${seen}${name}|"
    fi
  done < <(lsblk -dn -o NAME,TYPE,TRAN 2>/dev/null || true)
  # Then every other whole disk (SATA USB bridges often report TRAN empty)
  while read -r name typ; do
    [[ "$typ" == "disk" ]] || continue
    [[ "$seen" == *"|$name|"* ]] && continue
    echo "$name"
    seen="${seen}${name}|"
  done < <(lsblk -dn -o NAME,TYPE 2>/dev/null || true)
}

# Prefer archiso bootmnt's underlying disk when available.
_bootmnt_disk() {
  local live_src live_disk="" cand
  live_src="$(findmnt -no SOURCE /run/archiso/bootmnt 2>/dev/null || true)"
  if [[ -n "$live_src" && -b "$live_src" ]]; then
    live_disk="$(lsblk -no pkname "$live_src" 2>/dev/null | head -1 || true)"
    [[ -z "$live_disk" ]] && live_disk="$(basename "$live_src")"
    # loop/device-mapper: not a real stick — ignore
    case "$live_disk" in
      loop*|dm-*|ram*) live_disk="" ;;
    esac
  fi
  if [[ -z "$live_disk" ]]; then
    for cand in /run/archiso/bootmnt /run/archiso/copytoram; do
      live_src="$(findmnt -no SOURCE "$cand" 2>/dev/null || true)"
      [[ -n "$live_src" && -b "$live_src" ]] || continue
      live_disk="$(lsblk -no pkname "$live_src" 2>/dev/null | head -1 || true)"
      [[ -z "$live_disk" ]] && live_disk="$(basename "$live_src")"
      case "$live_disk" in loop*|dm-*|ram*) live_disk="" ;; esac
      [[ -n "$live_disk" ]] && break
    done
  fi
  [[ -n "$live_disk" ]] && echo "$live_disk"
}

_stage_from_disk() {
  local disk="$1"
  local hdr mo ms so ss model_out server_out got magic magic2

  hdr="$(dd if="$disk" bs=4096 skip=$((STAGE_OFFSET / 4096)) count=1 2>/dev/null | tr -d '\000')"
  [[ "$hdr" == FOUNDATIONAI2* ]] || return 1

  mo="$(printf '%s\n' "$hdr" | sed -n 's/^model_offset=//p'  | head -1)"
  ms="$(printf '%s\n' "$hdr" | sed -n 's/^model_size=//p'    | head -1)"
  so="$(printf '%s\n' "$hdr" | sed -n 's/^server_offset=//p' | head -1)"
  ss="$(printf '%s\n' "$hdr" | sed -n 's/^server_size=//p'   | head -1)"
  [[ "$mo" =~ ^[0-9]+$ && "$ms" =~ ^[0-9]+$ && "$ms" -gt 0 ]] || {
    c_warn "AI header unreadable on $disk — skipping"; return 1; }
  if (( mo < STAGE_OFFSET + 4096 || ms > 4294967296 )); then
    c_warn "AI header offsets look wrong on $disk (mo=$mo ms=$ms) — refusing"
    return 1
  fi

  mkdir -p "$DEST/vendor/models" "$DEST/vendor/bitnet"
  model_out="$DEST/vendor/models/model.gguf"
  server_out="$DEST/vendor/bitnet/llama-server"

  c_info "reading staged AI model from $disk ($ms bytes)…"
  if ! dd if="$disk" of="$model_out" bs=1M iflag=skip_bytes,count_bytes \
        skip="$mo" count="$ms" status=none 2>/dev/null; then
    c_warn "could not read the staged model from $disk"
    rm -f "$model_out"; return 1
  fi
  got="$(stat -c %s "$model_out" 2>/dev/null || stat -f %z "$model_out" 2>/dev/null || echo 0)"
  if [[ "$got" != "$ms" ]]; then
    c_warn "staged model size mismatch (got $got, expected $ms) — discarding"
    rm -f "$model_out"; return 1
  fi
  magic="$(dd if="$model_out" bs=1 count=4 2>/dev/null || true)"
  if [[ "$magic" != "GGUF" ]]; then
    c_warn "staged model is not a GGUF file (bad magic) — discarding"
    rm -f "$model_out"; return 1
  fi
  c_ok "staged AI model from $disk ($ms bytes) → $model_out"

  if [[ "$ss" =~ ^[0-9]+$ && "$ss" -gt 0 && "$so" =~ ^[0-9]+$ ]]; then
    if dd if="$disk" of="$server_out" bs=1M iflag=skip_bytes,count_bytes \
          skip="$so" count="$ss" status=none 2>/dev/null; then
      got="$(stat -c %s "$server_out" 2>/dev/null || stat -f %z "$server_out" 2>/dev/null || echo 0)"
      if [[ "$got" != "$ss" ]]; then
        c_warn "staged server size mismatch (got $got, expected $ss) — discarding"
        rm -f "$server_out"
      else
        magic="$(dd if="$server_out" bs=1 count=4 2>/dev/null || true)"
        magic2="$(dd if="$server_out" bs=1 count=2 2>/dev/null || true)"
        if [[ "$magic2" == $'\x1f\x8b' ]]; then
          cp -a "$server_out" "$DEST/vendor/bitnet/runtime.tar.gz"
          chmod 0644 "$DEST/vendor/bitnet/runtime.tar.gz"
          c_ok "staged AI runtime tarball from $disk ($ss bytes)"
        elif [[ "$magic" == $'\x7fELF' ]]; then
          chmod +x "$server_out"
          c_warn "staged bare ELF llama-server (no bundled libs) — may not start"
          c_ok "staged AI server ELF from $disk ($ss bytes)"
        else
          c_warn "staged server is neither gzip runtime nor ELF — discarding"
          rm -f "$server_out"
        fi
      fi
    else
      c_warn "could not read the staged AI server from $disk"
    fi
  else
    c_warn "USB has the model but no AI server/runtime in the header"
  fi

  if [[ -f "$model_out" ]] && { [[ -f "$DEST/vendor/bitnet/runtime.tar.gz" ]] \
       || [[ -f "$server_out" ]]; }; then
    c_ok "AI payload ready for install/11-frank-ai.sh (local BitNet)"
    return 0
  fi
  [[ -f "$model_out" ]] && c_warn "partial AI payload (model only)"
  return 1
}

# ── main ─────────────────────────────────────────────────────────────────────
boot="$(_bootmnt_disk || true)"
[[ -n "$boot" && -z "$PREFER" ]] && PREFER="$boot"

c_info "looking for FOUNDATIONAI2 AI sidecar (offset ${STAGE_OFFSET})…"
tried=0
while read -r name; do
  [[ -n "$name" ]] || continue
  tried=$((tried + 1))
  if _has_ai_header "/dev/$name"; then
    c_ok "found FOUNDATIONAI2 on /dev/$name"
    if _stage_from_disk "/dev/$name"; then
      exit 0
    fi
    c_warn "header on /dev/$name but stage failed — trying other disks"
  else
    c_info "no AI header on /dev/$name"
  fi
done < <(_candidate_disks)

if (( tried == 0 )); then
  c_warn "no block devices to scan — Frank runs rule-based (AI idle)"
else
  c_warn "no FOUNDATIONAI2 sidecar on any disk (scanned $tried) — AI idle"
  c_warn "Rewrite the stick with Create-FoundationUSB.ps1 (not Rufus) and"
  c_warn "confirm it prints 'AI sidecar verified'. Then UPDATE again."
fi
exit 0
