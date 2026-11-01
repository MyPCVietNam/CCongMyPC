"""Auth helpers: Argon2id passwords, signed sessions, CSRF tokens."""

from __future__ import annotations

import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def make_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="mypc-attendance-session")


def issue_session_token(secret_key: str, payload: dict[str, Any]) -> str:
    return make_serializer(secret_key).dumps(payload)


def load_session_token(
    secret_key: str, token: str, max_age: int
) -> dict[str, Any] | None:
    try:
        data = make_serializer(secret_key).loads(token, max_age=max_age)
        if not isinstance(data, dict):
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_bootstrap_password() -> str:
    return secrets.token_urlsafe(18)
