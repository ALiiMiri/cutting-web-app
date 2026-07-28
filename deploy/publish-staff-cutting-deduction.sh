#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.staff-cutting.previous.$(date +%Y%m%d%H%M%S)"

FILES='security_utils.py
templates/cutting_result.html'

mkdir -p "$PREVIOUS/templates"
for file in $FILES; do
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

if ! systemctl start cutting-web-app.service; then
    for file in $FILES; do
        cp -a "$PREVIOUS/$file" "$TARGET/$file"
    done
    exit 1
fi
systemctl is-active --quiet cutting-web-app.service
trap - EXIT
echo "STAFF_CUTTING_DEDUCTION_PUBLISH_OK previous=$PREVIOUS"
