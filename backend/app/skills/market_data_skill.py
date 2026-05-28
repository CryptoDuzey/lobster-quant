from __future__ import annotations

from typing import Any

from app.data_providers.akshare_provider import normalize_symbol
from app.data_providers.provider_router import get_market_provider
from app.skills.base_skill import BaseSkill, SkillResult


class MarketDataSkill(BaseSkill):
    name = "market_data"
    description = "读取统一行情数据源中的K线和快照"
    permissions = ("READ_MARKET",)

    def run(self, **kwargs: Any) -> SkillResult:
        provider = get_market_provider()
        symbol = normalize_symbol(kwargs.get("symbol", "000001.XSHE"))
        period = kwargs.get("period", "day")
        start_date = kwargs.get("start_date", "2025-01-01")
        end_date = kwargs.get("end_date", "2026-05-23")
        bars, source = provider.get_bars(symbol, period, start_date, end_date, kwargs.get("adjust", "qfq"))
        quote, quote_source = provider.get_quote(symbol)
        return SkillResult(
            True,
            {
                "symbol": symbol,
                "name": provider.get_name(symbol),
                "period": period,
                "bars": [bar.to_dict() for bar in bars],
                "quote": quote,
                "source": source or quote_source,
            },
        )
