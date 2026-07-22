#!/bin/sh
set -eu

SOURCE=/root/cutting-web-app
TARGET=/opt/cutting-web-app
PREVIOUS="/opt/cutting-web-app.project-ownership.previous.$(date +%Y%m%d%H%M%S)"

FILES='cutting_web_app.py
database.py
db_migrations.py
security_utils.py
migrations/022_project_ownership.py
templates/index.html
templates/project_assignment_history.html
templates/project_treeview.html
templates/project_details.html
templates/cutting_result.html'

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
echo "PROJECT_OWNERSHIP_PUBLISH_OK previous=$PREVIOUS"
