#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $# -eq 1 && -s "$1" ]] || { echo "Uso: $0 /caminho/PartsERP-versao-push.apk" >&2; exit 2; }
APK="$(realpath "$1")"
[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || { echo "Publique a partir de um commit limpo." >&2; exit 1; }
git -C "$ROOT_DIR" fetch --quiet origin main
[[ "$(git -C "$ROOT_DIR" rev-parse HEAD)" == "$(git -C "$ROOT_DIR" rev-parse origin/main)" ]] || { echo "HEAD deve corresponder a origin/main." >&2; exit 1; }

AAPT="${AAPT:-$(command -v aapt || true)}"
APKSIGNER="${APKSIGNER:-$(command -v apksigner || true)}"
[[ -x "$AAPT" && -x "$APKSIGNER" ]] || { echo "Defina AAPT e APKSIGNER com as ferramentas do Android SDK." >&2; exit 1; }
BADGING="$("$AAPT" dump badging "$APK" | head -n 1)"
PACKAGE="$(printf '%s\n' "$BADGING" | sed -nE "s/^package: name='([^']+)'.*/\1/p")"
VERSION="$(printf '%s\n' "$BADGING" | sed -nE "s/.*versionName='([^']+)'.*/\1/p")"
VERSION_CODE="$(printf '%s\n' "$BADGING" | sed -nE "s/.*versionCode='([^']+)'.*/\1/p")"
[[ "$PACKAGE" == "br.com.goesautoparts.erp" && "$VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ && "$VERSION_CODE" =~ ^[0-9]+$ ]] || { echo "Pacote ou versão Android inválidos." >&2; exit 1; }
SIGNATURE="$("$APKSIGNER" verify --print-certs "$APK" | awk '/Signer #1 certificate SHA-256 digest:/ { print $NF; exit }')"
[[ "$SIGNATURE" =~ ^[a-f0-9]{64}$ ]] || { echo "APK sem assinatura válida." >&2; exit 1; }
HASH="$(sha256sum "$APK" | cut -d' ' -f1)"
COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
TARGET="PartsERP-${VERSION}-push.apk"
STAGE=".upload-${VERSION}-${HASH:0:12}.apk"
MANIFEST_STAGE=".upload-${VERSION}-${HASH:0:12}.json"
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
python3 - "$MANIFEST" "$TARGET" "$VERSION" "$VERSION_CODE" "$COMMIT" "$HASH" "$SIGNATURE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path, filename, version, code, commit, digest, signer = sys.argv[1:]
Path(path).write_text(json.dumps({
    "file": filename,
    "version": version,
    "version_code": int(code),
    "package": "br.com.goesautoparts.erp",
    "source_commit": commit,
    "sha256": digest,
    "signer_sha256": signer,
    "published_at_utc": datetime.now(timezone.utc).isoformat(),
}, indent=2) + "\n")
PY

S9_HOST="${S9_HOST:-REMOTE_HOST}"
S9_USER="${S9_USER:-DEPLOY_USER}"
S9_PORT="${S9_PORT:-8022}"
S9_APP_DIR="${S9_APP_DIR:-parts-erp}"
REMOTE="$S9_USER@$S9_HOST"
SSH_OPTS=(-p "$S9_PORT" -o BatchMode=yes -o ConnectTimeout=10)
SCP_OPTS=(-P "$S9_PORT" -o BatchMode=yes -o ConnectTimeout=10)
if [[ -n "${S9_IDENTITY_FILE:-}" ]]; then
  SSH_OPTS+=(-i "$S9_IDENTITY_FILE")
  SCP_OPTS+=(-i "$S9_IDENTITY_FILE")
fi
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" <<'PREP'
set -euo pipefail
APP="$(realpath -m "$HOME/$1")"
[[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
mkdir -p "$APP/data/apks"
PREP
scp "${SCP_OPTS[@]}" "$APK" "$REMOTE:$S9_APP_DIR/data/apks/$STAGE"
scp "${SCP_OPTS[@]}" "$MANIFEST" "$REMOTE:$S9_APP_DIR/data/apks/$MANIFEST_STAGE"
ssh "${SSH_OPTS[@]}" "$REMOTE" bash -s -- "$S9_APP_DIR" "$STAGE" "$MANIFEST_STAGE" "$TARGET" "$HASH" <<'PUBLISH'
set -euo pipefail
APP="$(realpath -m "$HOME/$1")"
[[ "$APP" == "$HOME"/* && "$APP" != "$HOME" ]]
DIR="$APP/data/apks"
STAGE="$2"; MANIFEST_STAGE="$3"; TARGET="$4"; EXPECTED="$5"
[[ "$STAGE" =~ ^\.upload-[0-9.]+-[a-f0-9]{12}\.apk$ && "$MANIFEST_STAGE" =~ ^\.upload-[0-9.]+-[a-f0-9]{12}\.json$ && "$TARGET" =~ ^PartsERP-[0-9.]+-push\.apk$ && "$EXPECTED" =~ ^[a-f0-9]{64}$ ]]
[[ "$(sha256sum "$DIR/$STAGE" | cut -d' ' -f1)" == "$EXPECTED" ]]
if [[ -e "$DIR/$TARGET" ]]; then
  [[ "$(sha256sum "$DIR/$TARGET" | cut -d' ' -f1)" == "$EXPECTED" ]] || { echo "Esta versão já existe com outro conteúdo." >&2; exit 1; }
  rm "$DIR/$STAGE"
else
  mv "$DIR/$STAGE" "$DIR/$TARGET"
fi
mv "$DIR/$MANIFEST_STAGE" "$DIR/${TARGET%.apk}.json"
chmod 644 "$DIR/$TARGET" "$DIR/${TARGET%.apk}.json"
ln -s "$TARGET" "$DIR/.latest.apk.new"
mv -f "$DIR/.latest.apk.new" "$DIR/latest.apk"
ln -s "${TARGET%.apk}.json" "$DIR/.latest.json.new"
mv -f "$DIR/.latest.json.new" "$DIR/latest.json"
printf 'APK publicado: %s (%s)\n' "$TARGET" "$EXPECTED"
PUBLISH
