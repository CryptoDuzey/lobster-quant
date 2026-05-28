from __future__ import annotations

from app.agents.backtest_audit_agent import BacktestAuditAgent
from app.agents.decision_committee_agent import DecisionCommitteeAgent
from app.agents.market_watch_agent import MarketWatchAgent
from app.agents.strategy_debug_agent import StrategyDebugAgent
from app.agents.strategy_generation_agent import StrategyGenerationAgent


def get_agent(name: str):
    agents = {
        "market_watch": MarketWatchAgent,
        "decision_committee": DecisionCommitteeAgent,
        "strategy_generation": StrategyGenerationAgent,
        "strategy_debug": StrategyDebugAgent,
        "backtest_audit": BacktestAuditAgent,
    }
    return agents[name]()
