#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PRODUCT="hextunnel"
AUTH_ENDPOINT="https://ghostdeveloperkeys.duckdns.org/api/v1/install/authorize"
PUBLIC_KEY_URL="https://ghostdeveloperkeys.duckdns.org/.well-known/hextunnel-license-public.pem"
PUBLIC_KEY_SHA256="804f9b029d39dd9c9ba4246bcecf3cd9963a5555491f7da8dfc3cc6d24f6ec3e"
STATE_DIR="/etc/hextunnel"
KEY_FILE="$STATE_DIR/license.key"
TOKEN_FILE="$STATE_DIR/activation.token"
STATE_FILE="$STATE_DIR/license-state.env"
PUBLIC_KEY_FILE="$STATE_DIR/license-public.pem"
LOCK_FILE="/run/lock/hextunnel-bootstrap.lock"

fail(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_root(){ [[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "Ejecuta el instalador mediante sudo."; }

install_dependencies(){
  local command missing=0
  for command in curl jq openssl tar sha256sum date flock; do
    command -v "$command" >/dev/null 2>&1 || missing=1
  done
  ((missing == 0)) && return 0
  command -v apt-get >/dev/null 2>&1 || fail "Faltan dependencias y apt-get no está disponible."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    curl jq openssl ca-certificates tar coreutils util-linux
}

validate_platform(){
  local architecture
  architecture="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  case "$architecture" in
    amd64|x86_64|arm64|aarch64) ;;
    *) fail "Hex Tunnel requiere una VPS dedicada amd64/x86_64 o arm64/aarch64. Detectado: $architecture" ;;
  esac
  [[ -r /etc/os-release ]] || fail "No se pudo identificar el sistema operativo."
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}:${VERSION_ID:-}" in
    debian:12|ubuntu:22.04|ubuntu:24.04) ;;
    *) fail "Usa Debian 12 o Ubuntu 22.04/24.04 en una VPS dedicada." ;;
  esac
}

read_key(){
  local key="${HEXTUNNEL_LICENSE_KEY:-}"
  if [[ -z "$key" && -r "$KEY_FILE" ]]; then
    key="$(tr -d '\r\n' < "$KEY_FILE")"
  fi
  if [[ -z "$key" && -t 0 ]]; then
    read -r -s -p "KEY: " key
    printf '\n'
  fi
  [[ -n "$key" ]] || fail "No se proporcionó una key."
  printf '%s' "$key"
}

future_time(){
  local value="$1" label="$2" epoch
  epoch="$(date -d "$value" +%s 2>/dev/null)" || fail "$label contiene una fecha inválida."
  ((epoch > $(date -u +%s))) || fail "$label expiró."
}

canonical(){
  printf 'status=%s\nexpires_at=%s\ndownload_expires_at=%s\nnonce=%s\nsubject=%s\nversion=%s\ndownload_url=%s\npackage_sha256=%s\nentrypoint=%s\n' "$@"
}

validate_archive(){
  local archive="$1" duplicates
  if tar -tzf "$archive" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    fail "El paquete contiene rutas inseguras."
  fi
  if tar -tvzf "$archive" | awk 'substr($1,1,1) ~ /[lhbcp]/ {found=1} END {exit !found}'; then
    fail "El paquete contiene enlaces o dispositivos no permitidos."
  fi
  duplicates="$(tar -tzf "$archive" | sed -E 's#^\./##; s#/$##' | sort | uniq -d | head -n1)"
  [[ -z "$duplicates" ]] || fail "El paquete contiene una ruta duplicada: $duplicates"
}

persist_authorization_state(){
  local key="$1" activation_token="$2" expires_at="$3" lease_expires_at="$4"
  local subject="$5" version="$6" action="$7" public_key="$8" work
  install -d -m 700 "$STATE_DIR"
  work="$(mktemp -d "$STATE_DIR/.authorization.XXXXXX")"
  printf '%s\n' "$key" > "$work/license.key"
  printf '%s\n' "$activation_token" > "$work/activation.token"
  cat > "$work/license-state.env" <<EOF
HEXTUNNEL_LICENSE_EXPIRES_AT=$(printf '%q' "$expires_at")
HEXTUNNEL_LEASE_EXPIRES_AT=$(printf '%q' "$lease_expires_at")
HEXTUNNEL_LICENSE_SUBJECT=$(printf '%q' "$subject")
HEXTUNNEL_INSTALLED_VERSION=$(printf '%q' "$version")
HEXTUNNEL_LAST_OPERATION=$(printf '%q' "$action")
HEXTUNNEL_UPDATED_AT=$(printf '%q' "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
EOF
  install -m 600 "$public_key" "$work/license-public.pem"
  chmod 600 "$work/license.key" "$work/activation.token" "$work/license-state.env"
  mv -f "$work/license.key" "$KEY_FILE"
  mv -f "$work/activation.token" "$TOKEN_FILE"
  mv -f "$work/license-state.env" "$STATE_FILE"
  mv -f "$work/license-public.pem" "$PUBLIC_KEY_FILE"
  rmdir "$work"
}

main(){
  local action="${1:-install}" key ip nonce timestamp response tmp result
  local request_file auth_body http_status api_detail
  local status expires_at download_expires_at response_nonce subject version
  local download_url package_sha256 entrypoint signature activation_token lease_expires_at
  local public_key payload signature_file archive extract_root entrypoint_file package_root
  local -a matches=()

  case "$action" in
    install|upgrade) ;;
    status)
      [[ -x /usr/local/bin/hextunnel-license ]] || fail "Hex Tunnel no está instalado."
      exec /usr/local/bin/hextunnel-license status
      ;;
    *) fail "Uso: install.sh [install|upgrade|status]" ;;
  esac

  require_root
  install_dependencies
  install -d -m 755 "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Ya existe otra instalación o actualización de Hex Tunnel en curso."
  validate_platform

  tmp="$(mktemp -d /tmp/hextunnel-public.XXXXXX)"
  trap 'rm -rf "${tmp:-}"' EXIT
  chmod 700 "$tmp"
  request_file="$tmp/authorization-request.json"
  auth_body="$tmp/authorization-response.json"
  public_key="$tmp/public.pem"
  payload="$tmp/authorization.payload"
  signature_file="$tmp/authorization.sig"
  archive="$tmp/package.tar.gz"
  extract_root="$tmp/extracted"
  mkdir -p "$extract_root"

  key="$(read_key)"
  unset HEXTUNNEL_LICENSE_KEY
  ip="$(curl -4fsS --retry 2 --connect-timeout 8 --max-time 15 https://api.ipify.org)" \
    || fail "No se pudo detectar la IP pública."
  nonce="$(openssl rand -hex 24)"
  timestamp="$(date -u +%s)"
  jq -n \
    --arg key "$key" \
    --arg ip "$ip" \
    --arg nonce "$nonce" \
    --arg action "$action" \
    --argjson timestamp "$timestamp" \
    '{key:$key,ip:$ip,nonce:$nonce,timestamp:$timestamp,product:"hextunnel",action:$action}' \
    > "$request_file"
  : > "$auth_body"
  chmod 600 "$request_file" "$auth_body"

  printf 'Verificando licencia para %s...\n' "$action"
  if ! http_status="$(curl -sS --retry 2 --connect-timeout 8 --max-time 25 \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    -H 'Cache-Control: no-store' \
    --data-binary "@$request_file" \
    -o "$auth_body" \
    -w '%{http_code}' \
    "$AUTH_ENDPOINT")"; then
    fail "No se pudo contactar la API de licencias."
  fi
  response="$(cat "$auth_body")"

  if [[ ! "$http_status" =~ ^2[0-9]{2}$ ]]; then
    api_detail="$(jq -r '.detail // empty' <<< "$response" 2>/dev/null || true)"
    [[ -n "$api_detail" ]] || api_detail="respuesta HTTP sin detalle"
    fail "La API rechazó la solicitud: ${api_detail} (HTTP ${http_status})."
  fi

  jq empty <<< "$response" >/dev/null 2>&1 || fail "La API devolvió JSON inválido."
  status="$(jq -r '.status // empty' <<< "$response")"
  [[ "$status" == valid ]] || fail "La licencia no es válida."
  expires_at="$(jq -r '.expires_at // empty' <<< "$response")"
  download_expires_at="$(jq -r '.download_expires_at // empty' <<< "$response")"
  response_nonce="$(jq -r '.nonce // empty' <<< "$response")"
  subject="$(jq -r '.subject // empty' <<< "$response")"
  version="$(jq -r '.version // empty' <<< "$response")"
  download_url="$(jq -r '.download_url // empty' <<< "$response")"
  package_sha256="$(jq -r '.package_sha256 // empty' <<< "$response")"
  entrypoint="$(jq -r '.entrypoint // empty' <<< "$response")"
  signature="$(jq -r '.signature // empty' <<< "$response")"
  activation_token="$(jq -r '.activation_token // empty' <<< "$response")"
  lease_expires_at="$(jq -r '.lease_expires_at // empty' <<< "$response")"

  [[ "$response_nonce" == "$nonce" ]] || fail "Nonce de autorización incorrecto."
  [[ "$subject" == "$ip" ]] || fail "La licencia fue autorizada para otra IP."
  [[ -n "$version" ]] || fail "La autorización no incluye versión."
  [[ "$download_url" == https://* ]] || fail "La descarga privada no usa HTTPS."
  [[ "$package_sha256" =~ ^[0-9a-fA-F]{64}$ ]] || fail "SHA-256 inválido."
  [[ "$entrypoint" =~ ^[A-Za-z0-9._/-]+$ && "$entrypoint" != /* && "$entrypoint" != *".."* ]] \
    || fail "Entrypoint inseguro."
  [[ -n "$signature" && -n "$activation_token" ]] || fail "Autorización incompleta."
  future_time "$expires_at" "La licencia"
  future_time "$download_expires_at" "El enlace"
  future_time "$lease_expires_at" "El lease"

  curl -fsSL --retry 2 --connect-timeout 8 --max-time 20 \
    "$PUBLIC_KEY_URL" -o "$public_key" || fail "No se pudo descargar la clave pública."
  printf '%s  %s\n' "$PUBLIC_KEY_SHA256" "$public_key" | sha256sum -c - >/dev/null \
    || fail "La clave pública no coincide con el hash fijado."
  openssl pkey -pubin -in "$public_key" -noout >/dev/null 2>&1 || fail "Clave pública inválida."
  canonical \
    "$status" "$expires_at" "$download_expires_at" "$response_nonce" "$subject" \
    "$version" "$download_url" "${package_sha256,,}" "$entrypoint" > "$payload"
  printf '%s' "$signature" | base64 -d > "$signature_file" 2>/dev/null \
    || fail "Firma Base64 inválida."
  openssl dgst -sha256 -verify "$public_key" -signature "$signature_file" "$payload" >/dev/null \
    || fail "Firma RSA inválida."

  printf 'Descargando Hex Tunnel %s...\n' "$version"
  curl -fsSL --retry 3 --connect-timeout 10 --max-time 300 \
    "$download_url" -o "$archive" || fail "No se pudo descargar el paquete privado autorizado."
  printf '%s  %s\n' "${package_sha256,,}" "$archive" | sha256sum -c - >/dev/null \
    || fail "El paquete no coincide con el SHA-256 autorizado."
  validate_archive "$archive"
  tar -xzf "$archive" -C "$extract_root"

  if [[ -f "$extract_root/$entrypoint" ]]; then
    entrypoint_file="$extract_root/$entrypoint"
    package_root="$extract_root"
  else
    mapfile -t matches < <(find "$extract_root" -type f -path "*/$entrypoint" -print)
    ((${#matches[@]} == 1)) || fail "No existe un entrypoint único."
    entrypoint_file="${matches[0]}"
    package_root="${entrypoint_file%/$entrypoint}"
  fi
  chmod 700 "$entrypoint_file"

  persist_authorization_state \
    "$key" "$activation_token" "$expires_at" "$lease_expires_at" \
    "$subject" "$version" "$action" "$public_key"
  unset key activation_token signature response

  export HEXTUNNEL_LICENSE_PREVALIDATED=1
  export HEXTUNNEL_LICENSE_EXPIRES_AT="$expires_at"
  export HEXTUNNEL_LICENSE_SUBJECT="$subject"
  export HEXTUNNEL_PRIVATE_PACKAGE_ROOT="$package_root"
  export HEXTUNNEL_TARGET_VERSION="$version"
  export HEXTUNNEL_OPERATION="$action"
  export HEXTUNNEL_NO_REBOOT="${HEXTUNNEL_NO_REBOOT:-1}"

  set +e
  bash "$entrypoint_file" "${@:2}"
  result=$?
  set -e
  rm -rf "$tmp"
  tmp=""
  trap - EXIT
  exit "$result"
}

main "$@"
