#!/usr/bin/env bash
# build-iso.sh — build the flashable Foundation TerminalOS installer ISO.
#
# What it does:
#   1. stages image/profile/ into a work dir
#   2. embeds THIS repo at /opt/terminal-os inside the live image
#   3. downloads every package the installed system needs into an offline
#      repo inside the image (so flashing + installing needs no network)
#   4. runs mkarchiso -> image/out/foundation-terminalos-<date>-x86_64.iso
#
# Where to run it: an Arch Linux machine (or container) with `archiso`
# installed, as root, with network for steps 3 and mkarchiso's own pacstrap.
# No Arch box? From this repo's root, with Docker:
#
#   docker run --privileged --rm -v "$PWD:/repo" archlinux:latest \
#     bash -c 'pacman -Syu --noconfirm archiso git && /repo/image/build-iso.sh'
#
# Flags/env:
#   --skip-offline-repo   build a smaller ISO with no embedded packages; the
#                         installer then needs network on the target machine
#   BAKE_PROFILE=<name>   also bundle a hardware profile's packages into the
#                         offline repo (the profile itself is always embedded;
#                         this only matters for its extra packages)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_DIR="$REPO_ROOT/image"
WORK="${FOUNDATION_IMG_WORK:-$IMAGE_DIR/work}"
OUT="${FOUNDATION_IMG_OUT:-$IMAGE_DIR/out}"

c_info()  { printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
c_ok()    { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
c_warn()  { printf '\033[1;31m[!]\033[0m %s\n' "$*"; }
c_step()  { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

SKIP_OFFLINE=0
for arg in "$@"; do
  case "$arg" in
    --skip-offline-repo) SKIP_OFFLINE=1 ;;
    *) c_warn "unknown flag: $arg"; exit 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { c_warn "must run as root (mkarchiso needs it)"; exit 1; }
command -v mkarchiso >/dev/null 2>&1 || {
  c_warn "mkarchiso not found — install it:  pacman -S archiso"
  c_warn "(building requires an Arch host or container; see image/README.md)"
  exit 1
}

# ── 1. stage the profile ──────────────────────────────────────────────────────
c_step "Staging archiso profile"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"
cp -r "$IMAGE_DIR/profile" "$WORK/profile"

# ── 2. embed the repo at /opt/terminal-os ────────────────────────────────────
c_step "Embedding the repo into the live image"
EMBED="$WORK/profile/airootfs/opt/terminal-os"
mkdir -p "$EMBED"
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # a clean snapshot of HEAD — build artifacts and untracked junk stay out
  git -C "$REPO_ROOT" archive HEAD | tar -x -C "$EMBED"
  c_ok "embedded git HEAD ($(git -C "$REPO_ROOT" rev-parse --short HEAD))"
else
  tar -C "$REPO_ROOT" --exclude=.git --exclude=image/work --exclude=image/out \
      -cf - . | tar -x -C "$EMBED"
  c_ok "embedded working tree (not a git checkout)"
fi
# The image/ pipeline itself is dead weight inside the image.
rm -rf "$EMBED/image"

# ── 3. offline package repo ──────────────────────────────────────────────────
if ((SKIP_OFFLINE)); then
  c_step "Skipping offline package repo (--skip-offline-repo)"
  c_warn "the installer will need network on the TARGET machine"
else
  c_step "Building the offline package repo"
  PKGDIR="$WORK/profile/airootfs/opt/foundation/pkgs"
  mkdir -p "$PKGDIR"
  DBTMP="$(mktemp -d)"

  # Everything foundation-install pacstraps: its own base set + the OS's
  # package list (+ optionally one profile's extras). Keep in sync with the
  # pkgs=(...) block in airootfs/usr/local/bin/foundation-install.
  PKGS=(base archlinux-keyring mkinitcpio grub efibootmgr)
  mapfile -t -O "${#PKGS[@]}" PKGS < <(
    sed -E 's/#.*$//; s/[[:space:]]+$//; /^[[:space:]]*$/d' \
      "$REPO_ROOT/install/packages.txt")
  if [[ -n "${BAKE_PROFILE:-}" ]]; then
    if [[ -f "$REPO_ROOT/profiles/$BAKE_PROFILE/packages.txt" ]]; then
      mapfile -t -O "${#PKGS[@]}" PKGS < <(
        sed -E 's/#.*$//; s/[[:space:]]+$//; /^[[:space:]]*$/d' \
          "$REPO_ROOT/profiles/$BAKE_PROFILE/packages.txt")
      c_info "including profile packages: $BAKE_PROFILE"
    else
      c_warn "BAKE_PROFILE=$BAKE_PROFILE has no packages.txt — ignoring"
    fi
  fi

  c_info "downloading ${#PKGS[@]} packages (plus dependencies)…"
  pacman -Syw --noconfirm --cachedir "$PKGDIR" --dbpath "$DBTMP" "${PKGS[@]}"
  rm -rf "$DBTMP"
  rm -f "$PKGDIR"/*.sig
  repo-add --quiet "$PKGDIR/foundation.db.tar.gz" "$PKGDIR"/*.pkg.tar.*
  c_ok "offline repo: $(ls "$PKGDIR"/*.pkg.tar.* | wc -l) packages"
fi

# ── 4. mkarchiso ─────────────────────────────────────────────────────────────
c_step "mkarchiso"
mkarchiso -v -w "$WORK/archiso" -o "$OUT" "$WORK/profile"

c_step "Done"
ISO="$(ls -t "$OUT"/foundation-terminalos-*.iso | head -1)"
c_ok "ISO: $ISO"
echo
echo "  Flash it (USB stick at /dev/sdX — check with lsblk first!):"
echo "    dd if=$ISO of=/dev/sdX bs=4M status=progress oflag=sync"
echo "  …or use Etcher/Ventoy. Then boot the target machine from USB,"
echo "  and follow the on-screen installer."
