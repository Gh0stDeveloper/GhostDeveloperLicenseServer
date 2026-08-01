#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -ge 1 ]] || { echo "Uso: sudo $0 <license-id> [motivo]" >&2; exit 2; }
LICENSE_ID="$1"
REASON="${2:-Revocada manualmente}"
TOKEN="$(tr -d '\r\n' < /etc/ghostdeveloper-license/secrets/admin-token)"

jq -n --arg reason "$REASON" '{reason:$reason}' \
| curl -fsS \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    "http://127.0.0.1:8080/api/v1/admin/licenses/$LICENSE_ID/revoke"
printf '\n'
