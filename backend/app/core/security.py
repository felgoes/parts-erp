import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")


def biometric_credential_version(password_hash_value: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.secret_key.get_secret_value().encode(),
        password_hash_value.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_biometric_token(subject: str, password_hash_value: str) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.biometric_credential_days)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
        "type": "biometric",
        "version": biometric_credential_version(password_hash_value),
    }
    token = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")
    return token, expires_at


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=["HS256"])


def encrypt_secret(value: str) -> str:
    key = get_settings().token_encryption_key.get_secret_value().encode()
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    key = get_settings().token_encryption_key.get_secret_value().encode()
    return Fernet(key).decrypt(value.encode()).decode()
