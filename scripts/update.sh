#!/usr/bin/env bash
# Boot-time self-update for TransitHub, run once per boot by
# transithub-update.service (as the 'pi' user) just before the sign starts.
#
# Best-effort by design: a failed pull (offline at boot, or local edits that
# block a fast-forward) or a failed install must NEVER stop the sign from coming
# up on the code it already has. So we log each step and always exit 0 — the unit
# is ordered Before the app and only Wants= (not Requires=) it, so even a hard
# failure here can't block startup.
#
# Caveat: this pulls code and reinstalls Python deps. It does NOT re-copy the
# systemd unit files — if a pull changes systemd/*.service you must re-copy them
# and `systemctl daemon-reload` by hand (see README).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "==> update: git pull --ff-only"
if git pull --ff-only; then
  echo "    [ok] checkout up to date"
else
  echo "    !! git pull failed (offline, or local changes block a fast-forward) —"
  echo "       keeping the current checkout."
fi

echo "==> update: ./install.sh"
if ./install.sh; then
  echo "    [ok] install complete"
else
  echo "    !! install.sh failed — keeping the current virtualenv/install."
fi

exit 0
