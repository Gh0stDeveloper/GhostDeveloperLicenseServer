#!/usr/bin/env bash
set -Eeuo pipefail

[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo 'ERROR: se requiere root.' >&2; exit 1; }
[[ $# -ge 1 ]] || { echo "Uso: sudo $0 <license-id> [motivo]" >&2; exit 2; }
exec /usr/local/sbin/ghostctl revoke-key "$1" "${2:-Revocada manualmente}"
