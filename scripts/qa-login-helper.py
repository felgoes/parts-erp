#!/usr/bin/env python3
"""Serve a local-only page that prefills the real HML login form from .env.qa.local."""

from __future__ import annotations

import ast
import html
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.qa.local"
HOST = "127.0.0.1"
PORT = 8765
REQUIRED_KEYS = {"BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD"}


def read_qa_credentials() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or key not in REQUIRED_KEYS:
            continue

        value = raw_value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            closing = value.find(quote, 1)
            if closing < 0:
                raise ValueError(f"Unclosed quoted value for {key}")
            quoted = value[: closing + 1]
            try:
                value = ast.literal_eval(quoted)
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"Invalid quoted value for {key}") from error
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value

    missing = REQUIRED_KEYS - values.keys()
    if missing:
        raise ValueError("Missing QA login settings in ignored .env.qa.local")
    return values


def make_page(credentials: dict[str, str], nonce: str) -> bytes:
    email = html.escape(credentials["BOOTSTRAP_ADMIN_EMAIL"], quote=True)
    password = html.escape(credentials["BOOTSTRAP_ADMIN_PASSWORD"], quote=True)
    document = f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login QA local</title>
<style>body{{font:16px system-ui,sans-serif;margin:1rem;color:#222}}iframe{{width:100%;height:90vh;border:0}}#status{{padding:.5rem}}</style></head>
<body>
<p id="status" role="status">Carregando o login do ERP com a conta QA local…</p>
<input hidden id="qa-email" value="{email}">
<input hidden id="qa-password" value="{password}">
<iframe id="erp-login" title="Login QA do Parts ERP" src="/login"></iframe>
<script nonce="{nonce}">
(() => {{
  const frame = document.getElementById('erp-login');
  const status = document.getElementById('status');
  let attempts = 0;
  const timer = setInterval(() => {{
    attempts += 1;
    try {{
      const doc = frame.contentDocument;
      const email = doc && doc.querySelector('input[type="email"]');
      const password = doc && doc.querySelector('input[type="password"]');
      if (email && password) {{
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(email, document.getElementById('qa-email').value);
        email.dispatchEvent(new Event('input', {{ bubbles: true }}));
        email.dispatchEvent(new Event('change', {{ bubbles: true }}));
        setter.call(password, document.getElementById('qa-password').value);
        password.dispatchEvent(new Event('input', {{ bubbles: true }}));
        password.dispatchEvent(new Event('change', {{ bubbles: true }}));
        status.textContent = 'Conta QA preenchida. Entre pelo formulário abaixo.';
        clearInterval(timer);
      }} else if (attempts >= 100) {{
        status.textContent = 'Não foi possível carregar o login. Confira HML e API.';
        clearInterval(timer);
      }}
    }} catch (_) {{
      status.textContent = 'O login precisa estar na mesma origem do HML local.';
      clearInterval(timer);
    }}
  }}, 100);
}})();
</script>
</body></html>"""
    return document.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = ""
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/__qa-login":
            self.send_error(404)
            return
        body = make_page(self.server.credentials, self.server.nonce)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; script-src 'nonce-{self.server.nonce}'; "
            "style-src 'unsafe-inline'; frame-src 'self'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        # Request paths and credentials must never be written to the terminal log.
        return


def main() -> None:
    credentials = read_qa_credentials()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.credentials = credentials  # type: ignore[attr-defined]
    server.nonce = secrets.token_urlsafe(18)  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
