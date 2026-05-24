#!/usr/bin/env bash
# Reduce RGB LED matrix flicker on a Raspberry Pi.
#
# Applies the two permanent fixes from hzeller's rpi-rgb-led-matrix guide:
#   1. Disable the on-board sound (its PWM/timer conflicts with the panel —
#      the #1 cause of flicker on this hardware).
#   2. Reserve a CPU core for the panel (isolcpus) for a steadier refresh.
#
# Idempotent (safe to run repeatedly). Prompts before rebooting.
set -euo pipefail

# Bookworm uses /boot/firmware; older Raspberry Pi OS uses /boot.
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot
CONFIG="$BOOT/config.txt"
CMDLINE="$BOOT/cmdline.txt"
BLACKLIST=/etc/modprobe.d/blacklist-rgb-matrix.conf

echo "==> Boot directory: $BOOT"
changed=0

# 1a) Disable on-board sound in config.txt
if grep -qs '^dtparam=audio=off' "$CONFIG"; then
  echo "    [skip] on-board sound already disabled in config.txt"
else
  echo 'dtparam=audio=off' | sudo tee -a "$CONFIG" >/dev/null
  echo "    [done] added 'dtparam=audio=off' to config.txt"
  changed=1
fi

# 1b) Blacklist the sound module so it never loads
if grep -qs 'snd_bcm2835' "$BLACKLIST"; then
  echo "    [skip] snd_bcm2835 already blacklisted"
else
  echo 'blacklist snd_bcm2835' | sudo tee "$BLACKLIST" >/dev/null
  echo "    [done] blacklisted snd_bcm2835"
  changed=1
fi

# 2) Dedicate a CPU core to the panel (append to the single cmdline.txt line)
if grep -qs 'isolcpus' "$CMDLINE"; then
  echo "    [skip] isolcpus already set in cmdline.txt"
else
  sudo sed -i '1 s/$/ isolcpus=3/' "$CMDLINE"
  echo "    [done] added 'isolcpus=3' to cmdline.txt"
  changed=1
fi

echo
if [ "$changed" -eq 0 ]; then
  echo "==> Everything already applied — no reboot needed."
  exit 0
fi

echo "==> Flicker fixes applied; they take effect after a reboot."
echo "    (If any flicker remains afterward, raise 'gpio_slowdown' in config.yaml to 3 or 4.)"
echo
read -r -p "Reboot now? [y/N] " ans
case "$ans" in
  [yY] | [yY][eE][sS]) echo "Rebooting..."; sudo reboot ;;
  *) echo "Not rebooting. Apply later with: sudo reboot" ;;
esac
