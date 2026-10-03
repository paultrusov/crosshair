#!/usr/bin/env bash
# The one step that needs root: write the OS image to the SD card.
# Everything else (wifi, ssh, user, gadget mode) is configured afterwards
# by pi/configure.sh, which needs no privileges.
#
#   ./pi/flash.sh /dev/disk4
set -euo pipefail
DISK="${1:?usage: ./pi/flash.sh /dev/diskN}"
HERE="$(cd "$(dirname "$0")" && pwd)"
IMGXZ="$HERE/../.img/rpi.img.xz"

[ -f "$IMGXZ" ] || { echo "image missing: $IMGXZ"; exit 1; }

# Refuse to touch anything that is not a small external disk.
diskutil info "$DISK" | grep -q "Device Location:.*External" || {
  echo "REFUSING: $DISK is not external."; exit 1; }
SIZE=$(diskutil info -plist "$DISK" | plutil -extract TotalSize raw -)
if [ "$SIZE" -gt 137438953472 ]; then
  echo "REFUSING: $DISK is $((SIZE/1000000000)) GB, too big to be the SD card."
  exit 1
fi

echo "Target: $DISK  ($((SIZE/1000000000)) GB, external, currently blank)"
echo "Everything on it will be erased."
read -r -p "Type ERASE to continue: " C
[ "$C" = "ERASE" ] || { echo "aborted"; exit 1; }

diskutil unmountDisk "$DISK"
echo "Writing. ~3 GB, a few minutes. Your password is for sudo."
xzcat "$IMGXZ" | sudo dd of="${DISK/disk/rdisk}" bs=4m
sync
sleep 3
diskutil mountDisk "$DISK" || true
echo
echo "Image written. Tell Claude and it will configure the rest."
