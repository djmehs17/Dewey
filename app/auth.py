from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def generate_session_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, expected = encoded.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode(salt),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(_b64encode(digest), expected)


def issue_session(username: str, secret: str, ttl_hours: int) -> str:
    expires = int(time.time() + max(1, int(ttl_hours or 1)) * 60 * 60)
    payload = f"{username}|{expires}"
    signature = _sign(payload, secret)
    return f"{payload}|{signature}"


def verify_session(token: str | None, *, username: str, secret: str) -> bool:
    if not token or not username or not secret:
        return False
    try:
        session_username, expires, signature = token.split("|", 2)
        expires_at = int(expires)
    except (TypeError, ValueError):
        return False
    if session_username != username or expires_at < int(time.time()):
        return False
    return hmac.compare_digest(_sign(f"{session_username}|{expires_at}", secret), signature)


def prepare_auth_settings_payload(payload: dict[str, Any], current: Any) -> dict[str, Any]:
    updates = dict(payload)
    username = str(updates.get("auth_username", getattr(current, "auth_username", "")) or "")
    if "|" in username:
        raise ValueError("Dewey login username cannot contain the | character.")
    raw_password = str(updates.pop("auth_password", "") or "")
    password = raw_password.strip()
    if password:
        if len(password) < 8:
            raise ValueError("Dewey login password must be at least 8 characters.")
        updates["auth_password_hash"] = hash_password(raw_password)

    enabling = bool(updates.get("auth_enabled")) and not bool(getattr(current, "auth_enabled", False))
    wants_auth = bool(updates.get("auth_enabled", getattr(current, "auth_enabled", False)))
    has_password = bool(updates.get("auth_password_hash") or getattr(current, "auth_password_hash", ""))
    if wants_auth and not has_password:
        raise ValueError("Set a Dewey login password before enabling app-level authentication.")

    has_secret = bool(updates.get("auth_session_secret") or getattr(current, "auth_session_secret", ""))
    if (wants_auth or enabling or updates.get("auth_password_hash")) and not has_secret:
        updates["auth_session_secret"] = generate_session_secret()
    return updates


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
