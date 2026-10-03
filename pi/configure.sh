#!/usr/bin/env bash
# Configure a freshly flashed card. No root needed: the boot partition is
# FAT32 and mounts user-writable.
#
#   WIFI_PASS='...' ./pi/configure.sh "<ssid>"
set -euo pipefail
SSID="${1:?usage: WIFI_PASS=... ./pi/configure.sh \"<ssid>\"}"
: "${WIFI_PASS:?set WIFI_PASS}"
HERE="$(cd "$(dirname "$0")" && pwd)"
HOSTNAME="crosshair"
USERNAME="paul"

BOOT=""
for v in /Volumes/*; do [ -f "$v/config.txt" ] && BOOT="$v"; done
[ -n "$BOOT" ] || { echo "no boot partition mounted; is the card in?"; exit 1; }
echo "boot partition: $BOOT"

PUB=$(cat "$HERE/keys/crosshair_pi.pub")
# The account needs a password even though we log in by key. Generated here,
# saved locally, used nowhere else.
# No pipes here on purpose: `tr | head -c` makes tr take SIGPIPE, which
# under `set -o pipefail` kills this script with no message at all.
PLAIN=$(openssl rand -hex 10)
HASH=$(printf '%s' "$PLAIN" | openssl passwd -6 -stdin)
printf '%s\n' "$PLAIN" > "$HERE/keys/pi-password.txt"
chmod 600 "$HERE/keys/pi-password.txt"

cat > "$BOOT/custom.toml" <<TOML
config_version = 1

[system]
hostname = "$HOSTNAME"

[user]
name = "$USERNAME"
password = "$HASH"
password_encrypted = true

[ssh]
enabled = true
password_authentication = false
authorized_keys = [ "$PUB" ]

[wlan]
ssid = "$SSID"
password = "$WIFI_PASS"
password_encrypted = false
hidden = false
country = "US"

[locale]
keymap = "us"
timezone = "America/New_York"
TOML

# Second way in: USB gadget ethernet over the Pi's own USB-C port, so a
# flaky hotspot cannot strand us.
# Must match our own marker, not any dwc2 line: the stock config.txt
# already carries "dtoverlay=dwc2,dr_mode=host" under [cm5], so a loose
# grep silently skips this whole block and gadget mode never works.
grep -q "^# crosshair: USB gadget" "$BOOT/config.txt" || cat >> "$BOOT/config.txt" <<'CFG'

# crosshair: USB gadget mode. The Pi appears to the laptop as a network
# adapter over the same USB-C cable that powers it.
dtoverlay=dwc2,dr_mode=peripheral
# Let the Pi 5 draw full current from a supply that does not advertise 5A.
usb_max_current_enable=1
CFG
grep -q "modules-load=dwc2" "$BOOT/cmdline.txt" || \
  sed -i '' 's/rootwait/rootwait modules-load=dwc2,g_ether/' "$BOOT/cmdline.txt"

sync
echo "configured for ssid: $SSID   host: $HOSTNAME.local   user: $USERNAME"
diskutil eject "$BOOT" >/dev/null 2>&1 || diskutil eject /dev/disk4 || true
echo "Card ejected. Put it in the Pi, give it real power, wait 90 seconds."
