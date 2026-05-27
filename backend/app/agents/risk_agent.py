from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.skills.risk_check_skill import RiskCheckSkill


class RiskAgent(BaseAgent):
    name = "risk_agent"
    description = "风控经理 Agent"
    permissions = ("READ_MARKET", "RUN_BACKTEST")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = RiskCheckSkill().run(
            bars=payload.get("bars") or [],
            metrics=payload.get("metrics") or {},
            trades=payload.get("trades") or [],
        )
        data = result.data if result.success else {"risk_view": result.message, "risk_level": "未知"}
        self.log("risk_view", payload, {"risk_level": data.get("risk_level")})
        return data
