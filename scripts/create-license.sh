#!/usr/bin/env bash
set -Eeuo pipefail

MINUTES="${1:-240}"
TELEGRAM_ID="${2:-}"
USERNAME="${3:-}"
PRODUCT="${4:-hextunnel}"
ADMIN_TOKEN_FILE=/etc/ghostdeveloper-license/secrets/admin-token
TOKEN="$(tr -d '\r\n' < "$ADMIN_TOKEN_FILE")"

jq -n \
  --arg product "$PRODUCT" \
  --arg telegram_id "$TELEGRAM_ID" \
  --arg username "$USERNAME" \
  --argjson minutes "$MINUTES" \
  '{product:$product,owner_telegram_id:(if ($telegram_id|length)>0 then $telegram_id else null end),owner_username:(if ($username|length)>0 then $username else null end),expires_in_minutes:$minutes,activation_limit:1}' \
| curl -fsS \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    http://127.0.0.1:8080/api/v1/admin/licenses
printf '\n'
