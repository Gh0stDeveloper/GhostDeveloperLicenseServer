#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

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
API_BASE="${GHOST_LICENSE_ADMIN_API_BASE:-http://127.0.0.1:8080}"

[[ -f "$SOURCE_FILE" ]] || { echo "ERROR: paquete inexistente: $SOURCE_FILE" >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo 'ERROR: versión inválida.' >&2; exit 1; }
[[ -s "$ADMIN_TOKEN_FILE" ]] || { echo "ERROR: falta $ADMIN_TOKEN_FILE" >&2; exit 1; }

DEST_NAME="${PRODUCT}-${VERSION}.tar.gz"
DEST_FILE="$RELEASE_ROOT/$DEST_NAME"
SOURCE_SHA="$(sha256sum "$SOURCE_FILE" | awk '{print tolower($1)}')"
TOKEN="$(tr -d '\r\n' < "$ADMIN_TOKEN_FILE")"
CURL_CONFIG="$(mktemp /tmp/ghost-release-curl.XXXXXX)"
trap 'rm -f "${CURL_CONFIG:-}"' EXIT
printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" > "$CURL_CONFIG"
chmod 600 "$CURL_CONFIG"

api_get() {
  curl -fsS --connect-timeout 3 --max-time 30 --config "$CURL_CONFIG" "$API_BASE$1"
}

api_post() {
  local path="$1" payload="$2"
  curl -fsS --connect-timeout 3 --max-time 60 --config "$CURL_CONFIG" \
    -H 'Content-Type: application/json' --data-binary "$payload" "$API_BASE$path"
}

RELEASES="$(api_get "/api/v1/admin/releases?product=$PRODUCT")"
EXISTING="$(jq -c --arg version "$VERSION" '.[] | select(.version == $version)' <<< "$RELEASES" | head -n1)"

if [[ -n "$EXISTING" ]]; then
  EXISTING_ID="$(jq -r '.id' <<< "$EXISTING")"
  EXISTING_SHA="$(jq -r '.sha256' <<< "$EXISTING")"
  EXISTING_ENTRYPOINT="$(jq -r '.entrypoint' <<< "$EXISTING")"
  [[ "$EXISTING_SHA" == "$SOURCE_SHA" ]] || {
    echo "ERROR: la versión $VERSION ya existe con otro SHA-256." >&2
    exit 1
  }
  [[ "$EXISTING_ENTRYPOINT" == "$ENTRYPOINT" ]] || {
    echo "ERROR: la versión $VERSION ya existe con otro entrypoint." >&2
    exit 1
  }
  install -o ghostlicense -g ghostlicense -m 0600 "$SOURCE_FILE" "$DEST_FILE"
  PAYLOAD="$(jq -n --arg reason 'Publicación idempotente mediante register-release.sh' '{reason:$reason}')"
  api_post "/api/v1/admin/releases/$EXISTING_ID/activate" "$PAYLOAD"
  printf '\n' >&2
  exit 0
fi

if [[ -e "$DEST_FILE" ]]; then
  DEST_SHA="$(sha256sum "$DEST_FILE" | awk '{print tolower($1)}')"
  [[ "$DEST_SHA" == "$SOURCE_SHA" ]] || {
    echo "ERROR: $DEST_FILE ya existe con contenido diferente." >&2
    exit 1
  }
else
  install -o ghostlicense -g ghostlicense -m 0600 "$SOURCE_FILE" "$DEST_FILE"
fi

PAYLOAD="$(jq -n \
  --arg product "$PRODUCT" \
  --arg version "$VERSION" \
  --arg relative_path "$DEST_NAME" \
  --arg entrypoint "$ENTRYPOINT" \
  '{product:$product,version:$version,relative_path:$relative_path,entrypoint:$entrypoint,activate:true}')"
api_post '/api/v1/admin/releases' "$PAYLOAD"
printf '\n' >&2
