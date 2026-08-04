#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

usage() {
  cat >&2 <<'EOF'
Uso:
  sudo scripts/publish-hextunnel-release.sh <commit_sha> [version]

La versión se obtiene automáticamente del archivo VERSION del commit. Si se
indica manualmente, debe coincidir exactamente.
EOF
  exit 2
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo 'ERROR: se requiere root.' >&2; exit 1; }
[[ $# -ge 1 && $# -le 2 ]] || usage

COMMIT_SHA="${1,,}"
REQUESTED_VERSION="${2:-}"
REPOSITORY_URL="${HEXTUNNEL_SOURCE_REPOSITORY:-https://github.com/Gh0stDeveloper/Porno-OS.git}"
REGISTER_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/register-release.sh"

[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: commit_sha debe contener 40 caracteres hexadecimales.' >&2; exit 1; }
[[ -z "$REQUESTED_VERSION" || "$REQUESTED_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] \
  || { echo 'ERROR: versión inválida.' >&2; exit 1; }
[[ -f "$REGISTER_SCRIPT" ]] || { echo "ERROR: falta $REGISTER_SCRIPT" >&2; exit 1; }

missing=0
for command in git rsync tar gzip jq shellcheck curl; do
  command -v "$command" >/dev/null 2>&1 || missing=1
done
if ((missing)); then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    git rsync tar gzip ca-certificates jq shellcheck curl
fi

WORK_ROOT="$(mktemp -d /tmp/hextunnel-publish.XXXXXX)"
SOURCE_DIR="$WORK_ROOT/source"
STAGE_DIR="$WORK_ROOT/stage"
trap 'rm -rf "${WORK_ROOT:-}"' EXIT

mkdir -p "$SOURCE_DIR" "$STAGE_DIR"
git -C "$SOURCE_DIR" init -q
git -C "$SOURCE_DIR" remote add origin "$REPOSITORY_URL"
git -C "$SOURCE_DIR" fetch --depth=1 origin "$COMMIT_SHA"
git -C "$SOURCE_DIR" checkout -q --detach FETCH_HEAD

RESOLVED_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
[[ "$RESOLVED_COMMIT" == "$COMMIT_SHA" ]] || {
  echo "ERROR: Git resolvió $RESOLVED_COMMIT en vez de $COMMIT_SHA." >&2
  exit 1
}

VERSION="$(tr -d '\r\n' < "$SOURCE_DIR/VERSION" 2>/dev/null || true)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] \
  || { echo "ERROR: VERSION del repositorio es inválida: '$VERSION'." >&2; exit 1; }
if [[ -n "$REQUESTED_VERSION" && "$REQUESTED_VERSION" != "$VERSION" ]]; then
  echo "ERROR: VERSION del repositorio es '$VERSION'; se solicitó '$REQUESTED_VERSION'." >&2
  exit 1
fi

ARCHIVE="/root/hextunnel-$VERSION.tar.gz"
BUILD_INFO="/root/hextunnel-$VERSION-build-info.txt"
RELEASE_JSON="/root/hextunnel-$VERSION-release.json"

bash "$SOURCE_DIR/scripts/resolve-component-lock.sh" "$SOURCE_DIR/config/component-lock.env"
HEXTUNNEL_RELEASE_BUILD=1 bash "$SOURCE_DIR/scripts/production-readiness.sh"

rsync -a --delete \
  --exclude='.git/' \
  --exclude='.github/' \
  --exclude='dist/' \
  --exclude='*.tar.gz' \
  --exclude='*.sha256' \
  "$SOURCE_DIR/" "$STAGE_DIR/"

# GitHub's Contents API cannot reliably set an executable bit when files are
# created or replaced. Normalize the commercial staging tree exactly as the
# reproducible package builder does, so the package tested by the gate and the
# package registered by the LicenseServer have compatible modes.
find "$STAGE_DIR" -type d -exec chmod 0755 {} +
find "$STAGE_DIR" -type f -exec chmod 0644 {} +
chmod 0755 \
  "$STAGE_DIR/install.sh" \
  "$STAGE_DIR/beta-install.sh" \
  "$STAGE_DIR"/bin/* \
  "$STAGE_DIR"/scripts/*.sh \
  "$STAGE_DIR/legacy/install-all.sh"

cat > "$STAGE_DIR/RELEASE-SOURCE.env" <<EOF
HEXTUNNEL_RELEASE_VERSION=$(printf '%q' "$VERSION")
HEXTUNNEL_SOURCE_COMMIT=$(printf '%q' "$COMMIT_SHA")
HEXTUNNEL_SOURCE_REPOSITORY=$(printf '%q' "$REPOSITORY_URL")
HEXTUNNEL_BUILT_AT=$(printf '%q' "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
EOF
chmod 0644 "$STAGE_DIR/RELEASE-SOURCE.env"

if find "$STAGE_DIR" -type l -print -quit | grep -q .; then
  echo 'ERROR: el árbol contiene enlaces simbólicos y no puede publicarse.' >&2
  find "$STAGE_DIR" -type l -print >&2
  exit 1
fi

for required in \
  install.sh \
  bin/hextunnel-private-install \
  bin/hextunnel-private-upgrade \
  bin/hextunnel-license \
  bin/hextunnel-install-license-runtime \
  lib/common.sh \
  lib/framework.sh; do
  [[ -s "$STAGE_DIR/$required" ]] || { echo "ERROR: falta $required" >&2; exit 1; }
done

for executable in \
  install.sh \
  bin/hextunnel-private-install \
  bin/hextunnel-private-upgrade \
  bin/hextunnel-license \
  bin/hextunnel-install-license-runtime; do
  [[ -x "$STAGE_DIR/$executable" ]] \
    || { echo "ERROR: $executable no quedó ejecutable en staging." >&2; exit 1; }
done

rm -f "$ARCHIVE" "$RELEASE_JSON"
tar \
  --sort=name \
  --mtime="@$(git -C "$SOURCE_DIR" log -1 --format=%ct)" \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -C "$STAGE_DIR" \
  -czf "$ARCHIVE" \
  .
chmod 0600 "$ARCHIVE"

tar -tzf "$ARCHIVE" | sed 's#^\./##' | grep -Fxq 'bin/hextunnel-private-install'
tar -tzf "$ARCHIVE" | sed 's#^\./##' | grep -Fxq 'bin/hextunnel-private-upgrade'
tar -tzf "$ARCHIVE" | sed 's#^\./##' | grep -Fxq 'bin/hextunnel-license'

for executable in \
  ./install.sh \
  ./bin/hextunnel-private-install \
  ./bin/hextunnel-private-upgrade \
  ./bin/hextunnel-license \
  ./bin/hextunnel-install-license-runtime; do
  archive_mode="$(tar -tvzf "$ARCHIVE" | awk -v path="$executable" '$NF == path {print $1; exit}')"
  [[ "$archive_mode" == -rwx* ]] \
    || { echo "ERROR: $executable perdió el permiso ejecutable dentro del TAR.GZ ($archive_mode)." >&2; exit 1; }
done

if tar -tzf "$ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
  echo 'ERROR: el TAR.GZ contiene rutas inseguras.' >&2
  exit 1
fi

{
  echo "version=$VERSION"
  echo "commit=$COMMIT_SHA"
  echo "repository=$REPOSITORY_URL"
  echo "sha256=$(sha256sum "$ARCHIVE" | awk '{print $1}')"
  echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$BUILD_INFO"
chmod 0600 "$BUILD_INFO"

bash "$REGISTER_SCRIPT" \
  "$ARCHIVE" \
  "$VERSION" \
  hextunnel \
  bin/hextunnel-private-install \
  | tee "$RELEASE_JSON"
chmod 0600 "$RELEASE_JSON"

jq -e --arg version "$VERSION" '
  .product == "hextunnel" and
  .version == $version and
  .entrypoint == "bin/hextunnel-private-install" and
  .active == true
' "$RELEASE_JSON" >/dev/null

printf '\nRelease publicada correctamente.\n'
printf 'Paquete: %s\n' "$ARCHIVE"
printf 'Procedencia: %s\n' "$BUILD_INFO"
printf 'Registro API: %s\n' "$RELEASE_JSON"
