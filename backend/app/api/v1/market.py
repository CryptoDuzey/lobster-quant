from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.data_providers.akshare_provider import normalize_symbol
from app.data_providers.base import EmptyMarketDataError, MarketDataError
from app.data_providers.provider_router import get_market_provider


router = APIRouter(prefix="/api/v1/market", tags=["market"])


def _actual_range(bars: list[Any]) -> tuple[str, str]:
    if not bars:
        return "", ""
    first = getattr(bars[0], "time", "") or ""
    last = getattr(bars[-1], "time", "") or ""
    return str(first), str(last)


def _data_warning(period: str, start_date: str, bars: list[Any]) -> str:
    if not bars or period in {"day", "1d"}:
        return ""
    try:
        requested = datetime.fromisoformat(str(start_date)[:10])
        actual = datetime.fromisoformat(str(getattr(bars[0], "time", ""))[:10])
    except Exception:
        return ""
    if (actual - requested).days > 14:
        return f"当前分钟线数据源只返回 {actual.strftime('%Y-%m-%d')} 之后的真实数据，早于该日期的分钟K线未返回，系统未使用补假数据。"
    return ""


def _http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    if isinstance(exc, EmptyMarketDataError):
        return HTTPException(status_code=404, detail=message)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=503, detail=message)


@router.get("/search")
def search_stocks(keyword: str = Query("")) -> dict[str, Any]:
    provider = get_market_provider()
    started = time.perf_counter()
    items = provider.search_stocks(keyword)
    if keyword.strip() and not items:
        raise HTTPException(status_code=404, detail="未找到相关股票，请尝试输入股票代码或完整股票名称")
    return {
        "items": [item.to_dict() for item in items],
        "source": provider.name,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/bars")
def market_bars(
    symbol: str = Query("000001.XSHE"),
    period: str = Query("day"),
    start_date: str = Query("2025-01-01"),
    end_date: str = Query("2026-03-01"),
    adjust: str = Query("qfq"),
) -> dict[str, Any]:
    provider = get_market_provider()
    try:
        started = time.perf_counter()
        normalized_symbol = normalize_symbol(symbol)
        bars, source = provider.get_bars(normalized_symbol, period, start_date, end_date, adjust)
        actual_start, actual_end = _actual_range(bars)
        return {
            "symbol": normalized_symbol,
            "name": provider.get_name(normalized_symbol),
            "period": period,
            "requested_start": start_date,
            "requested_end": end_date,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "bars_count": len(bars),
            "data_warning": _data_warning(period, start_date, bars),
            "source": source,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bars": [bar.to_dict() for bar in bars],
        }
    except (ValueError, MarketDataError) as exc:
        raise _http_error(exc) from exc


@router.get("/quote")
def market_quote(symbol: str = Query("000001.XSHE")) -> dict[str, Any]:
    provider = get_market_provider()
    try:
        started = time.perf_counter()
        normalized_symbol = normalize_symbol(symbol)
        quote, source = provider.get_quote(normalized_symbol)
        return {
            **quote,
            "source": source,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": quote.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except (ValueError, MarketDataError) as exc:
        raise _http_error(exc) from exc
