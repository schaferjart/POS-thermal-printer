#!/usr/bin/env bash
# Daily: pull the tracked branch; on change, re-run install.sh if it changed,
# then restart the service.
# ponytail: no rollback yet. Add a health check + `git reset --hard $old` when
# a bad release ever reaches a printer.
set -euo pipefail
cd /opt/printer
branch=$(git rev-parse --abbrev-ref HEAD)
old=$(git rev-parse HEAD)
git fetch -q origin "$branch"
new=$(git rev-parse "origin/$branch")
[ "$old" = "$new" ] && exit 0

git reset -q --hard "$new"
echo "updated $branch ${old:0:7} -> ${new:0:7}"
if ! git diff --quiet "$old" "$new" -- device/install.sh device/systemd device/requirements.txt; then
  ./device/install.sh
else
  systemctl restart printerd.service
fi
