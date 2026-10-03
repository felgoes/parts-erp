#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="${PARTS_ERP_DIR:-$HOME/parts-erp}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"

if [[ ! -x "$PREFIX/bin/pkg" ]]; then
  echo "Execute este script no Termux principal, não dentro de Proot/Ubuntu." >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/backend/pyproject.toml" ]]; then
  echo "Projeto não encontrado em $APP_DIR." >&2
  exit 1
fi

cd "$APP_DIR"
mkdir -p data/{backups,documents,logs,redis,run} "$HOME/.termux/boot"

if [[ ! -x backend/.venv-termux/bin/python ]] || \
  ! backend/.venv-termux/bin/python -c 'import app' 2>/dev/null; then
  python -m venv --system-site-packages backend/.venv-termux
  backend/.venv-termux/bin/python -m pip install --upgrade pip setuptools wheel
  backend/.venv-termux/bin/python -m pip install \
    --only-binary=:all: \
    --extra-index-url https://termux-user-repository.github.io/pypi/ \
    'pydantic-core==2.41.5'
  backend/.venv-termux/bin/python -m pip install \
    --extra-index-url https://termux-user-repository.github.io/pypi/ \
    ./backend
fi

if [[ ! -f frontend/dist/frontend/browser/index.html ]]; then
  (cd frontend && npm ci && npm run build)
fi

if [[ ! -f backend/.env ]]; then
  secret_key="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  token_key="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  webhook_secret="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  admin_password="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  cat >backend/.env <<EOF
APP_ENV=production
APP_NAME=Parts ERP
API_V1_PREFIX=/api/v1
FRONTEND_URL=http://127.0.0.1:8080
PUBLIC_SITE_URL=https://goesautoparts.com.br
SECRET_KEY=$secret_key
TOKEN_ENCRYPTION_KEY=$token_key
ACCESS_TOKEN_MINUTES=30
DATABASE_URL=sqlite+pysqlite:///$APP_DIR/data/parts-erp.db
REDIS_URL=redis://127.0.0.1:6379/0
DOCUMENTS_DIR=$APP_DIR/data/documents
BOOTSTRAP_ADMIN_EMAIL=admin@parts-erp.com.br
BOOTSTRAP_ADMIN_PASSWORD=$admin_password
MERCADOLIVRE_CLIENT_ID=
MERCADOLIVRE_CLIENT_SECRET=
MERCADOLIVRE_REDIRECT_URI=http://127.0.0.1:8080/api/v1/integrations/mercadolivre/callback
MERCADOLIVRE_SITE_ID=MLB
MERCADOLIVRE_API_URL=https://api.mercadolibre.com
MERCADOLIVRE_AUTH_URL=https://auth.mercadolivre.com.br/authorization
MERCADOLIVRE_AUTO_ISSUE_INVOICE=true
MERCADOLIVRE_AUTO_DOWNLOAD_LABEL=true
MERCADOLIVRE_LABEL_FORMAT=pdf
WEBHOOK_SHARED_SECRET=$webhook_secret
WEBHOOK_MAX_BODY_BYTES=131072
TELEMETRY_RATE_LIMIT_PER_MINUTE=60
LOGIN_RATE_LIMIT_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
SHOPEE_PARTNER_ID=
SHOPEE_PARTNER_KEY=
SHOPEE_REDIRECT_URI=http://127.0.0.1:8080/api/v1/integrations/shopee/callback
EOF
  chmod 600 backend/.env
  printf '%s\n' "$admin_password" >data/initial-admin-password
  chmod 600 data/initial-admin-password
fi

sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__PREFIX__|$PREFIX|g" \
  deploy/termux/nginx.conf.in >deploy/termux/nginx.conf
sed -e "s|__APP_DIR__|$APP_DIR|g" \
  deploy/termux/redis.conf.in >deploy/termux/redis.conf

chmod +x deploy/termux/*.sh

cat >"$HOME/.termux/boot/parts-erp" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
sleep 10
PARTS_ERP_DIR="$APP_DIR" "$APP_DIR/deploy/termux/start.sh" >>"$APP_DIR/data/logs/boot.log" 2>&1
EOF
chmod 700 "$HOME/.termux/boot/parts-erp"

(cd backend && .venv-termux/bin/alembic upgrade head)

if [[ ! -f data/.admin-bootstrapped ]]; then
  (cd backend && .venv-termux/bin/python -m app.cli bootstrap-admin)
  touch data/.admin-bootstrapped
fi

echo "Instalação concluída. Use deploy/termux/start.sh para iniciar."
