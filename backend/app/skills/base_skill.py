from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)


class BaseSkill(ABC):
    name = "base_skill"
    description = ""
    permissions: tuple[str, ...] = ("READ_MARKET",)

    @abstractmethod
    def run(self, **kwargs: Any) -> SkillResult:
        raise NotImplementedError

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": list(self.permissions),
        }
