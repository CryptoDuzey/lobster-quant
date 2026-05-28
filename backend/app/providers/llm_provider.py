from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    content: str
    raw: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""


class LLMProvider(ABC):
    name = "base"

    def __init__(self, model: str = "", enabled: bool = True) -> None:
        self.model = model
        self.enabled = enabled

    @property
    def available(self) -> bool:
        return bool(self.enabled)

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        timeout: int = 45,
    ) -> LLMResponse:
        raise NotImplementedError

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        timeout: int = 45,
    ) -> dict[str, Any]:
        import json
        import re

        response = self.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))
