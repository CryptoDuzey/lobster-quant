from __future__ import annotations

from typing import Any

from app.agents.market_watch_agent import MarketWatchAgent


class DecisionCommitteeAgent(MarketWatchAgent):
    name = "decision_committee_agent"
    description = "AI投研委员会 Agent，汇总技术、消息、风控、多空观点"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return super().run(payload)
