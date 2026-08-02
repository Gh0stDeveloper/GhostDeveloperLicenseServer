#!/usr/bin/env bash
set -Eeuo pipefail

[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo 'ERROR: se requiere root.' >&2; exit 1; }
MINUTES="${1:-240}"
OWNER_ID="${2:-}"
OWNER_USERNAME="${3:-}"
PRODUCT="${4:-hextunnel}"
[[ "$PRODUCT" == hextunnel ]] || { echo 'ERROR: ghostctl create-key administra el producto hextunnel.' >&2; exit 1; }
exec /usr/local/sbin/ghostctl create-key "$MINUTES" "$OWNER_ID" "$OWNER_USERNAME"
