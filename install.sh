#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="${PYTHON:-python3}"
VENV="$HERE/.venv"
RGB_DIR="${RGB_DIR:-$HOME/.local/src/rpi-rgb-led-matrix}"

# --- system packages: only install what's missing (skips the slow apt update) ---
PKGS=(python3-dev python3-venv python3-pip git build-essential cmake ninja-build)
missing=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "==> Installing system packages: ${missing[*]}"
  sudo apt-get update
  sudo apt-get install -y "${missing[@]}"
else
  echo "==> System packages already present (skip)"
fi

# --- virtualenv ---
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating virtualenv"
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
else
  echo "==> Virtualenv present (skip)"
fi
PIP="$VENV/bin/pip"
VPY="$VENV/bin/python"

# --- rpi-rgb-led-matrix source ---
if [ ! -d "$RGB_DIR/.git" ]; then
  echo "==> Cloning rpi-rgb-led-matrix into $RGB_DIR"
  git clone --depth 1 https://github.com/hzeller/rpi-rgb-led-matrix.git "$RGB_DIR"
else
  echo "==> rpi-rgb-led-matrix source present (skip clone)"
fi

# --- LED matrix binding: skip the slow C++ build if it already imports ---
if "$VPY" -c "import rgbmatrix" 2>/dev/null; then
  echo "==> rgbmatrix binding already installed (skip build)"
else
  echo "==> Building + installing the LED matrix binding (compiles C++, a few minutes)"
  "$PIP" install "$RGB_DIR"
fi

# --- TransitHub + Python deps (fast & idempotent; installs nyct-gtfs etc.) ---
echo "==> Installing/updating TransitHub and its dependencies"
"$PIP" install -e .

# --- config ---
if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
  echo "==> Wrote config.yaml (edit it to set your trains)"
fi

# --- verify the venv actually has everything the app needs ---
echo "==> Verifying the virtualenv"
if "$VPY" -c "import rgbmatrix, nyct_gtfs, transithub" 2>/dev/null; then
  echo "    [ok] rgbmatrix, nyct_gtfs, transithub all import"
else
  echo "    !! something is missing — checking individually:"
  for m in rgbmatrix nyct_gtfs transithub; do
    if "$VPY" -c "import $m" 2>/dev/null; then echo "       [ok] $m"; else echo "       [MISSING] $m"; fi
  done
  echo "    !! Re-run ./install.sh. If a module is still MISSING, paste this output."
fi

echo
echo "==> Done. IMPORTANT: run via the venv binary so it finds its dependencies:"
echo "      sudo $VENV/bin/transithub --config $HERE/config.yaml"
echo "    Autostart: sudo cp systemd/transithub.service /etc/systemd/system/ \\"
echo "               && sudo systemctl enable --now transithub"
