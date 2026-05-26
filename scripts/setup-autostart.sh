#!/usr/bin/env bash
# One-shot, idempotent setup of TransitHub's systemd autostart.
#
# Installs and enables both units, pointed at THIS checkout (wherever it lives):
#   * transithub.service         — the sign, Restart=always (auto-restart on crash)
#   * transithub-update.service  — boot-time `git pull` + `./install.sh`, before the sign
#
# Safe to run as many times as you like. Each run re-renders the unit files for
# this checkout + owner, reloads systemd, (re)enables and (re)starts the services,
# clears any failed state, and prints a status summary. Re-run it whenever the unit
# files change, the checkout moves, or a service gets wedged — it's self-healing.
#
# Usage:  sudo ./scripts/setup-autostart.sh   (re-execs itself with sudo if needed)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR=/etc/systemd/system
UNITS=(transithub-update.service transithub.service)

# --- need root to write /etc/systemd and drive systemctl ---
if [ "$(id -u)" -ne 0 ]; then
  echo "==> Re-running with sudo (root needed for systemd)"
  exec sudo -E bash "$0" "$@"
fi
command -v systemctl >/dev/null 2>&1 || {
  echo "!! systemctl not found — this host doesn't use systemd. Aborting."; exit 1; }

OWNER="$(stat -c '%U' "$HERE")"        # owns the checkout; runs git pull + install.sh
echo "==> Setting up TransitHub autostart"
echo "    checkout: $HERE"
echo "    owner:    $OWNER   (self-update runs as this user; the sign runs as root)"

# --- render + install both units, pointed at this checkout (idempotent) ---
for u in "${UNITS[@]}"; do
  src="$HERE/systemd/$u"
  dst="$UNIT_DIR/$u"
  [ -f "$src" ] || { echo "!! missing $src — not a full checkout? Aborting."; exit 1; }
  tmp="$(mktemp)"
  # Point the units at this checkout, and run the self-update as the checkout owner.
  sed -e "s|/home/pi/transithub|$HERE|g" \
      -e "s|^User=pi\$|User=$OWNER|" \
      "$src" > "$tmp"
  if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then
    echo "    [unchanged] $dst"; rm -f "$tmp"
  else
    install -m 0644 "$tmp" "$dst" && rm -f "$tmp"
    echo "    [installed] $dst"
  fi
done

echo "==> systemctl daemon-reload"
systemctl daemon-reload

echo "==> Enabling units (start on every boot)"
systemctl enable "${UNITS[@]}" >/dev/null

echo "==> Clearing any failed state and (re)starting"
for u in "${UNITS[@]}"; do systemctl reset-failed "$u" 2>/dev/null || true; done
# The update unit is one-shot (best-effort): run it now, but never let it block setup.
systemctl restart transithub-update.service \
  || echo "    !! self-update reported a problem (best-effort) — see: journalctl -u transithub-update -b"
systemctl restart transithub.service

# --- report ---
echo
echo "==> Status"
for u in "${UNITS[@]}"; do
  enabled="$(systemctl is-enabled "$u" 2>/dev/null || echo '?')"
  active="$(systemctl is-active "$u" 2>/dev/null || echo '?')"
  printf "    %-26s enabled=%-9s active=%s\n" "$u" "$enabled" "$active"
done

# The sign is the long-running unit and must end up active. The update unit is
# one-shot, so 'inactive' after a clean run is expected — not a failure.
if [ "$(systemctl is-active transithub.service 2>/dev/null)" = "active" ]; then
  echo
  echo "==> Done. The sign is running, and will auto-start + self-update on every boot."
  echo "    Sign logs:    journalctl -u transithub -f"
  echo "    Update logs:  journalctl -u transithub-update -b"
else
  echo
  echo "!! transithub.service is not active — recent logs:"
  journalctl -u transithub.service -n 25 --no-pager 2>/dev/null || true
  echo
  echo "==> Finished with problems (see above). Fix, then re-run: sudo $0"
  exit 1
fi
