#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.inventory-access.previous.$(date +%Y%m%d%H%M%S)"
FILES='security_utils.py
cutting_web_app.py
templates/index.html
templates/cutting_result.html'

mkdir -p "$PREVIOUS"
for file in $FILES; do
    mkdir -p "$PREVIOUS/$(dirname "$file")"
    cp -a "$TARGET/$file" "$PREVIOUS/$file"
done

systemctl stop cutting-web-app.service
restart_service() {
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap restart_service EXIT

for file in $FILES; do
    cp "$SOURCE/$file" "$TARGET/$file"
    chown root:cuttingapp "$TARGET/$file"
    chmod 0640 "$TARGET/$file"
done

systemctl start cutting-web-app.service
systemctl is-active --quiet cutting-web-app.service
trap - EXIT
echo "INVENTORY_ACCESS_PUBLISH_OK previous=$PREVIOUS"
