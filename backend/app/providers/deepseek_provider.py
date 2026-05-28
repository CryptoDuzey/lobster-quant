from __future__ import annotations

import os
from typing import Any

import requests

from app.auth.security import decrypt_secret
from app.db.database import get_connection
from app.providers.llm_provider import LLMProvider, LLMResponse


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self) -> None:
        stored_key = self._stored_api_key()
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or stored_key
        model = os.getenv("DEEPSEEK_MODEL", "").strip() or self._stored_model() or "deepseek-chat"
        super().__init__(
            model=model,
            enabled=bool(api_key),
        )
        self.api_key = api_key
        self.base_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")

    def _stored_api_key(self) -> str:
        try:
            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT encrypted_api_key FROM api_keys
                    WHERE provider = 'deepseek' AND is_active = 1
                    ORDER BY user_id DESC, id DESC
                    LIMIT 1
                    """,
                ).fetchone()
            if not row:
                return ""
            return decrypt_secret(row["encrypted_api_key"]).strip()
        except Exception:
            return ""

    def _stored_model(self) -> str:
        try:
            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT model FROM model_providers
                    WHERE provider = 'deepseek' AND is_active = 1
                    ORDER BY user_id DESC, id DESC
                    LIMIT 1
                    """,
                ).fetchone()
            return str(row["model"]).strip() if row and row["model"] else ""
        except Exception:
            return ""

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        timeout: int = 45,
    ) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("DeepSeek API Key 未配置")
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format
        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()
        return LLMResponse(
            content=raw["choices"][0]["message"]["content"],
            raw=raw,
            provider=self.name,
            model=self.model,
        )
