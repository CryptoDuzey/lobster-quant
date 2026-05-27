from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.skills import (
    BacktestSkill,
    ChartAnalysisSkill,
    MarketDataSkill,
    NewsFetchSkill,
    RiskCheckSkill,
    SentimentSkill,
    StrategyCodegenSkill,
    TechnicalIndicatorSkill,
)
from app.skills.base_skill import BaseSkill


@dataclass
class ToolDefinition:
    name: str
    description: str
    permissions: list[str]
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill:
        return self._skills[name]

    def list_tools(self) -> list[dict[str, Any]]:
        tools = [skill.metadata() for skill in self._skills.values()]
        tools.append(
            {
                "name": "live_trade",
                "description": "真实交易接口，当前阶段默认禁用。",
                "permissions": ["LIVE_TRADE_DISABLED"],
                "enabled": False,
            }
        )
        return tools


tool_registry = ToolRegistry()
for skill in [
    MarketDataSkill(),
    NewsFetchSkill(),
    TechnicalIndicatorSkill(),
    SentimentSkill(),
    RiskCheckSkill(),
    StrategyCodegenSkill(),
    BacktestSkill(),
    ChartAnalysisSkill(),
]:
    tool_registry.register(skill)
