from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.skills.technical_indicator_skill import TechnicalIndicatorSkill


class TechnicalAgent(BaseAgent):
    name = "technical_agent"
    description = "技术面分析师 Agent"
    permissions = ("READ_MARKET",)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = TechnicalIndicatorSkill().run(bars=payload.get("bars") or [])
        data = result.data if result.success else {"technical_view": result.message}
        self.log("technical_view", payload, data, "success" if result.success else "warning")
        return data
