#!/usr/bin/env bash
# One-time setup on Arch Linux (tested target: Lenovo T470s).
# Usage:  bash setup_arch.sh          (re-running is safe)
set -euo pipefail
cd "$(dirname "$0")"
VENV="${HYPOLAB_VENV:-$HOME/.venvs/hypolab}"

echo "==> system packages (python, git) via pacman"
sudo pacman -S --needed --noconfirm python python-pip git

echo "==> virtual environment at $VENV (keeps Arch's system python clean)"
python -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -e ".[cockpit,test]"

echo "==> private data folder ~/.hypolab (mode 700)"
mkdir -p "$HOME/.hypolab" && chmod 700 "$HOME/.hypolab"

echo "==> self-test (about five minutes; one test file at a time, so it fits in 8 GB)"
"$VENV/bin/python" tests/run_all.py

cat <<MSG

Done. Start working with:

    source $VENV/bin/activate
    cd $(pwd)
    python -m hypolab cockpit        # the Ideas app (127.0.0.1:2719) + the marimo gallery: cockpit, dataset scan,
                                     # quant basics (127.0.0.1:2718)

Everything starts in SANDBOX mode (offline practice market). To use your BRAIN account, open the cockpit's
Setup tab: switch to Live and log in there (the face-scan link appears on the page).
Upgrading from hypolab 1.0? The old Jupyter kernel can go:  jupyter kernelspec uninstall hypolab
MSG
