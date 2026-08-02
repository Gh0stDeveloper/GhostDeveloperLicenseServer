#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

KEYS_BASE="${GHOST_KEYS_BASE_URL:-https://ghostdeveloperkeys.duckdns.org}"
DOWNLOADS_BASE="${GHOST_DOWNLOADS_BASE_URL:-https://ghostdeveloperdownloads.duckdns.org}"
PUBLIC_BASE="${GHOST_PUBLIC_BASE_URL:-https://ghostdeveloper.duckdns.org}"
REPORT="${GHOST_SMOKE_REPORT:-/tmp/ghostdeveloper-live-smoke.txt}"
SSH_HOST="${GHOST_VPS_HOST:-}"
SSH_USER="${GHOST_VPS_USER:-}"
SSH_PORT="${GHOST_VPS_PORT:-22}"
SSH_KEY_FILE="${GHOST_VPS_SSH_KEY_FILE:-}"
SSH_KNOWN_HOSTS_FILE="${GHOST_VPS_KNOWN_HOSTS_FILE:-}"
LICENSE_ID=""

exec > >(tee "$REPORT") 2>&1

log() { printf '[live-smoke] %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
mask() {
  [[ -n "${1:-}" ]] || return 0
  [[ "${GITHUB_ACTIONS:-}" == true ]] && printf '::add-mask::%s\n' "$1"
}

remote() {
  ssh -p "$SSH_PORT" \
    -i "$SSH_KEY_FILE" \
    -o BatchMode=yes \
    -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$SSH_KNOWN_HOSTS_FILE" \
    "$SSH_USER@$SSH_HOST" "$@"
}

cleanup() {
  if [[ -n "$LICENSE_ID" && -n "$SSH_HOST" ]]; then
    remote "sudo -n ghostctl revoke-key '$LICENSE_ID' 'Limpieza automática de CI' >/dev/null" || true
  fi
}
trap cleanup EXIT

for command in curl jq openssl sha256sum ssh; do
  command -v "$command" >/dev/null 2>&1 || fail "falta $command"
done

log 'Comprobando endpoints públicos.'
curl -fsS --retry 2 --connect-timeout 8 --max-time 20 "$KEYS_BASE/health" \
  | jq -e '.status == "online" and .service == "ghostdeveloper-license-api"' >/dev/null
curl -fsS --retry 2 --connect-timeout 8 --max-time 20 "$DOWNLOADS_BASE/health" \
  | jq -e '.status == "online"' >/dev/null
INSTALLER="$(mktemp /tmp/ghost-installer.XXXXXX)"
PUBLIC_KEY="$(mktemp /tmp/ghost-public-key.XXXXXX)"
trap 'rm -f "${INSTALLER:-}" "${PUBLIC_KEY:-}"; cleanup' EXIT
curl -fsS --retry 2 --connect-timeout 8 --max-time 20 "$PUBLIC_BASE/install.sh" -o "$INSTALLER"
bash -n "$INSTALLER"
grep -Fq 'amd64|x86_64|arm64|aarch64' "$INSTALLER"
EXPECTED_PUBLIC_SHA="$(sed -nE 's/^PUBLIC_KEY_SHA256="?([0-9a-fA-F]{64})"?$/\1/p' "$INSTALLER" | head -n1 | tr 'A-F' 'a-f')"
[[ "$EXPECTED_PUBLIC_SHA" =~ ^[0-9a-f]{64}$ ]] || fail 'el bootstrap no contiene un SHA-256 público válido.'
curl -fsS --retry 2 "$KEYS_BASE/.well-known/hextunnel-license-public.pem" -o "$PUBLIC_KEY"
ACTUAL_PUBLIC_SHA="$(sha256sum "$PUBLIC_KEY" | awk '{print tolower($1)}')"
[[ "$ACTUAL_PUBLIC_SHA" == "$EXPECTED_PUBLIC_SHA" ]] || fail 'la clave pública desplegada no coincide con el bootstrap.'
openssl pkey -pubin -in "$PUBLIC_KEY" -noout >/dev/null

RUNNER_IP="$(curl -fsS --retry 2 --connect-timeout 8 --max-time 20 https://api.ipify.org)"
[[ "$RUNNER_IP" =~ ^[0-9a-fA-F:.]+$ ]] || fail 'no se pudo detectar la IP del runner.'

log 'Comprobando que una key inexistente sea rechazada.'
INVALID_NONCE="$(openssl rand -hex 24)"
INVALID_REQUEST="$(jq -n \
  --arg key 'HT-CI-INVALID-KEY-000000000000' \
  --arg ip "$RUNNER_IP" \
  --arg nonce "$INVALID_NONCE" \
  --argjson timestamp "$(date -u +%s)" \
  '{key:$key,ip:$ip,nonce:$nonce,timestamp:$timestamp,product:"hextunnel",action:"install"}')"
INVALID_BODY="$(mktemp /tmp/ghost-invalid.XXXXXX)"
INVALID_STATUS="$(curl -sS --connect-timeout 8 --max-time 25 \
  -H 'Content-Type: application/json' --data-binary "$INVALID_REQUEST" \
  -o "$INVALID_BODY" -w '%{http_code}' "$KEYS_BASE/api/v1/install/authorize")"
[[ "$INVALID_STATUS" == 403 ]] || fail "una key inexistente devolvió HTTP $INVALID_STATUS"
jq -e '.detail == "La key no existe"' "$INVALID_BODY" >/dev/null
rm -f "$INVALID_BODY"

if [[ -z "$SSH_HOST" || -z "$SSH_USER" || -z "$SSH_KEY_FILE" || -z "$SSH_KNOWN_HOSTS_FILE" ]]; then
  log 'Prueba pública correcta. No se configuraron secretos SSH; se omite el ciclo real de key.'
  exit 0
fi
[[ -s "$SSH_KEY_FILE" && -s "$SSH_KNOWN_HOSTS_FILE" ]] || fail 'los archivos SSH configurados no existen.'

log 'Generando una licencia real de corta duración mediante la API local.'
LICENSE_JSON="$(remote "sudo -n ghostctl create-key 15 999999999 ci-production-smoke")"
KEY="$(jq -r '.key // empty' <<< "$LICENSE_JSON")"
LICENSE_ID="$(jq -r '.id // empty' <<< "$LICENSE_JSON")"
[[ -n "$KEY" && "$LICENSE_ID" =~ ^[0-9a-f-]{36}$ ]] || fail 'no se obtuvo una licencia real válida.'
mask "$KEY"
mask "$LICENSE_ID"

log 'Autorizando instalación real desde el runner.'
NONCE="$(openssl rand -hex 24)"
REQUEST="$(jq -n \
  --arg key "$KEY" \
  --arg ip "$RUNNER_IP" \
  --arg nonce "$NONCE" \
  --argjson timestamp "$(date -u +%s)" \
  '{key:$key,ip:$ip,nonce:$nonce,timestamp:$timestamp,product:"hextunnel",action:"install"}')"
AUTH="$(curl -fsS --retry 2 --connect-timeout 8 --max-time 30 \
  -H 'Content-Type: application/json' --data-binary "$REQUEST" \
  "$KEYS_BASE/api/v1/install/authorize")"
jq -e --arg nonce "$NONCE" --arg ip "$RUNNER_IP" \
  '.status == "valid" and .nonce == $nonce and .subject == $ip and (.version|length)>0' \
  <<< "$AUTH" >/dev/null

DOWNLOAD_URL="$(jq -r '.download_url' <<< "$AUTH")"
PACKAGE_SHA="$(jq -r '.package_sha256' <<< "$AUTH" | tr 'A-F' 'a-f')"
ACTIVATION_TOKEN="$(jq -r '.activation_token' <<< "$AUTH")"
SIGNATURE="$(jq -r '.signature' <<< "$AUTH")"
VERSION="$(jq -r '.version' <<< "$AUTH")"
mask "$DOWNLOAD_URL"
mask "$ACTIVATION_TOKEN"
mask "$SIGNATURE"

PAYLOAD_FILE="$(mktemp /tmp/ghost-auth-payload.XXXXXX)"
SIGNATURE_FILE="$(mktemp /tmp/ghost-auth-signature.XXXXXX)"
printf 'status=%s\nexpires_at=%s\ndownload_expires_at=%s\nnonce=%s\nsubject=%s\nversion=%s\ndownload_url=%s\npackage_sha256=%s\nentrypoint=%s\n' \
  "$(jq -r '.status' <<< "$AUTH")" \
  "$(jq -r '.expires_at' <<< "$AUTH")" \
  "$(jq -r '.download_expires_at' <<< "$AUTH")" \
  "$(jq -r '.nonce' <<< "$AUTH")" \
  "$(jq -r '.subject' <<< "$AUTH")" \
  "$VERSION" \
  "$DOWNLOAD_URL" \
  "$PACKAGE_SHA" \
  "$(jq -r '.entrypoint' <<< "$AUTH")" > "$PAYLOAD_FILE"
printf '%s' "$SIGNATURE" | base64 -d > "$SIGNATURE_FILE"
openssl dgst -sha256 -verify "$PUBLIC_KEY" -signature "$SIGNATURE_FILE" "$PAYLOAD_FILE" >/dev/null

log "Descargando y verificando el paquete real $VERSION."
PACKAGE="$(mktemp /tmp/hextunnel-live.XXXXXX.tar.gz)"
curl -fsSL --retry 2 --connect-timeout 8 --max-time 300 "$DOWNLOAD_URL" -o "$PACKAGE"
[[ "$(sha256sum "$PACKAGE" | awk '{print tolower($1)}')" == "$PACKAGE_SHA" ]] \
  || fail 'el paquete descargado no coincide con el SHA-256 autorizado.'
tar -tzf "$PACKAGE" | grep -Eq '(^|/)bin/hextunnel-private-install$'
REUSE_STATUS="$(curl -sS --connect-timeout 8 --max-time 20 -o /dev/null -w '%{http_code}' "$DOWNLOAD_URL")"
[[ "$REUSE_STATUS" == 404 ]] || fail "el enlace de un solo uso pudo reutilizarse: HTTP $REUSE_STATUS"

log 'Renovando y verificando el lease firmado.'
LEASE_REQUEST="$(jq -n --arg token "$ACTIVATION_TOKEN" --arg ip "$RUNNER_IP" \
  '{activation_token:$token,ip:$ip,product:"hextunnel"}')"
LEASE="$(curl -fsS --retry 2 --connect-timeout 8 --max-time 30 \
  -H 'Content-Type: application/json' --data-binary "$LEASE_REQUEST" \
  "$KEYS_BASE/api/v1/licenses/lease")"
jq -e --arg ip "$RUNNER_IP" '.status == "active" and .subject == $ip and .product == "hextunnel"' \
  <<< "$LEASE" >/dev/null
LEASE_PAYLOAD="$(mktemp /tmp/ghost-lease-payload.XXXXXX)"
LEASE_SIGNATURE="$(mktemp /tmp/ghost-lease-signature.XXXXXX)"
printf 'status=%s\nlease_expires_at=%s\nsubject=%s\nproduct=%s\nactivation_id=%s\n' \
  "$(jq -r '.status' <<< "$LEASE")" \
  "$(jq -r '.lease_expires_at' <<< "$LEASE")" \
  "$(jq -r '.subject' <<< "$LEASE")" \
  "$(jq -r '.product' <<< "$LEASE")" \
  "$(jq -r '.activation_id' <<< "$LEASE")" > "$LEASE_PAYLOAD"
printf '%s' "$(jq -r '.signature' <<< "$LEASE")" | base64 -d > "$LEASE_SIGNATURE"
openssl dgst -sha256 -verify "$PUBLIC_KEY" -signature "$LEASE_SIGNATURE" "$LEASE_PAYLOAD" >/dev/null

log 'Comprobando autorización de upgrade sin una activación adicional.'
UPGRADE_NONCE="$(openssl rand -hex 24)"
UPGRADE_REQUEST="$(jq -n \
  --arg key "$KEY" --arg ip "$RUNNER_IP" --arg nonce "$UPGRADE_NONCE" \
  --argjson timestamp "$(date -u +%s)" \
  '{key:$key,ip:$ip,nonce:$nonce,timestamp:$timestamp,product:"hextunnel",action:"upgrade"}')"
UPGRADE="$(curl -fsS --retry 2 --connect-timeout 8 --max-time 30 \
  -H 'Content-Type: application/json' --data-binary "$UPGRADE_REQUEST" \
  "$KEYS_BASE/api/v1/install/authorize")"
jq -e --arg version "$VERSION" '.status == "valid" and .version == $version' <<< "$UPGRADE" >/dev/null
REMOTE_COUNT="$(remote "sudo -n ghostctl license '$LICENSE_ID'" | jq -r '.activation_count')"
[[ "$REMOTE_COUNT" == 1 ]] || fail "upgrade alteró activation_count: $REMOTE_COUNT"

rm -f "$PAYLOAD_FILE" "$SIGNATURE_FILE" "$PACKAGE" "$LEASE_PAYLOAD" "$LEASE_SIGNATURE"
log "Prueba integral real correcta: versión=$VERSION, activaciones=$REMOTE_COUNT."
