from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.database import get_connection, row_to_dict


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("邮箱格式不正确。")
        return normalized


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录。")
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (payload.get("sub"),)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在。")
    return dict(row)


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, Any]:
    now = _now()
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.username.strip(), payload.email.lower(), hash_password(payload.password), now, now),
            )
            user_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO user_settings
                (user_id, theme, default_model_provider, default_symbol, default_period, created_at, updated_at)
                VALUES (?, 'black_gold', 'deepseek', '000001.XSHE', 'day', ?, ?)
                """,
                (user_id, now, now),
            )
            user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    except Exception as exc:
        message = "用户名或邮箱已存在。" if "UNIQUE" in str(exc).upper() else f"注册失败：{exc}"
        raise HTTPException(status_code=400, detail=message) from exc
    token = create_access_token({"sub": user["id"], "username": user["username"]})
    return {"token": token, "user": _public_user(user)}


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    key = payload.username_or_email.strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (key, key.lower()),
        ).fetchone()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码不正确。")
    user = dict(row)
    token = create_access_token({"sub": user["id"], "username": user["username"]})
    return {"token": token, "user": _public_user(user)}


@router.get("/me")
def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _public_user(user)}


@router.post("/logout")
def logout() -> dict[str, Any]:
    return {"success": True}
