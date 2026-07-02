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
# GRUB for both firmware types — one bootloader config, and it matches the
# installed system (install/03 configures GRUB there too).
bootmodes=('bios.grub.mbr' 'bios.grub.eltorito'
           'uefi-x64.grub.esp' 'uefi-x64.grub.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
file_permissions=(
  ["/root"]="0:0:750"
  ["/usr/local/bin/foundation-install"]="0:0:755"
)
