from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class MarketBar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
    ma20: float | None = None
    atr: float | None = None
    atr_upper: float | None = None
    atr_lower: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StockItem:
    symbol: str
    code: str
    name: str
    exchange: str
    type: str = "股票"
    pinyin: str = ""
    match_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "code": self.code,
            "name": self.name,
            "exchange": self.exchange,
            "type": self.type,
            "match_reason": self.match_reason,
        }


class MarketDataError(RuntimeError):
    pass


class EmptyMarketDataError(MarketDataError):
    pass
