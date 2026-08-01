#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

usage() {
  cat >&2 <<'EOF'
Uso:
  sudo scripts/publish-hextunnel-release.sh <commit_sha> <version>

Ejemplo:
  sudo scripts/publish-hextunnel-release.sh \
    eb8b750f8d2df93fabf1f3505ee26fc9519042ee \
    1.0.0-rc.2
EOF
  exit 2
}

[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo 'ERROR: se requiere root.' >&2; exit 1; }
[[ $# -eq 2 ]] || usage

COMMIT_SHA="${1,,}"
VERSION="$2"
REPOSITORY_URL="${HEXTUNNEL_SOURCE_REPOSITORY:-https://github.com/Gh0stDeveloper/Porno-OS.git}"
REGISTER_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/register-release.sh"

[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: commit_sha debe contener 40 caracteres hexadecimales.' >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo 'ERROR: versión inválida.' >&2; exit 1; }
[[ -x "$REGISTER_SCRIPT" ]] || { echo "ERROR: falta $REGISTER_SCRIPT" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends git rsync tar gzip ca-certificates jq

WORK_ROOT="$(mktemp -d /tmp/hextunnel-publish.XXXXXX)"
SOURCE_DIR="$WORK_ROOT/source"
STAGE_DIR="$WORK_ROOT/stage"
ARCHIVE="/root/hextunnel-$VERSION.tar.gz"
BUILD_INFO="/root/hextunnel-$VERSION-build-info.txt"
RELEASE_JSON="/root/hextunnel-$VERSION-release.json"
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

SOURCE_VERSION="$(tr -d '\r\n' < "$SOURCE_DIR/VERSION" 2>/dev/null || true)"
[[ "$SOURCE_VERSION" == "$VERSION" ]] || {
  echo "ERROR: VERSION del repositorio es '$SOURCE_VERSION'; se solicitó '$VERSION'." >&2
  exit 1
}

bash -n "$SOURCE_DIR/install.sh"
bash -n "$SOURCE_DIR/bin/hextunnel-private-install"
bash -n "$SOURCE_DIR/bin/hextunnel-private-upgrade"
bash -n "$SOURCE_DIR/bin/hextunnel-license"
bash "$SOURCE_DIR/tests/security/test-hardening.sh"
bash "$SOURCE_DIR/tests/unit/test-license-runtime.sh"

rsync -a --delete \
  --exclude='.git/' \
  --exclude='.github/' \
  --exclude='dist/' \
  --exclude='*.tar.gz' \
  --exclude='*.sha256' \
  "$SOURCE_DIR/" "$STAGE_DIR/"

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

rm -f "$ARCHIVE" "$RELEASE_JSON"
tar \
  --sort=name \
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

"$REGISTER_SCRIPT" \
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
