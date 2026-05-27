from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


SECRET_KEY = os.getenv("LOBSTER_SECRET_KEY") or os.getenv("SECRET_KEY") or "lobster-quant-local-dev-secret"
TOKEN_TTL_SECONDS = int(os.getenv("LOBSTER_TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256$200000${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        return hmac.compare_digest(candidate.hex(), digest)
    except Exception:
        return False


def create_access_token(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = {**payload, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(body, separators=(',', ':')).encode())}"
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        header_text, body_text, signature_text = token.split(".", 2)
        signing_input = f"{header_text}.{body_text}"
        expected = _b64url(hmac.new(SECRET_KEY.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_text):
            return None
        body = json.loads(_b64url_decode(body_text))
        if int(body.get("exp") or 0) < int(time.time()):
            return None
        return body
    except Exception:
        return None


def _secret_stream(length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(hashlib.sha256(f"{SECRET_KEY}:{counter}".encode("utf-8")).digest())
        counter += 1
    return b"".join(chunks)[:length]


def encrypt_secret(value: str) -> str:
    raw = value.encode("utf-8")
    stream = _secret_stream(len(raw))
    encrypted = bytes(a ^ b for a, b in zip(raw, stream))
    return _b64url(encrypted)


def decrypt_secret(value: str) -> str:
    encrypted = _b64url_decode(value)
    stream = _secret_stream(len(encrypted))
    raw = bytes(a ^ b for a, b in zip(encrypted, stream))
    return raw.decode("utf-8")
