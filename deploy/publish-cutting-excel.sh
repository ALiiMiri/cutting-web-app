#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.cutting-excel.previous.$(date +%Y%m%d%H%M%S)"

/usr/bin/python3 -m py_compile \
    "$SOURCE/cutting_excel.py" \
    "$SOURCE/cutting_web_app.py"

mkdir -p "$PREVIOUS"
cp -a "$TARGET/cutting_web_app.py" "$PREVIOUS/cutting_web_app.py"
if [ -f "$TARGET/cutting_excel.py" ]; then
    cp -a "$TARGET/cutting_excel.py" "$PREVIOUS/cutting_excel.py"
    touch "$PREVIOUS/cutting_excel.preexisting"
fi

systemctl stop cutting-web-app.service

rollback_publish() {
    cp -a "$PREVIOUS/cutting_web_app.py" "$TARGET/cutting_web_app.py"
    if [ -f "$PREVIOUS/cutting_excel.preexisting" ]; then
        cp -a "$PREVIOUS/cutting_excel.py" "$TARGET/cutting_excel.py"
    else
        rm -f "$TARGET/cutting_excel.py"
    fi
    chown root:cuttingapp "$TARGET/cutting_web_app.py"
    chmod 0640 "$TARGET/cutting_web_app.py"
    if [ -f "$TARGET/cutting_excel.py" ]; then
        chown root:cuttingapp "$TARGET/cutting_excel.py"
        chmod 0640 "$TARGET/cutting_excel.py"
    fi
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap rollback_publish EXIT HUP INT TERM

cp "$SOURCE/cutting_web_app.py" "$TARGET/cutting_web_app.py"
cp "$SOURCE/cutting_excel.py" "$TARGET/cutting_excel.py"
chown root:cuttingapp "$TARGET/cutting_web_app.py" "$TARGET/cutting_excel.py"
chmod 0640 "$TARGET/cutting_web_app.py" "$TARGET/cutting_excel.py"

systemctl start cutting-web-app.service

attempt=0
while [ "$attempt" -lt 10 ]; do
    if systemctl is-active --quiet cutting-web-app.service; then
        trap - EXIT HUP INT TERM
        echo "CUTTING_EXCEL_PUBLISH_OK previous=$PREVIOUS"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

echo "Cutting web app did not become active; restoring previous files." >&2
exit 1
