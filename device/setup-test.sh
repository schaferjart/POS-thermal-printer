#!/bin/bash
# Setup test: the printer acts as if it had been carried to a new place.
#
#   sudo /opt/printer/device/setup-test.sh           hide every saved WiFi, then reboot
#   sudo /opt/printer/device/setup-test.sh check     show what would be hidden
#   sudo /opt/printer/device/setup-test.sh restore   bring them back now
#
# After the reboot no saved WiFi is visible: comitup raises the setup hotspot and
# the setup slip prints (about 2-3 min). Set up a WiFi on the phone as a new owner
# would. 15 min after boot printer-setup-restore.timer brings the hidden WiFis
# back on its own; one that was set up again during the test keeps the new entry.
#
# comitup ignores NetworkManager's autoconnect flag (it tries every saved
# client WiFi), so the files themselves are moved aside.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
STASH=/var/lib/printer-setup-test
LIST=$STASH/list                 # original path <TAB> ssid <TAB> stashed copy

clients() {  # uuid <TAB> ssid <TAB> file, for every saved client WiFi (not the hotspot)
  nmcli -t -f UUID,TYPE,FILENAME con show | while IFS=: read -r uuid type file; do
    [ "$type" = 802-11-wireless ] || continue
    [ "$(nmcli -g 802-11-wireless.mode con show "$uuid")" != ap ] || continue
    printf '%s\t%s\t%s\n' "$uuid" "$(nmcli -g 802-11-wireless.ssid con show "$uuid")" "$file"
  done
}

restore() {
  [ -f "$LIST" ] || { echo "nothing hidden"; return 0; }
  known=$(clients | cut -f2)     # WiFis saved now, e.g. set up again during the test
  netplan=0
  while IFS=$'\t' read -r path ssid stashed; do
    if grep -qxF -- "$ssid" <<<"$known"; then
      rm -f "$stashed"           # set up again on the phone: keep that one
      echo "$ssid: set up again during the test, keeping the new entry"
    else
      mv "$stashed" "$path"
      case $path in /etc/netplan/*) netplan=1 ;; esac
      echo "$ssid: back"
    fi
  done <"$LIST"
  [ $netplan = 0 ] || netplan generate
  nmcli con reload
  rm -rf "$STASH"
  systemctl disable printer-setup-restore.timer 2>/dev/null || true
  # Still on the hotspot: let comitup look again now that the WiFis are back.
  iw dev wlan0 link | grep -q '^Connected' || systemctl restart comitup
}

if [ "${1:-}" = restore ]; then restore; exit; fi

[ ! -e "$STASH" ] || { echo "a setup test is already running (restore: $0 restore)" >&2; exit 1; }

# Find every file first; move nothing unless all of them are known.
plan=()
while IFS=$'\t' read -r uuid ssid file; do
  case $file in
    /run/NetworkManager/system-connections/netplan-*)
      src=$(grep -l -- "$uuid" /etc/netplan/*.yaml 2>/dev/null | head -1) ;;
    *) src=$file ;;
  esac
  [ -n "$src" ] && [ -f "$src" ] || { echo "can't find where '$ssid' is stored, nothing changed" >&2; exit 1; }
  ! grep -qE '^ *(ethernets|bonds|bridges|vlans):' "$src" \
    || { echo "$src holds more than WiFi, nothing changed" >&2; exit 1; }
  for p in "${plan[@]}"; do [ "${p%%$'\t'*}" != "$src" ] || continue 2; done
  plan+=("$src"$'\t'"$ssid")
done < <(clients)
[ ${#plan[@]} -gt 0 ] || { echo "no saved WiFi: this printer is already 'new'" >&2; exit 1; }
if [ "${1:-}" = check ]; then printf 'would hide: %s\n' "${plan[@]}"; exit; fi

mkdir -p "$STASH"
chmod 700 "$STASH"
i=0
for p in "${plan[@]}"; do
  src=${p%%$'\t'*}; ssid=${p#*$'\t'}
  i=$((i + 1)); stashed="$STASH/$i-$(basename "$src")"
  mv "$src" "$stashed"
  printf '%s\t%s\t%s\n' "$src" "$ssid" "$stashed" >>"$LIST"
  echo "hidden until 15 min after boot: $ssid"
done
systemctl enable printer-setup-restore.timer >/dev/null
echo "rebooting: expect the setup slip in about 3 minutes"
sleep 2
systemctl reboot
