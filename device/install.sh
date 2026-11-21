#!/usr/bin/env bash
# Turn a fresh Raspberry Pi OS Lite (64-bit) into the thermal printer.
#
#   curl -fsSL https://raw.githubusercontent.com/schaferjart/POS-thermal-printer/stable/device/install.sh | sudo bash
#
# or, from a checkout:  sudo ./device/install.sh
# With your own cloud (see device/printer.env.example):
#   curl ... | sudo PRINTER_CLOUD_URL=https://<ref>.supabase.co PRINTER_CLOUD_KEY=sb_publishable_... bash
# Safe to run again: every step checks before it changes anything.
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/schaferjart/POS-thermal-printer.git}
BRANCH=${BRANCH:-stable}
DIR=/opt/printer
QUEUE=Thermal80
ZJ_COMMIT=${ZJ_COMMIT:-master}     # klirichek/zj-58; pin a sha once tested

[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }
log() { printf '\n== %s\n' "$*"; }
# put FILE < content: write FILE; true only if that changed it
put() { local t; t=$(mktemp); cat > "$t"
        if cmp -s "$t" "$1"; then rm -f "$t"; return 1; fi
        install -D -m 644 "$t" "$1"; rm -f "$t"; }

log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  git curl iw cups cups-filters avahi-daemon libnss-mdns \
  python3 python3-venv python3-flask python3-pil python3-yaml python3-qrcode

log "code in $DIR"
SRC=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd || true)
if [ -d "$DIR/.git" ]; then
  :                                             # already installed; the updater owns it
elif [ -n "$SRC" ] && [ -f "$SRC/device/printerd.py" ] && [ "$SRC" != "$DIR" ]; then
  mkdir -p "$DIR" && (cd "$SRC" && tar --exclude=.venv -cf - .) | tar -xf - -C "$DIR"   # from a checkout
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$DIR"
fi

log "python env (apt packages + python-escpos, which Debian doesn't package)"
[ -x "$DIR/.venv/bin/python" ] || python3 -m venv --system-site-packages "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/device/requirements.txt"

log "cloud settings"
install -d -m 755 /etc/printer
if [ -n "${PRINTER_CLOUD_URL:-}" ] && [ -n "${PRINTER_CLOUD_KEY:-}" ]; then
  umask 027
  printf 'PRINTER_CLOUD_URL=%s\nPRINTER_CLOUD_KEY=%s\n' "$PRINTER_CLOUD_URL" "$PRINTER_CLOUD_KEY" > /etc/printer/printer.env
  umask 022
fi
[ -f /etc/printer/printer.env ] || echo "no /etc/printer/printer.env: cloud jobs off (see device/printer.env.example)"

log "usblp off (CUPS talks to the printer over libusb)"
echo "blacklist usblp" > /etc/modprobe.d/no-usblp.conf
modprobe -r usblp 2>/dev/null || true

log "zj-58 CUPS driver"
if [ ! -x /usr/lib/cups/filter/rastertozj ]; then
  BUILD_DEPS="build-essential cmake libcups2-dev libcupsimage2-dev"
  apt-get install -y -q --no-install-recommends $BUILD_DEPS
  tmp=$(mktemp -d)
  git clone -q https://github.com/klirichek/zj-58.git "$tmp/zj-58"
  git -C "$tmp/zj-58" checkout -q "$ZJ_COMMIT"
  cmake -S "$tmp/zj-58" -B "$tmp/build" >/dev/null
  cmake --build "$tmp/build" >/dev/null
  cmake --install "$tmp/build" >/dev/null
  rm -rf "$tmp"
  apt-get purge -y -q --auto-remove $BUILD_DEPS >/dev/null   # keep the card lean
fi
PPD=$(find /usr/share/cups/model -name 'zj80.ppd*' | head -1)
[ -n "$PPD" ] || { echo "zj80.ppd not found after driver install" >&2; exit 1; }

log "hostname: print (page at http://print.local)"
# On the WiFi every printer is simply `print` (avahi makes a second one
# print-2). Its identity in the cloud is printer-<serial>, set by printerd.
NAME=print
if [ "$(hostname)" != "$NAME" ]; then
  hostnamectl set-hostname "$NAME"
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NAME/" /etc/hosts
  grep -q "^127.0.1.1" /etc/hosts || echo -e "127.0.1.1\t$NAME" >> /etc/hosts
  # CUPS and avahi read the hostname at start: restart both, or AirPrint
  # keeps advertising the old name and Macs can't reach the printer.
  systemctl restart avahi-daemon
  systemctl is-active -q cups && systemctl restart cups
fi

log "CUPS queue $QUEUE (shared, AirPrint via avahi)"
systemctl enable --now cups avahi-daemon >/dev/null
cupsctl --share-printers --no-remote-admin
if ! lpstat -p "$QUEUE" >/dev/null 2>&1; then
  URI=""
  for _ in $(seq 1 10); do                      # the backend can take a moment
    URI=$(lpinfo -v 2>/dev/null | awk '/usb:\/\//{print $2; exit}')
    [ -n "$URI" ] && break; sleep 2
  done
  [ -n "$URI" ] || { echo "no USB printer found: is it plugged in and on?" >&2; exit 1; }
  lpadmin -p "$QUEUE" -E -v "$URI" -P "$PPD" -o printer-is-shared=true \
          -D "Thermal printer 80mm" -L "$(hostname)"
  cupsenable "$QUEUE"; cupsaccept "$QUEUE"
fi
# Driver defaults are a 70x65mm page and no cutter. The longest page + the
# driver skipping blank page tails (BlankSpace=False) acts like a continuous
# roll: prints are as long as their content, one cut per job.
lpadmin -p "$QUEUE" -o PageSize=X70MMY3276MM -o BlankSpace=False -o CutMedia=EndOfJob -o OptionCutter=True \
        -o FeedDist=12feed39mm  # feed past the cutter before cutting. The driver says mm, but this
                                # printer counts ESC J in ~1/360in: "39mm" is ~22mm real (measured)
# The ZJ-80 PPD prints 560 of the head's 576 dots with 5mm margins: use all 576.
PPD_Q=/etc/cups/ppd/$QUEUE.ppd
if grep -q '^\*cupsModelNumber: 560' "$PPD_Q"; then
  sed -i -e 's/^\*cupsModelNumber: 560/*cupsModelNumber: 576/' \
         -e '/^\*ImageableArea/s/"14 0 212 /"11 0 215 /' \
         -e 's/^\*HWMargins: 14 0 14 0/*HWMargins: 11 0 11 0/' "$PPD_Q"
  systemctl restart cups
fi

log "few SD card writes: journal in RAM, CUPS logs warnings only"
# Swap is zram (in RAM) on Pi OS already: no swap file. printerd writes only
# /var/lib/printer, and only when something changes.
put /etc/systemd/journald.conf.d/printer.conf <<'EOF' && systemctl restart systemd-journald
[Journal]
Storage=volatile
RuntimeMaxUse=16M
EOF
if ! grep -q '^LogLevel warn' /etc/cups/cupsd.conf; then
  sed -i 's/^LogLevel .*/LogLevel warn/' /etc/cups/cupsd.conf
  systemctl restart cups
fi

log "services"
install -m 644 "$DIR/device/systemd/printerd.service"       /etc/systemd/system/
install -m 644 "$DIR/device/systemd/printer-update.service" /etc/systemd/system/
install -m 644 "$DIR/device/systemd/printer-update.timer"   /etc/systemd/system/
install -m 644 "$DIR/device/systemd/printer-setup-restore.service" /etc/systemd/system/
install -m 644 "$DIR/device/systemd/printer-setup-restore.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now printerd.service printer-update.timer >/dev/null
systemctl restart printerd.service

log "WiFi setup from a phone (comitup)"
# No known WiFi in reach -> the printer opens its own WiFi printer-<serial>
# (its cloud name) with comitup's page to pick a WiFi. Known WiFi, including
# the one Raspberry Pi Imager wrote, keeps working: comitup tries every saved
# WiFi first. comitup-web needs port 80 in hotspot mode: printerd lets go of
# it while the hotspot is up (the dispatcher script tells it) and takes it
# back on WiFi.
SERIAL=$(tr -d '\0' < /sys/firmware/devicetree/base/serial-number 2>/dev/null || true)
AP=printer-$(printf %s "$SERIAL" | tail -c 4 | tr 'A-Z' 'a-z')
[ -n "$SERIAL" ] || AP='printer-<nnnn>'          # not a Pi: comitup picks a number
install -m 755 "$DIR/device/nm-dispatcher.sh" /etc/NetworkManager/dispatcher.d/90-printer
# The hotspot has its own password, made once and kept across installs. It is
# printed on the setup slip (and inside its QR code), so only someone standing
# at the printer can join. WPA2 needs 8+ characters; no look-alike letters.
AP_PW=$(sed -n 's/^ap_password: *//p' /etc/comitup.conf 2>/dev/null || true)
[ -n "$AP_PW" ] || AP_PW=$(python3 -c "import secrets; print(''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(8)))")
CONF_CHANGED=0
put /etc/comitup.conf <<EOF && CONF_CHANGED=1
# Written by $DIR/device/install.sh (options: man comitup-conf)
ap_name: $AP
ap_password: $AP_PW
EOF
if ! dpkg -s comitup >/dev/null 2>&1; then
  apt-get install -y -q --no-install-recommends -o Dpkg::Options::=--force-confold comitup
elif [ "$CONF_CHANGED" = 1 ]; then
  systemctl restart comitup      # stays on the current WiFi when it is a saved one
fi

log "done"
echo "Print page: http://$NAME.local   AirPrint: Thermal printer 80mm @ $NAME"
echo "No known WiFi: join the WiFi $AP from a phone to pick one"
