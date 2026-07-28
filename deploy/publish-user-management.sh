#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.user-management.previous.$(date +%Y%m%d%H%M%S)"

FILES='auth_utils.py
cutting_web_app.py
db_migrations.py
decorators.py
security_utils.py
migrations/021_user_management_security.py
routes/admin.py
routes/auth.py
routes/inventory.py
templates/admin/users.html
templates/change_password.html
templates/index.html
templates/inventory_dashboard.html
templates/inventory_waste.html
templates/login.html
templates/profile_inventory_details.html
templates/profile_types.html'

mkdir -p "$PREVIOUS"
for file in $FILES; do
    if [ -f "$TARGET/$file" ]; then
        mkdir -p "$PREVIOUS/$(dirname "$file")"
        cp -a "$TARGET/$file" "$PREVIOUS/$file"
    fi
done

systemctl stop cutting-web-app.service
restart_service() {
    systemctl start cutting-web-app.service >/dev/null 2>&1 || true
}
trap restart_service EXIT

for file in $FILES; do
    mkdir -p "$TARGET/$(dirname "$file")"
    cp "$SOURCE/$file" "$TARGET/$file"
    chown root:cuttingapp "$TARGET/$file"
    chmod 0640 "$TARGET/$file"
done

if ! runuser -u cuttingapp -- /bin/sh -c \
    'set -a; . /etc/cutting-web-app.env; set +a; exec /usr/bin/python3 /opt/cutting-web-app/safe_upgrade.py'; then
    for file in $FILES; do
        if [ -f "$PREVIOUS/$file" ]; then
            cp -a "$PREVIOUS/$file" "$TARGET/$file"
        fi
    done
    exit 1
fi

systemctl start cutting-web-app.service
systemctl is-active --quiet cutting-web-app.service
trap - EXIT
echo "USER_MANAGEMENT_PUBLISH_OK previous=$PREVIOUS"
