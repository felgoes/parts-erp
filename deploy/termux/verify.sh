#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
PASSWORD_FILE="$APP_DIR/data/initial-admin-password"
RESPONSE_FILE="$PREFIX/tmp/parts-erp-login-check.json"

if [[ ! -f "$PASSWORD_FILE" ]]; then
  echo "Arquivo da senha inicial não existe; verificando apenas a saúde da API."
  curl --fail --silent --show-error http://127.0.0.1:8000/health
  exit 0
fi

password="$(cat "$PASSWORD_FILE")"
status="$(curl --silent --show-error --output "$RESPONSE_FILE" --write-out '%{http_code}' \
  --request POST \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin@parts-erp.com.br' \
  --data-urlencode "password=$password" \
  http://127.0.0.1:8080/api/v1/auth/login)"

STATUS="$status" RESPONSE_FILE="$RESPONSE_FILE" "$APP_DIR/backend/.venv-termux/bin/python" - <<'PY'
import json
import os

with open(os.environ["RESPONSE_FILE"], encoding="utf-8") as response_file:
    data = json.load(response_file)

print({"http": os.environ["STATUS"], "token_received": bool(data.get("access_token")), "user": data.get("user", {}).get("email")})
PY

rm -f "$RESPONSE_FILE"
[[ "$status" == "200" ]]
