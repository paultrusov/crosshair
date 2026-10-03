#!/usr/bin/env bash
# Run this ON THE PI, once.
set -e
echo "== enabling I2C (Grove base hat does nothing without it) =="
sudo raspi-config nonint do_i2c 0
echo "== packages =="
sudo apt-get update -qq
sudo apt-get install -y python3-gpiozero python3-rpi.gpio i2c-tools
echo "== check the hat is seen on the bus =="
i2cdetect -y 1 || true
echo
echo "Now run:  python3 buzzbox.py"
echo "If i2cdetect printed nothing but '--', reseat the hat and reboot."
