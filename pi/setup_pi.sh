#!/usr/bin/env bash
# Run this ON THE PI, once. Written for a Raspberry Pi 5 on Bookworm.
set -e
echo "== enabling I2C (the Grove base hat's analog ports need it) =="
sudo raspi-config nonint do_i2c 0

echo "== packages =="
sudo apt-get update -qq
# Pi 5 note: RPi.GPIO does NOT work on the Pi 5. The RP1 south bridge changed
# the GPIO interface and gpiozero must sit on lgpio instead. Installing
# RPi.GPIO here is how you get a confusing "cannot determine SOC" at 3am.
sudo apt-get install -y python3-gpiozero python3-lgpio i2c-tools

echo "== is the hat on the bus? =="
i2cdetect -y 1 || true
echo
echo "You should see 04 in that grid. That is the hat's ADC."
echo "If the grid is all '--', reseat the hat and reboot."
echo
echo "Now:  python3 buzzbox.py"
