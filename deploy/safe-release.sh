#!/bin/sh
set -eu

systemctl stop cutting-web-app.service
if ! /usr/bin/python3 /opt/cutting-web-app/safe_upgrade.py; then
    systemctl start cutting-web-app.service
    exit 1
fi
systemctl start cutting-web-app.service
systemctl is-active --quiet cutting-web-app.service
echo "SAFE_RELEASE_OK"
