from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.orchestration.audit_logger import audit_logger
from app.providers.provider_factory import get_llm_provider


class BaseAgent(ABC):
    name = "base_agent"
    description = ""
    permissions: tuple[str, ...] = ("READ_MARKET",)

    def __init__(self, provider_name: str | None = None) -> None:
        self.provider = get_llm_provider(provider_name)

    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def log(
        self,
        action: str,
        payload: dict[str, Any],
        result: dict[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        audit_logger.log(
            agent=self.name,
            action=action,
            input_summary={
                "symbol": payload.get("symbol"),
                "name": payload.get("name"),
                "period": payload.get("period"),
            },
            output_summary=result or {},
            status=status,
            permissions=list(self.permissions),
        )
