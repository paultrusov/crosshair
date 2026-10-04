#!/usr/bin/env bash
# Run this ON THE PI, once, from the repo root:   ./pi/setup_standalone.sh
# Sets up the no-laptop build (onboard.py) on a Raspberry Pi 5.
#
# Needs internet once, to fetch packages and the two models. After that it
# runs offline, and starts by itself at boot.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/crosshair-venv"
OUT="${OUT:-motor}"            # OUT=buzzer ./pi/setup_standalone.sh

echo "== system packages =="
sudo apt-get update -qq
# libportaudio2: microphone. libgl1: opencv's GUI build, which mediapipe drags in.
sudo apt-get install -y curl i2c-tools libportaudio2 libgl1 libglib2.0-0
sudo raspi-config nonint do_i2c 0 || true

echo "== python 3.11 =="
# MediaPipe's last release with the Pose API we use (0.10.18) has no build
# for Python 3.13, which is what current Raspberry Pi OS ships. uv fetches a
# private 3.11 instead of fighting the system one.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
[ -d "$VENV" ] || uv venv --python 3.11 "$VENV"

echo "== python packages (10-20 minutes the first time) =="
# gpiozero sits on lgpio on a Pi 5. RPi.GPIO does NOT work on a Pi 5.
uv pip install --python "$VENV/bin/python" \
  --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  torch "numpy<2" "mediapipe==0.10.18" transformers pillow \
  faster-whisper sounddevice gpiozero lgpio

echo "== downloading models so it works offline =="
"$VENV/bin/python" - <<'PY'
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
m = "google/owlvit-base-patch32"
AutoProcessor.from_pretrained(m); AutoModelForZeroShotObjectDetection.from_pretrained(m)
from faster_whisper import WhisperModel
WhisperModel("base.en", device="cpu", compute_type="int8")
print("models cached")
PY

echo "== start at boot =="
# buzzbox.py and onboard.py both want pin D5. Only one may run.
sudo tee /etc/systemd/system/crosshair.service >/dev/null <<UNIT
[Unit]
Description=Crosshair (standalone, no laptop)
After=sound.target

[Service]
User=$USER
SupplementaryGroups=audio video gpio
WorkingDirectory=$REPO
Environment=HF_HUB_OFFLINE=1
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python $REPO/onboard.py --out $OUT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable crosshair.service

echo
echo "Done. Test it by hand first (Ctrl-C to stop):"
echo "    $VENV/bin/python haptics.py --out $OUT      # every signal, then the button"
echo "    $VENV/bin/python onboard.py --out $OUT"
echo "Then either reboot, or:  sudo systemctl start crosshair"
echo "Logs:                    journalctl -u crosshair -f"
