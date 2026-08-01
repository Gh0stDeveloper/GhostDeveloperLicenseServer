#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: ejecuta este script como root." >&2; exit 1; }

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTALL_ROOT=/opt/ghostdeveloper-license-server
APP_DIR="$INSTALL_ROOT/current"
VENV_DIR="$INSTALL_ROOT/venv"
STATE_DIR=/var/lib/ghostdeveloper-license
RELEASE_DIR="$STATE_DIR/releases"
BACKUP_DIR=/var/backups/ghostdeveloper-license
CONFIG_DIR=/etc/ghostdeveloper-license
SECRET_DIR="$CONFIG_DIR/secrets"
ENV_FILE="$CONFIG_DIR/license-api.env"
PUBLIC_DIR=/var/www/ghostdeveloper/.well-known
SERVICE_USER=ghostlicense
SERVICE_GROUP=ghostlicense

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip ca-certificates curl jq openssl rsync sqlite3

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -m 0755 "$INSTALL_ROOT"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STATE_DIR" "$RELEASE_DIR"
install -d -o root -g root -m 0700 "$BACKUP_DIR"
install -d -o root -g "$SERVICE_GROUP" -m 0750 "$CONFIG_DIR" "$SECRET_DIR"
install -d -o root -g root -m 0755 "$PUBLIC_DIR"

rm -rf "$APP_DIR.new"
install -d -m 0755 "$APP_DIR.new"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.db*' \
  "$SOURCE_DIR/" "$APP_DIR.new/"
rm -rf "$APP_DIR.previous"
if [[ -d "$APP_DIR" ]]; then
  mv "$APP_DIR" "$APP_DIR.previous"
fi
mv "$APP_DIR.new" "$APP_DIR"
chown -R root:root "$APP_DIR"
chmod 0755 "$APP_DIR/scripts/"*.sh

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

umask 077
if [[ ! -s "$SECRET_DIR/admin-token" ]]; then
  openssl rand -hex 32 > "$SECRET_DIR/admin-token"
fi
if [[ ! -s "$SECRET_DIR/key-hmac-secret" ]]; then
  openssl rand -hex 32 > "$SECRET_DIR/key-hmac-secret"
fi
if [[ ! -s "$SECRET_DIR/license-private.pem" ]]; then
  openssl genpkey -algorithm RSA \
    -pkeyopt rsa_keygen_bits:3072 \
    -out "$SECRET_DIR/license-private.pem"
fi
openssl pkey \
  -in "$SECRET_DIR/license-private.pem" \
  -pubout \
  -out "$PUBLIC_DIR/hextunnel-license-public.pem"

chown root:"$SERVICE_GROUP" \
  "$SECRET_DIR/admin-token" \
  "$SECRET_DIR/key-hmac-secret" \
  "$SECRET_DIR/license-private.pem"
chmod 0640 \
  "$SECRET_DIR/admin-token" \
  "$SECRET_DIR/key-hmac-secret" \
  "$SECRET_DIR/license-private.pem"
chown root:root "$PUBLIC_DIR/hextunnel-license-public.pem"
chmod 0644 "$PUBLIC_DIR/hextunnel-license-public.pem"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'ENVEOF'
GHOST_LICENSE_ENVIRONMENT=production
GHOST_LICENSE_DATABASE_URL=sqlite:////var/lib/ghostdeveloper-license/license.db
GHOST_LICENSE_ADMIN_TOKEN_FILE=/etc/ghostdeveloper-license/secrets/admin-token
GHOST_LICENSE_HMAC_SECRET_FILE=/etc/ghostdeveloper-license/secrets/key-hmac-secret
GHOST_LICENSE_PRIVATE_KEY_FILE=/etc/ghostdeveloper-license/secrets/license-private.pem
GHOST_LICENSE_PUBLIC_KEY_FILE=/var/www/ghostdeveloper/.well-known/hextunnel-license-public.pem
GHOST_LICENSE_RELEASE_ROOT=/var/lib/ghostdeveloper-license/releases
GHOST_LICENSE_DOWNLOAD_BASE_URL=https://ghostdeveloperdownloads.duckdns.org
GHOST_LICENSE_PUBLIC_INSTALL_URL=https://ghostdeveloper.duckdns.org/install.sh
GHOST_LICENSE_MAX_CLOCK_SKEW_SECONDS=300
GHOST_LICENSE_NONCE_TTL_SECONDS=600
GHOST_LICENSE_DOWNLOAD_TTL_SECONDS=300
GHOST_LICENSE_LEASE_TTL_SECONDS=86400
GHOST_LICENSE_ENFORCE_SOURCE_IP=1
GHOST_LICENSE_DOCS_ENABLED=0
ENVEOF
fi
chown root:"$SERVICE_GROUP" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

install -m 0644 "$APP_DIR/systemd/ghost-license-api.service" /etc/systemd/system/ghost-license-api.service
install -m 0644 "$APP_DIR/systemd/ghost-license-backup.service" /etc/systemd/system/ghost-license-backup.service
install -m 0644 "$APP_DIR/systemd/ghost-license-backup.timer" /etc/systemd/system/ghost-license-backup.timer

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
(
  cd "$APP_DIR"
  runuser -u "$SERVICE_USER" --preserve-environment -- "$VENV_DIR/bin/python" -m app.cli init-db
)

systemctl daemon-reload
systemctl enable --now ghost-license-api.service
systemctl enable --now ghost-license-backup.timer
systemctl --no-pager --full status ghost-license-api.service || true

cat <<EOF2

Instalación completada.
API interna: http://127.0.0.1:8080/health
Token administrativo: $SECRET_DIR/admin-token
Clave pública: $PUBLIC_DIR/hextunnel-license-public.pem

Siguiente paso: integrar los bloques de nginx incluidos en nginx/README.md.
EOF2
