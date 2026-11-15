#!/bin/sh
# NetworkManager runs this on every network change (installed by install.sh as
# /etc/NetworkManager/dispatcher.d/90-printer). When a WiFi connection comes up
# (home WiFi or comitup's hotspot), tell printerd: it checks what changed,
# frees or takes port 80, and prints a status slip if needed.
[ "$2" = up ] || exit 0
[ "$CONNECTION_ID" ] || exit 0
case "$(nmcli -g connection.type connection show uuid "$CONNECTION_UUID" 2>/dev/null)" in
  802-11-wireless) curl -s -m 5 -X POST http://127.0.0.1:9100/network >/dev/null || true ;;
esac
exit 0
