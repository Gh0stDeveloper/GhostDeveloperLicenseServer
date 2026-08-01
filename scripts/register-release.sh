#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Uso: sudo $0 <paquete.tar.gz> <version> [producto] [entrypoint]" >&2
  exit 2
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: se requiere root." >&2; exit 1; }
[[ $# -ge 2 ]] || usage

SOURCE_FILE="$(readlink -f "$1")"
VERSION="$2"
PRODUCT="${3:-hextunnel}"
ENTRYPOINT="${4:-bin/hextunnel-private-install}"
RELEASE_ROOT=/var/lib/ghostdeveloper-license/releases
ADMIN_TOKEN_FILE=/etc/ghostdeveloper-license/secrets/admin-token

[[ -f "$SOURCE_FILE" ]] || { echo "ERROR: paquete inexistente: $SOURCE_FILE" >&2; exit 1; }
DEST_NAME="${PRODUCT}-${VERSION}.tar.gz"
install -o ghostlicense -g ghostlicense -m 0600 "$SOURCE_FILE" "$RELEASE_ROOT/$DEST_NAME"
TOKEN="$(tr -d '\r\n' < "$ADMIN_TOKEN_FILE")"

jq -n \
  --arg product "$PRODUCT" \
  --arg version "$VERSION" \
  --arg relative_path "$DEST_NAME" \
  --arg entrypoint "$ENTRYPOINT" \
  '{product:$product,version:$version,relative_path:$relative_path,entrypoint:$entrypoint,activate:true}' \
| curl -fsS \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    http://127.0.0.1:8080/api/v1/admin/releases
printf '\n'
