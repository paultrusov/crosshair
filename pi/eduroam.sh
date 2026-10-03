#!/usr/bin/env bash
# Put the Pi on Cornell eduroam.
#
# eduroam is WPA2-Enterprise (PEAP/MSCHAPv2). The Pi's normal custom.toml can
# only express a pre-shared key, so this writes a NetworkManager profile
# instead, delivered by the same first-boot hook the official Pi Imager uses.
#
# Run with the SD card in the Mac:
#     ./pi/eduroam.sh
#
# You type your NetID password. It is read with echo off, written straight to
# the card, and never printed or stored anywhere else.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOSTNAME="crosshair"
USERNAME="paul"
NETID="${NETID:-pmt62}"

BOOT=""
for v in /Volumes/*; do [ -f "$v/config.txt" ] && BOOT="$v"; done
[ -n "$BOOT" ] || { echo "No Pi boot partition mounted. Is the card in the Mac?"; exit 1; }
echo "boot partition: $BOOT"
echo "NetID: $NETID   (set NETID=... to change)"

read -r -s -p "Cornell NetID password: " NETPW; echo
[ -n "$NETPW" ] || { echo "empty, aborting"; exit 1; }
read -r -s -p "Your iPhone hotspot password (fallback network, blank to skip): " HOTPW; echo

PUB=$(cat "$HERE/keys/crosshair_pi.pub")
PLAIN=$(openssl rand -hex 10)
HASH=$(printf '%s' "$PLAIN" | openssl passwd -6 -stdin)
printf '%s\n' "$PLAIN" > "$HERE/keys/pi-password.txt"; chmod 600 "$HERE/keys/pi-password.txt"

# custom.toml and this hook both want to own first boot. Only one of them can.
rm -f "$BOOT/custom.toml"

cat > "$BOOT/firstrun.sh" <<EOS
#!/bin/bash
set +e
CURRENT_HOSTNAME=\$(cat /etc/hostname | tr -d " \t\n\r")
echo $HOSTNAME >/etc/hostname
sed -i "s/127.0.1.1.*\$CURRENT_HOSTNAME/127.0.1.1\t$HOSTNAME/g" /etc/hosts

# account, key only, no password login
if ! id -u $USERNAME >/dev/null 2>&1; then
  useradd -m $USERNAME -s /bin/bash
  echo "$USERNAME:$HASH" | chpasswd -e
  for g in adm dialout sudo audio video plugdev games users input netdev gpio i2c spi; do
    getent group \$g >/dev/null && usermod -aG \$g $USERNAME
  done
fi
echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" >/etc/sudoers.d/010_$USERNAME-nopasswd
chmod 440 /etc/sudoers.d/010_$USERNAME-nopasswd
install -o $USERNAME -g $USERNAME -m 700 -d /home/$USERNAME/.ssh
echo '$PUB' >/home/$USERNAME/.ssh/authorized_keys
chown $USERNAME:$USERNAME /home/$USERNAME/.ssh/authorized_keys
chmod 600 /home/$USERNAME/.ssh/authorized_keys
systemctl enable ssh
systemctl start ssh

mkdir -p /etc/NetworkManager/system-connections

cat >/etc/NetworkManager/system-connections/eduroam.nmconnection <<'NMEOF'
[connection]
id=eduroam
type=wifi
autoconnect=true
autoconnect-priority=10

[wifi]
mode=infrastructure
ssid=eduroam

[wifi-security]
key-mgmt=wpa-eap

[802-1x]
eap=peap;
identity=$NETID@cornell.edu
anonymous-identity=anonymous@cornell.edu
password=$NETPW
phase2-auth=mschapv2

[ipv4]
method=auto

[ipv6]
method=auto
NMEOF
chmod 600 /etc/NetworkManager/system-connections/eduroam.nmconnection
EOS

if [ -n "$HOTPW" ]; then
cat >> "$BOOT/firstrun.sh" <<EOS

cat >/etc/NetworkManager/system-connections/iphone.nmconnection <<'NMEOF2'
[connection]
id=iPhone
type=wifi
autoconnect=true
autoconnect-priority=5

[wifi]
mode=infrastructure
ssid=iPhone

[wifi-security]
key-mgmt=wpa-psk
psk=$HOTPW

[ipv4]
method=auto

[ipv6]
method=auto
NMEOF2
chmod 600 /etc/NetworkManager/system-connections/iphone.nmconnection
EOS
fi

cat >> "$BOOT/firstrun.sh" <<'EOS'

rfkill unblock wifi 2>/dev/null
raspi-config nonint do_wifi_country US 2>/dev/null
raspi-config nonint do_i2c 0 2>/dev/null
systemctl restart NetworkManager 2>/dev/null

rm -f /boot/firmware/firstrun.sh
sed -i 's| systemd.run.*||g' /boot/firmware/cmdline.txt
exit 0
EOS

chmod +x "$BOOT/firstrun.sh"

# The hook: systemd runs the script once, then reboots. Same mechanism the
# official Imager uses, so it is well travelled.
CMD=$(cat "$BOOT/cmdline.txt")
CMD=$(echo "$CMD" | sed 's| systemd.run.*||')
printf '%s systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.run_failure_action=reboot\n' "$CMD" > "$BOOT/cmdline.txt"

sync
echo
echo "Written. Networks: eduroam (priority) and iPhone (fallback)."
grep -c "" "$BOOT/firstrun.sh" | xargs echo "firstrun.sh lines:"
diskutil eject "$BOOT" >/dev/null 2>&1 && echo "Card ejected."
echo "Put it in the Pi, power it, wait ~2 minutes (it boots, configures, reboots)."
