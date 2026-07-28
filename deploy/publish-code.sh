#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app/
TARGET=/opt/cutting-web-app/
PREVIOUS=/opt/cutting-web-app.previous/

systemctl stop cutting-web-app.service
restart_service() {
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap restart_service EXIT

if [ -d "$TARGET" ]; then
    mkdir -p "$PREVIOUS"
    rsync -a --delete --exclude 'static/exports/*' "$TARGET" "$PREVIOUS"
fi

rsync -a --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude 'backups/' \
    --exclude 'cutting_web_data.db*' \
    --exclude 'static/exports/*' \
    "$SOURCE" "$TARGET"
chown -R root:cuttingapp "$TARGET"
find "$TARGET" -type d -exec chmod 0750 {} \;
find "$TARGET" -type f -exec chmod 0640 {} \;
chmod 0750 "$TARGET"/deploy/*.sh "$TARGET"/*.py
mkdir -p "$TARGET"/static/exports
chown cuttingapp:cuttingapp "$TARGET"/static/exports
chmod 0750 "$TARGET"/static/exports

if ! runuser -u cuttingapp -- /bin/sh -c \
    'set -a; . /etc/cutting-web-app.env; set +a; exec /usr/bin/python3 /opt/cutting-web-app/safe_upgrade.py'; then
    if [ -d "$PREVIOUS" ]; then
        rsync -a --delete --exclude 'static/exports/*' "$PREVIOUS" "$TARGET"
    fi
    exit 1
fi

install -m 0644 "$TARGET"/deploy/cutting-web-app.service /etc/systemd/system/cutting-web-app.service
install -m 0644 "$TARGET"/deploy/cutting-web-healthcheck.service /etc/systemd/system/cutting-web-healthcheck.service
install -m 0644 "$TARGET"/deploy/cutting-web-healthcheck.timer /etc/systemd/system/cutting-web-healthcheck.timer
systemctl daemon-reload
systemctl enable cutting-web-app.service cutting-web-healthcheck.timer >/dev/null
systemctl start cutting-web-app.service
systemctl start cutting-web-healthcheck.timer
systemctl is-active --quiet cutting-web-app.service
systemctl is-active --quiet cutting-web-healthcheck.timer
trap - EXIT
echo "PUBLISH_OK"
