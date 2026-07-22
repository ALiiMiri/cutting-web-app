#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.cutting-export-gate.previous.$(date +%Y%m%d%H%M%S)"
EXISTING_FILES='cutting_excel.py
cutting_web_app.py
database.py
db_migrations.py'
NEW_FILES='migrations/024_cutting_plan_snapshot.py
templates/confirm_excel_without_cutting.html'

/usr/bin/python3 -m py_compile \
    "$SOURCE/cutting_excel.py" \
    "$SOURCE/cutting_web_app.py" \
    "$SOURCE/database.py" \
    "$SOURCE/db_migrations.py" \
    "$SOURCE/migrations/024_cutting_plan_snapshot.py"

mkdir -p "$PREVIOUS"
for file in $EXISTING_FILES; do
    mkdir -p "$PREVIOUS/$(dirname "$file")"
    cp -a "$TARGET/$file" "$PREVIOUS/$file"
done
for file in $NEW_FILES; do
    if [ -f "$TARGET/$file" ]; then
        mkdir -p "$PREVIOUS/$(dirname "$file")"
        cp -a "$TARGET/$file" "$PREVIOUS/$file"
    fi
done

systemctl stop cutting-web-app.service

rollback_publish() {
    for file in $EXISTING_FILES; do
        cp -a "$PREVIOUS/$file" "$TARGET/$file"
        chown root:cuttingapp "$TARGET/$file"
        chmod 0640 "$TARGET/$file"
    done
    for file in $NEW_FILES; do
        if [ -f "$PREVIOUS/$file" ]; then
            cp -a "$PREVIOUS/$file" "$TARGET/$file"
            chown root:cuttingapp "$TARGET/$file"
            chmod 0640 "$TARGET/$file"
        else
            rm -f "$TARGET/$file"
        fi
    done
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap rollback_publish EXIT HUP INT TERM

for file in $EXISTING_FILES $NEW_FILES; do
    mkdir -p "$TARGET/$(dirname "$file")"
    cp "$SOURCE/$file" "$TARGET/$file"
    chown root:cuttingapp "$TARGET/$file"
    chmod 0640 "$TARGET/$file"
done

/usr/bin/python3 "$TARGET/safe_upgrade.py"
systemctl start cutting-web-app.service

attempt=0
while [ "$attempt" -lt 10 ]; do
    if systemctl is-active --quiet cutting-web-app.service; then
        trap - EXIT HUP INT TERM
        echo "CUTTING_EXPORT_GATE_PUBLISH_OK previous=$PREVIOUS"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

echo "Cutting web app did not become active; restoring previous files." >&2
exit 1
