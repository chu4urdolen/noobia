#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run through pkexec or sudo.'; exit 1; }
test "$(hostname)" = syra || { echo 'This installer is for Syra only.'; exit 1; }
backup_dir="/var/backups/noobia-hardware-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
for file in /etc/default/gpsd /etc/udev/rules.d/70-noobia-usb.rules /etc/modprobe.d/noobia-rtw89.conf; do
    if test -f "$file"; then cp -a "$file" "$backup_dir/$(basename "$file")"; fi
done
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ubertooth gpsd gpsd-tools gpsd-clients python3-usb dkms
cat > /etc/udev/rules.d/70-noobia-usb.rules <<'RULES'
SUBSYSTEM=="usb", ATTR{idVendor}=="1d50", ATTR{idProduct}=="6002", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="001a", MODE="0660", GROUP="plugdev", TAG+="uaccess"
RULES
cat > /etc/default/gpsd <<'GPS'
START_DAEMON="true"
USBAUTO="true"
DEVICES="/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00"
GPSD_OPTIONS="-n"
GPS
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=1d50 --attr-match=idProduct=6002
udevadm trigger --subsystem-match=usb --attr-match=idVendor=2886 --attr-match=idProduct=001a
systemctl enable --now gpsd.socket
systemctl restart gpsd.service
driver=/noobia/rose-hardware/vendor/rtw89
test -f "$driver/rtw89_8852au_git.ko" || { echo 'Wi-Fi build has not passed; packages installed, driver skipped.'; exit 2; }
# Register the reviewed, pinned source for rebuilds on future kernel updates.
dkms install "$driver"
cat > /etc/modprobe.d/noobia-rtw89.conf <<'WIFI'
# TP-Link 2357:0141; firmware already supplied by firmware-realtek.
# Keep this hub-attached adapter in USB 2 mode; built-in Wi-Fi is untouched.
options rtw89_usb_git switch_usb_mode=n
blacklist rtw89_8852au
WIFI
modprobe rtw89_8852au_git
echo "Rose hardware installation complete. Backups: $backup_dir"
