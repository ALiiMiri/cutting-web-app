#!/bin/sh
set -eu

SERVICE=cutting-web-app.service
HEALTH_URL=${CUTTING_HEALTH_URL:-http://127.0.0.1:5000/healthz}
ATTEMPTS=${CUTTING_HEALTH_ATTEMPTS:-3}

# A stopped service during a guarded release is intentional. Restart-on-failure
# already handles crashes; this monitor is specifically for active-but-stuck
# processes.
if ! /usr/bin/systemctl is-active --quiet "$SERVICE"; then
    exit 0
fi

attempt=1
while [ "$attempt" -le "$ATTEMPTS" ]; do
    if /usr/bin/curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null; then
        exit 0
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -le "$ATTEMPTS" ]; then
        /usr/bin/sleep 2
    fi
done

/usr/bin/logger -t cutting-web-healthcheck \
    "health check failed after $ATTEMPTS attempts; restarting $SERVICE"
/usr/bin/systemctl restart "$SERVICE"

# Make the monitor fail visibly if the restarted service still cannot respond.
/usr/bin/sleep 3
/usr/bin/curl --fail --silent --show-error --max-time 10 "$HEALTH_URL" >/dev/null
