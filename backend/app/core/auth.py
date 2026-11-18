"""Minimal first-party tenant authentication using signed bearer tokens.

Use a high-entropy APP_AUTH_SECRET from a secret manager outside local development.
Passwords are PBKDF2-HMAC-SHA256 hashed; plaintext is never stored.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import store

bearer = HTTPBearer(auto_error=False)
bearer_dependency = Depends(bearer)
_secret_value = os.getenv("APP_AUTH_SECRET")
if os.getenv("APP_ENV", "development").lower() == "production" and not _secret_value:
    raise RuntimeError("APP_AUTH_SECRET must be set in production")
_SECRET = (_secret_value or "local-development-only-change-me").encode()
_TOKEN_TTL = 8 * 60 * 60


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    email: str
    role: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(user: dict[str, str]) -> str:
    payload = {
        "sub": user["user_id"], "tenant": user["tenant_id"],
        "email": user["email"], "role": user.get("role", "developer"), "exp": int(time.time()) + _TOKEN_TTL,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_SECRET, body, hashlib.sha256).digest()
    return body.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def decode_token(token: str) -> Principal:
    try:
        body_text, signature_text = token.split(".", 1)
        body = body_text.encode()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_SECRET, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        return Principal(
            user_id=str(payload["sub"]), tenant_id=str(payload["tenant"]), email=str(payload["email"]), role=str(payload.get("role", "developer"))
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token") from exc


def require_roles(*allowed_roles: str):
    def dependency(principal: Principal = principal_dependency) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient workspace role")
        return principal
    return dependency


def require_principal(
    credentials: HTTPAuthorizationCredentials | None = bearer_dependency,
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    principal = decode_token(credentials.credentials)
    user = store.get_user_by_id(principal.user_id)
    if user is None or user["tenant_id"] != principal.tenant_id or user["email"] != principal.email:
        raise HTTPException(status_code=401, detail="Account is no longer active")
    return Principal(
        user_id=principal.user_id, tenant_id=principal.tenant_id,
        email=principal.email, role=user["role"],
    )


principal_dependency = Depends(require_principal)
