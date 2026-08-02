#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

API_BASE="${GHOSTCTL_API_BASE:-http://127.0.0.1:8080}"
ADMIN_TOKEN_FILE="${GHOSTCTL_ADMIN_TOKEN_FILE:-/etc/ghostdeveloper-license/secrets/admin-token}"
SERVER_REPOSITORY="${GHOSTCTL_SERVER_REPOSITORY:-Gh0stDeveloper/GhostDeveloperLicenseServer}"
SERVER_REF="${GHOSTCTL_SERVER_REF:-agent/public-bootstrap-web}"
BOT_REPOSITORY="${GHOSTCTL_BOT_REPOSITORY:-Gh0stDeveloper/TeleBotGen}"
BOT_REF="${GHOSTCTL_BOT_REF:-feat/hextunnel-license-integration}"
HEX_REPOSITORY="${GHOSTCTL_HEX_REPOSITORY:-Gh0stDeveloper/Porno-OS}"
GITHUB_TOKEN_FILE="${GHOSTCTL_GITHUB_TOKEN_FILE:-/etc/ghostdeveloper-license/secrets/github-token}"
LOCK_FILE=/run/lock/ghostdeveloper-operations.lock
LOG_DIR=/var/log/ghostdeveloper-operations

log() { printf '[ghostctl] %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_root() { [[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'ejecuta ghostctl mediante sudo.'; }

usage() {
  cat <<'EOF'
Ghost Developer Operations

Uso:
  ghostctl status
  ghostctl smoke
  ghostctl releases [producto]
  ghostctl activate <producto> <version>
  ghostctl create-key [minutos] [telegram_id] [username]
  ghostctl deploy-server [ref]
  ghostctl rollback-server
  ghostctl deploy-bot [ref]
  ghostctl publish-hextunnel <commit_sha> [version]
  ghostctl release-all <commit_sha> [version] [server_ref] [bot_ref]

Sin argumentos abre un menú interactivo.
EOF
}

admin_curl() {
  local method="$1" path="$2" payload="${3:-}" token config
  [[ -s "$ADMIN_TOKEN_FILE" ]] || fail "falta $ADMIN_TOKEN_FILE"
  token="$(tr -d '\r\n' < "$ADMIN_TOKEN_FILE")"
  config="$(mktemp /tmp/ghostctl-curl.XXXXXX)"
  printf 'header = "Authorization: Bearer %s"\n' "$token" > "$config"
  chmod 600 "$config"
  if [[ "$method" == GET ]]; then
    curl -fsS --connect-timeout 3 --max-time 30 --config "$config" "$API_BASE$path"
  else
    curl -fsS --connect-timeout 3 --max-time 60 --config "$config" \
      -H 'Content-Type: application/json' --data-binary "$payload" -X "$method" "$API_BASE$path"
  fi
  rm -f "$config"
}

api_online() {
  curl -fsS --connect-timeout 3 --max-time 8 "$API_BASE/health" | jq -e '.status == "online"' >/dev/null
}

status_command() {
  printf '=== Servicios ===\n'
  systemctl is-active ghost-license-api.service || true
  systemctl is-active ghost-license-backup.timer || true
  systemctl is-active telebotgen.service || true
  printf '\n=== API local ===\n'
  curl -fsS "$API_BASE/health" | jq . || true
  printf '\n=== Release Hex Tunnel activa ===\n'
  admin_curl GET '/api/v1/admin/releases?product=hextunnel' \
    | jq '[.[] | select(.active == true)] | first // {active:false}'
  printf '\n=== Enlaces actuales ===\n'
  readlink -f /opt/ghostdeveloper-license-server/current 2>/dev/null || true
  readlink -f /opt/ghostdeveloper-license-server/previous 2>/dev/null || true
  printf '\n=== Espacio ===\n'
  df -h / /var/lib/ghostdeveloper-license 2>/dev/null || df -h /
}

smoke_command() {
  local failed=0
  printf 'API local: '
  if api_online; then echo OK; else echo ERROR; failed=1; fi
  for url in \
    https://ghostdeveloperkeys.duckdns.org/health \
    https://ghostdeveloperdownloads.duckdns.org/health; do
    printf '%s: ' "$url"
    if curl -fsS --connect-timeout 5 --max-time 15 "$url" | jq -e '.status == "online"' >/dev/null; then
      echo OK
    else
      echo ERROR
      failed=1
    fi
  done
  printf 'Página pública: '
  if curl -fsSI --connect-timeout 5 --max-time 15 https://ghostdeveloper.duckdns.org/ | head -n1 | grep -Eq ' 2[0-9]{2} '; then
    echo OK
  else
    echo ERROR
    failed=1
  fi
  printf 'Bootstrap público: '
  if curl -fsS --connect-timeout 5 --max-time 20 https://ghostdeveloper.duckdns.org/install.sh \
    | grep -Fq 'amd64|x86_64|arm64|aarch64'; then
    echo OK
  else
    echo ERROR
    failed=1
  fi
  return "$failed"
}

releases_command() {
  local product="${1:-hextunnel}"
  admin_curl GET "/api/v1/admin/releases?product=$product" \
    | jq -r '.[] | [.version, (if .active then "ACTIVE" else "inactive" end), .sha256, .relative_path] | @tsv' \
    | column -t -s $'\t'
}

activate_command() {
  local product="${1:-}" version="${2:-}" data release_id payload
  [[ -n "$product" && -n "$version" ]] || fail 'uso: ghostctl activate <producto> <version>'
  data="$(admin_curl GET "/api/v1/admin/releases?product=$product")"
  release_id="$(jq -r --arg version "$version" '.[] | select(.version == $version) | .id' <<< "$data" | head -n1)"
  [[ -n "$release_id" && "$release_id" != null ]] || fail "no existe $product $version"
  payload="$(jq -n --arg reason "Activada mediante ghostctl" '{reason:$reason}')"
  admin_curl POST "/api/v1/admin/releases/$release_id/activate" "$payload" | jq .
}

create_key_command() {
  local minutes="${1:-240}" telegram_id="${2:-}" username="${3:-}" payload
  [[ "$minutes" =~ ^[0-9]+$ && "$minutes" -ge 1 && "$minutes" -le 525600 ]] \
    || fail 'los minutos deben estar entre 1 y 525600.'
  [[ -z "$telegram_id" || "$telegram_id" =~ ^[0-9]+$ ]] || fail 'telegram_id inválido.'
  payload="$(jq -n \
    --arg telegram_id "$telegram_id" \
    --arg username "$username" \
    --argjson minutes "$minutes" \
    '{product:"hextunnel",owner_telegram_id:(if ($telegram_id|length)>0 then $telegram_id else null end),owner_username:(if ($username|length)>0 then $username else null end),expires_in_minutes:$minutes,activation_limit:1,metadata:{channel:"ghostctl"}}')"
  admin_curl POST '/api/v1/admin/licenses' "$payload" | jq .
}

github_download() {
  local repository="$1" ref="$2" destination="$3" url token
  url="https://api.github.com/repos/${repository}/tarball/${ref}"
  if [[ -s "$GITHUB_TOKEN_FILE" ]]; then
    token="$(tr -d '\r\n' < "$GITHUB_TOKEN_FILE")"
    curl -fL --retry 3 --connect-timeout 10 --max-time 300 \
      -H 'Accept: application/vnd.github+json' \
      -H "Authorization: Bearer $token" \
      -o "$destination" "$url"
  else
    curl -fL --retry 3 --connect-timeout 10 --max-time 300 \
      -H 'Accept: application/vnd.github+json' \
      -o "$destination" "$url"
  fi
}

extract_repository() {
  local repository="$1" ref="$2" output="$3" archive
  archive="$(mktemp /tmp/ghostctl-repository.XXXXXX.tar.gz)"
  github_download "$repository" "$ref" "$archive"
  install -d -m 700 "$output"
  tar -xzf "$archive" --strip-components=1 -C "$output"
  rm -f "$archive"
}

deploy_server_command() {
  local ref="${1:-$SERVER_REF}" work
  work="$(mktemp -d /tmp/ghostctl-server.XXXXXX)"
  trap 'rm -rf "${work:-}"' RETURN
  log "Descargando $SERVER_REPOSITORY@$ref"
  extract_repository "$SERVER_REPOSITORY" "$ref" "$work"
  bash -n "$work/scripts/install-server.sh"
  bash "$work/scripts/install-server.sh"
  rm -rf "$work"
  trap - RETURN
}

deploy_bot_command() {
  local ref="${1:-$BOT_REF}" work
  work="$(mktemp -d /tmp/ghostctl-bot.XXXXXX)"
  trap 'rm -rf "${work:-}"' RETURN
  log "Descargando $BOT_REPOSITORY@$ref"
  extract_repository "$BOT_REPOSITORY" "$ref" "$work"
  TELEBOTGEN_REPOSITORY="$BOT_REPOSITORY" TELEBOTGEN_REF="$ref" \
    bash "$work/confbot.sh" install
  systemctl is-active --quiet telebotgen.service \
    || fail 'TeleBotGen no quedó activo después del despliegue.'
  rm -rf "$work"
  trap - RETURN
}

publish_hextunnel_command() {
  local commit="${1:-}" version="${2:-}"
  [[ "$commit" =~ ^[0-9a-fA-F]{40}$ ]] || fail 'indica un commit SHA completo de Hex Tunnel.'
  export HEXTUNNEL_SOURCE_REPOSITORY="https://github.com/${HEX_REPOSITORY}.git"
  if [[ -n "$version" ]]; then
    bash /opt/ghostdeveloper-license-server/current/scripts/publish-hextunnel-release.sh "$commit" "$version"
  else
    bash /opt/ghostdeveloper-license-server/current/scripts/publish-hextunnel-release.sh "$commit"
  fi
}

rollback_server_command() {
  local current previous
  current="$(readlink -f /opt/ghostdeveloper-license-server/current 2>/dev/null || true)"
  previous="$(readlink -f /opt/ghostdeveloper-license-server/previous 2>/dev/null || true)"
  [[ -n "$previous" && -d "$previous" ]] || fail 'no existe una release anterior disponible.'
  ln -sfn "$previous" /opt/ghostdeveloper-license-server/current.next
  mv -Tf /opt/ghostdeveloper-license-server/current.next /opt/ghostdeveloper-license-server/current
  ln -sfn "$current" /opt/ghostdeveloper-license-server/previous.next
  mv -Tf /opt/ghostdeveloper-license-server/previous.next /opt/ghostdeveloper-license-server/previous
  systemctl daemon-reload
  systemctl restart ghost-license-api.service
  api_online || fail 'la release anterior tampoco superó el health check.'
  log "Rollback completado: $previous"
}

release_all_command() {
  local commit="${1:-}" version="${2:-}" server_ref="${3:-$SERVER_REF}" bot_ref="${4:-$BOT_REF}"
  [[ "$commit" =~ ^[0-9a-fA-F]{40}$ ]] || fail 'indica el commit SHA completo de Hex Tunnel.'
  deploy_server_command "$server_ref"
  publish_hextunnel_command "$commit" "$version"
  deploy_bot_command "$bot_ref"
  smoke_command
  status_command
}

interactive_menu() {
  local option value second
  while true; do
    clear || true
    cat <<'EOF'
============================================================
               GHOST DEVELOPER OPERATIONS
============================================================
  1) Estado completo
  2) Prueba rápida
  3) Ver releases Hex Tunnel
  4) Activar una versión existente
  5) Generar key manual
  6) Actualizar servidor de licencias
  7) Actualizar TeleBotGen
  8) Publicar Hex Tunnel
  9) Actualizar todo
 10) Rollback del servidor
  0) Salir
============================================================
EOF
    read -r -p 'Opción: ' option
    case "$option" in
      1) status_command ;;
      2) smoke_command || true ;;
      3) releases_command hextunnel ;;
      4) read -r -p 'Versión: ' value; activate_command hextunnel "$value" ;;
      5) read -r -p 'Minutos: ' value; create_key_command "${value:-240}" ;;
      6) read -r -p "Ref [$SERVER_REF]: " value; deploy_server_command "${value:-$SERVER_REF}" ;;
      7) read -r -p "Ref [$BOT_REF]: " value; deploy_bot_command "${value:-$BOT_REF}" ;;
      8) read -r -p 'Commit Hex Tunnel: ' value; read -r -p 'Versión (vacío=automática): ' second; publish_hextunnel_command "$value" "$second" ;;
      9) read -r -p 'Commit Hex Tunnel: ' value; read -r -p 'Versión (vacío=automática): ' second; release_all_command "$value" "$second" ;;
      10) rollback_server_command ;;
      0) return ;;
      *) echo 'Opción inválida.' ;;
    esac
    read -r -p 'Presiona Enter para continuar...' _
  done
}

main() {
  require_root
  install -d -m 750 "$LOG_DIR"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail 'ya existe otra operación de despliegue o publicación en curso.'
  case "${1:-menu}" in
    status) status_command ;;
    smoke) smoke_command ;;
    releases) releases_command "${2:-hextunnel}" ;;
    activate) activate_command "${2:-}" "${3:-}" ;;
    create-key) create_key_command "${2:-240}" "${3:-}" "${4:-}" ;;
    deploy-server) deploy_server_command "${2:-$SERVER_REF}" ;;
    rollback-server) rollback_server_command ;;
    deploy-bot) deploy_bot_command "${2:-$BOT_REF}" ;;
    publish-hextunnel) publish_hextunnel_command "${2:-}" "${3:-}" ;;
    release-all) release_all_command "${2:-}" "${3:-}" "${4:-$SERVER_REF}" "${5:-$BOT_REF}" ;;
    menu) interactive_menu ;;
    help|--help|-h) usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
