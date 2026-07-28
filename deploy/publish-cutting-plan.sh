#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.cutting-plan.previous.$(date +%Y%m%d%H%M%S)"
FILES='cutting_calculator.py
cutting_web_app.py
database.py
templates/cutting_result.html'

/usr/bin/python3 -m py_compile \
    "$SOURCE/cutting_calculator.py" \
    "$SOURCE/cutting_web_app.py" \
    "$SOURCE/database.py"

mkdir -p "$PREVIOUS"
for file in $FILES; do
    mkdir -p "$PREVIOUS/$(dirname "$file")"
    cp -a "$TARGET/$file" "$PREVIOUS/$file"
done

systemctl stop cutting-web-app.service

rollback_publish() {
    for file in $FILES; do
        cp -a "$PREVIOUS/$file" "$TARGET/$file"
        chown root:cuttingapp "$TARGET/$file"
        chmod 0640 "$TARGET/$file"
    done
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap rollback_publish EXIT HUP INT TERM

for file in $FILES; do
    cp "$SOURCE/$file" "$TARGET/$file"
    chown root:cuttingapp "$TARGET/$file"
    chmod 0640 "$TARGET/$file"
done

systemctl start cutting-web-app.service

attempt=0
while [ "$attempt" -lt 10 ]; do
    if systemctl is-active --quiet cutting-web-app.service; then
        trap - EXIT HUP INT TERM
        echo "CUTTING_PLAN_PUBLISH_OK previous=$PREVIOUS"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

echo "Cutting web app did not become active; restoring previous files." >&2
exit 1
