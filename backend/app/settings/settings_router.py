from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.auth.auth_router import get_current_user
from app.auth.security import decrypt_secret, encrypt_secret
from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

PROVIDERS = [
    {"provider": "deepseek", "label": "DeepSeek", "default_model": "deepseek-chat", "implemented": True},
    {"provider": "openai", "label": "OpenAI / GPT", "default_model": "gpt-4.1", "implemented": False},
    {"provider": "qwen", "label": "通义千问", "default_model": "qwen-plus", "implemented": False},
    {"provider": "kimi", "label": "Kimi", "default_model": "moonshot-v1-8k", "implemented": False},
    {"provider": "claude", "label": "Claude", "default_model": "claude-3-5-sonnet", "implemented": False},
    {"provider": "openrouter", "label": "OpenRouter", "default_model": "", "implemented": False},
    {"provider": "local", "label": "本地模型", "default_model": "local-llm", "implemented": False},
]

PURPOSES = ["strategy_generation", "strategy_debug", "backtest_audit", "stock_analysis", "news_summary"]


class UserSettingsPayload(BaseModel):
    theme: str = "black_gold"
    default_model_provider: str = "deepseek"
    default_symbol: str = "000001.XSHE"
    default_period: str = "day"


class ProviderPayload(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""
    is_active: bool = True
    purposes: list[str] = Field(default_factory=lambda: PURPOSES.copy())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _user_id(user: dict[str, Any] | None) -> int:
    return int(user["id"]) if user else 0


def optional_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    if not authorization:
        return None
    try:
        from app.auth.auth_router import get_current_user

        return get_current_user(authorization)
    except Exception:
        return None


@router.get("/user")
def get_user_settings(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user["id"],)).fetchone()
    return {
        "settings": dict(row) if row else {
            "theme": "black_gold",
            "default_model_provider": "deepseek",
            "default_symbol": "000001.XSHE",
            "default_period": "day",
        }
    }


@router.post("/user")
def save_user_settings(payload: UserSettingsPayload, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_settings
            (user_id, theme, default_model_provider, default_symbol, default_period, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                theme=excluded.theme,
                default_model_provider=excluded.default_model_provider,
                default_symbol=excluded.default_symbol,
                default_period=excluded.default_period,
                updated_at=excluded.updated_at
            """,
            (user["id"], payload.theme, payload.default_model_provider, payload.default_symbol, payload.default_period, now, now),
        )
    return {"success": True, "settings": payload.model_dump()}


@router.get("/model-providers")
def get_model_providers(user: dict[str, Any] | None = Depends(optional_current_user)) -> dict[str, Any]:
    uid = _user_id(user)
    with get_connection() as conn:
        provider_rows = conn.execute(
            """
            SELECT * FROM model_providers
            WHERE user_id IN (0, ?)
            ORDER BY user_id ASC, id ASC
            """,
            (uid,),
        ).fetchall()
        key_rows = conn.execute(
            """
            SELECT provider, is_active FROM api_keys
            WHERE user_id IN (0, ?)
            ORDER BY user_id ASC, id ASC
            """,
            (uid,),
        ).fetchall()
    provider_map = {(row["provider"], row["purpose"]): dict(row) for row in provider_rows}
    configured_keys = {row["provider"]: bool(row["is_active"]) for row in key_rows}
    items = []
    for provider in PROVIDERS:
        purposes = []
        for purpose in PURPOSES:
            row = provider_map.get((provider["provider"], purpose))
            purposes.append(
                {
                    "purpose": purpose,
                    "model": row["model"] if row else provider["default_model"],
                    "is_active": bool(row["is_active"]) if row else provider["provider"] == "deepseek",
                }
            )
        items.append(
            {
                **provider,
                "configured": bool(configured_keys.get(provider["provider"]) or os.getenv(f"{provider['provider'].upper()}_API_KEY")),
                "purposes": purposes,
            }
        )
    return {"items": items, "purposes": PURPOSES}


@router.post("/model-providers")
def save_model_provider(payload: ProviderPayload, user: dict[str, Any] | None = Depends(optional_current_user)) -> dict[str, Any]:
    uid = _user_id(user)
    now = _now()
    with get_connection() as conn:
        for purpose in payload.purposes or ["default"]:
            conn.execute(
                """
                INSERT INTO model_providers
                (user_id, provider, model, purpose, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider, purpose) DO UPDATE SET
                    model=excluded.model,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (uid, payload.provider, payload.model, purpose, int(payload.is_active), now, now),
            )
        if payload.api_key:
            conn.execute(
                """
                INSERT INTO api_keys
                (user_id, provider, encrypted_api_key, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    encrypted_api_key=excluded.encrypted_api_key,
                    is_active=1,
                    updated_at=excluded.updated_at
                """,
                (uid, payload.provider, encrypt_secret(payload.api_key), now, now),
            )
    return {"success": True, "provider": payload.provider, "configured": bool(payload.api_key)}


@router.post("/model-providers/test")
def test_model_provider(payload: ProviderPayload, user: dict[str, Any] | None = Depends(optional_current_user)) -> dict[str, Any]:
    api_key = payload.api_key or _stored_api_key(_user_id(user), payload.provider) or os.getenv(f"{payload.provider.upper()}_API_KEY", "")
    if payload.provider != "deepseek":
        return {"success": False, "message": "该供应商已预留配置入口，当前版本暂未接入真实测试。"}
    if not api_key:
        return {"success": False, "message": "DeepSeek API Key 未配置。"}
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": payload.model or "deepseek-chat",
                "messages": [{"role": "user", "content": "请回复：连接正常"}],
                "temperature": 0,
                "max_tokens": 16,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            return {"success": False, "message": f"连接失败：{response.status_code}"}
        return {"success": True, "message": "DeepSeek 连接正常。"}
    except Exception as exc:
        return {"success": False, "message": f"连接失败：{exc}"}


def _stored_api_key(user_id: int, provider: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT encrypted_api_key FROM api_keys
            WHERE user_id IN (0, ?) AND provider = ? AND is_active = 1
            ORDER BY user_id DESC, id DESC
            LIMIT 1
            """,
            (user_id, provider),
        ).fetchone()
    if not row:
        return ""
    try:
        return decrypt_secret(row["encrypted_api_key"])
    except Exception:
        return ""
