#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: ejecuta este script como root." >&2; exit 1; }

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTALL_ROOT=/opt/ghostdeveloper-license-server
APP_RELEASES="$INSTALL_ROOT/releases"
CURRENT_LINK="$INSTALL_ROOT/current"
PREVIOUS_LINK="$INSTALL_ROOT/previous"
STATE_DIR=/var/lib/ghostdeveloper-license
PACKAGE_RELEASE_DIR="$STATE_DIR/releases"
BACKUP_DIR=/var/backups/ghostdeveloper-license
CONFIG_DIR=/etc/ghostdeveloper-license
SECRET_DIR="$CONFIG_DIR/secrets"
ENV_FILE="$CONFIG_DIR/license-api.env"
WEB_ROOT=/var/www/ghostdeveloper
PUBLIC_DIR="$WEB_ROOT/.well-known"
SERVICE_USER=ghostlicense
SERVICE_GROUP=ghostlicense
KEEP_APP_RELEASES="${GHOST_LICENSE_KEEP_APP_RELEASES:-5}"

log() { printf '[license-server] %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

wait_for_health() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:8080/health \
      | jq -e '.status == "online"' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

atomic_link() {
  local target="$1" link="$2" next="${link}.next"
  rm -f "$next"
  ln -s "$target" "$next"
  mv -Tf "$next" "$link"
}

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip ca-certificates curl jq openssl rsync sqlite3 git

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -m 0755 "$INSTALL_ROOT" "$APP_RELEASES"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STATE_DIR" "$PACKAGE_RELEASE_DIR"
install -d -o root -g root -m 0700 "$BACKUP_DIR"
install -d -o root -g "$SERVICE_GROUP" -m 0750 "$CONFIG_DIR" "$SECRET_DIR"
install -d -o root -g root -m 0755 "$WEB_ROOT" "$PUBLIC_DIR"

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

APP_VERSION="$(python3 - <<'PY' "$SOURCE_DIR/app/__init__.py"
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
print(match.group(1) if match else "unknown")
PY
)"
RELEASE_ID="${APP_VERSION}-$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 4)"
APP_DIR="$APP_RELEASES/$RELEASE_ID"
PREVIOUS_TARGET=""

if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_TARGET="$(readlink -f "$CURRENT_LINK" || true)"
elif [[ -d "$CURRENT_LINK" ]]; then
  PREVIOUS_TARGET="$APP_RELEASES/legacy-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$CURRENT_LINK" "$PREVIOUS_TARGET"
fi

log "Preparando release de aplicación $RELEASE_ID"
install -d -m 0755 "$APP_DIR"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.db*' \
  "$SOURCE_DIR/" "$APP_DIR/"
chown -R root:root "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 0755 {} +
chmod 0755 "$APP_DIR/scripts/"*.sh "$APP_DIR/public/install.sh"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" -m compileall -q "$APP_DIR/app"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -s "$STATE_DIR/license.db" ]]; then
  sqlite3 "$STATE_DIR/license.db" ".backup '$BACKUP_DIR/predeploy-$RELEASE_ID.db'"
  chmod 0600 "$BACKUP_DIR/predeploy-$RELEASE_ID.db"
fi
(
  cd "$APP_DIR"
  runuser -u "$SERVICE_USER" --preserve-environment -- "$APP_DIR/.venv/bin/python" -m app.cli init-db
)

install -m 0644 "$APP_DIR/systemd/ghost-license-api.service" /etc/systemd/system/ghost-license-api.service
install -m 0644 "$APP_DIR/systemd/ghost-license-backup.service" /etc/systemd/system/ghost-license-backup.service
install -m 0644 "$APP_DIR/systemd/ghost-license-backup.timer" /etc/systemd/system/ghost-license-backup.timer

atomic_link "$APP_DIR" "$CURRENT_LINK"
systemctl daemon-reload
systemctl enable ghost-license-api.service ghost-license-backup.timer >/dev/null

if ! systemctl restart ghost-license-api.service || ! wait_for_health; then
  log "La nueva API no superó el health check; restaurando la release anterior."
  if [[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" ]]; then
    atomic_link "$PREVIOUS_TARGET" "$CURRENT_LINK"
    systemctl daemon-reload
    systemctl restart ghost-license-api.service || true
    wait_for_health || true
  fi
  systemctl --no-pager --full status ghost-license-api.service || true
  journalctl -u ghost-license-api.service -n 100 --no-pager || true
  fail "Despliegue revertido por fallo de salud."
fi

systemctl enable --now ghost-license-backup.timer >/dev/null
if [[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" ]]; then
  atomic_link "$PREVIOUS_TARGET" "$PREVIOUS_LINK"
fi

PUBLIC_KEY_SHA256="$(sha256sum "$PUBLIC_DIR/hextunnel-license-public.pem" | awk '{print $1}')"
INSTALLER_TMP="$(mktemp /tmp/ghostdeveloper-install.XXXXXX)"
sed -E \
  "s#^PUBLIC_KEY_SHA256=.*#PUBLIC_KEY_SHA256=\"$PUBLIC_KEY_SHA256\"#" \
  "$APP_DIR/public/install.sh" > "$INSTALLER_TMP"
bash -n "$INSTALLER_TMP"
install -o root -g root -m 0644 "$APP_DIR/public/index.html" "$WEB_ROOT/index.html"
install -o root -g root -m 0755 "$INSTALLER_TMP" "$WEB_ROOT/install.sh"
rm -f "$INSTALLER_TMP"

install -o root -g root -m 0755 "$APP_DIR/scripts/ghostctl.sh" /usr/local/sbin/ghostctl

mapfile -t old_releases < <(
  find "$APP_RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -nr \
    | awk -v keep="$KEEP_APP_RELEASES" 'NR > keep {sub(/^[^ ]+ /, ""); print}'
)
for old in "${old_releases[@]}"; do
  [[ "$old" == "$APP_DIR" || "$old" == "$PREVIOUS_TARGET" ]] && continue
  rm -rf -- "$old"
done

log "Despliegue correcto: $APP_VERSION"
curl -fsS http://127.0.0.1:8080/health | jq .
cat <<EOF2

Actualización completada y validada.
Release activa: $APP_DIR
Release anterior: ${PREVIOUS_TARGET:-ninguna}
API interna: http://127.0.0.1:8080/health
Página pública: https://ghostdeveloper.duckdns.org/
Instalador público: https://ghostdeveloper.duckdns.org/install.sh
Control operativo: sudo ghostctl
EOF2
