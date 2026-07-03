#!/usr/bin/env bash
# shellcheck disable=SC2034
# archiso profile for the Foundation TerminalOS installer ISO (see image/README.md).
# Built by image/build-iso.sh — do not run mkarchiso against this directory
# directly; the build script stages it and embeds the repo + offline package
# repo first.

iso_name="foundation-terminalos"
iso_label="FOUNDATION_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="Foundation TerminalOS <from the Foundation>"
iso_application="Foundation TerminalOS installer"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
# archiso only does BIOS via syslinux; GRUB covers UEFI (and the installed
# system still gets plain GRUB for both firmware types via install/03).
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito' 'uefi.grub')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
file_permissions=(
  # Unlocked, empty-password root (same as the official Arch ISO): the LIVE
  # medium only. Without it the rescue ttys and systemd's emergency shell
  # (sulogin) are unreachable — a boot problem becomes undebuggable.
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/usr/local/bin/foundation-install"]="0:0:755"
)
