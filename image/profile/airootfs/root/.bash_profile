# Live installer medium: tty1 goes straight into the installer. Any other VT
# (Ctrl-Alt-F2…) is a plain root rescue shell. If the installer exits or
# fails, you land back in a shell here — rerun with `foundation-install`.
if [[ "$(tty)" == "/dev/tty1" ]]; then
  foundation-install
fi
