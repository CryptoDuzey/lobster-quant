from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.data.cache_service import MarketCacheService
from app.data_providers.akshare_provider import normalize_symbol
from app.data_providers.base import EmptyMarketDataError, MarketDataError
from app.data_providers.provider_router import get_market_provider


router = APIRouter(prefix="/api/v1/market", tags=["market"])
market_cache = MarketCacheService()


def _actual_range(bars: list[Any]) -> tuple[str, str]:
    if not bars:
        return "", ""
    first = bars[0].get("time", "") if isinstance(bars[0], dict) else getattr(bars[0], "time", "")
    last = bars[-1].get("time", "") if isinstance(bars[-1], dict) else getattr(bars[-1], "time", "")
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


def _bars_to_dicts(bars: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        rows.append(bar.to_dict() if hasattr(bar, "to_dict") else dict(bar))
    return rows


def _append_indicators(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    closes: list[float] = []
    ranges: list[float] = []
    previous_close: float | None = None
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        close = float(item.get("close") or 0)
        high = float(item.get("high") or close)
        low = float(item.get("low") or close)
        closes.append(close)
        true_range = max(high - low, abs(high - (previous_close or close)), abs(low - (previous_close or close)))
        ranges.append(true_range)
        previous_close = close
        ma_window = closes[-20:]
        atr_window = ranges[-14:]
        ma20 = sum(ma_window) / len(ma_window) if ma_window else close
        atr = sum(atr_window) / len(atr_window) if atr_window else 0
        item["ma20"] = round(ma20, 6)
        item["atr"] = round(atr, 6)
        item["atr_upper"] = round(ma20 + atr, 6)
        item["atr_lower"] = round(ma20 - atr, 6)
        enriched.append(item)
    return enriched


def _cache_covers_request(rows: list[dict[str, Any]], period: str, start_date: str, end_date: str) -> bool:
    if not rows:
        return False
    if period not in {"day", "1d"}:
        return len(rows) >= 2
    try:
        first = datetime.fromisoformat(str(rows[0]["time"])[:10])
        last = datetime.fromisoformat(str(rows[-1]["time"])[:10])
        requested_start = datetime.fromisoformat(start_date[:10])
        requested_end = datetime.fromisoformat(end_date[:10])
    except Exception:
        return False
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    effective_end = min(requested_end, today)
    return first <= requested_start + timedelta(days=10) and last >= effective_end - timedelta(days=10)


def _cached_market_payload(
    *,
    provider: Any,
    symbol: str,
    period: str,
    start_date: str,
    end_date: str,
    adjust: str,
    latency_ms: int,
    warning: str = "",
) -> dict[str, Any] | None:
    cached = market_cache.get_market_bars(symbol, period, adjust, start_date, end_date)
    if not _cache_covers_request(cached, period, start_date, end_date):
        return None
    rows = _append_indicators(cached)
    actual_start, actual_end = _actual_range(rows)
    source = rows[0].get("source") or "cache"
    data_warning = warning or _data_warning(period, start_date, rows)
    return {
        "symbol": symbol,
        "name": provider.get_name(symbol),
        "period": period,
        "requested_start": start_date,
        "requested_end": end_date,
        "actual_start": actual_start,
        "actual_end": actual_end,
        "bars_count": len(rows),
        "data_warning": data_warning,
        "source": f"{source}_cache",
        "cache_hit": True,
        "latency_ms": latency_ms,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bars": rows,
    }


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
        if period in {"day", "1d"}:
            cached_payload = _cached_market_payload(
                provider=provider,
                symbol=normalized_symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            if cached_payload:
                return cached_payload
        bars, source = provider.get_bars(normalized_symbol, period, start_date, end_date, adjust)
        rows = _bars_to_dicts(bars)
        market_cache.upsert_market_bars(normalized_symbol, period, adjust, rows, source)
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
            "cache_hit": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bars": rows,
        }
    except (ValueError, MarketDataError) as exc:
        try:
            normalized_symbol = normalize_symbol(symbol)
            fallback = _cached_market_payload(
                provider=provider,
                symbol=normalized_symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                latency_ms=0,
                warning=f"实时数据源暂时不可用，当前展示的是本地缓存的真实历史数据：{exc}",
            )
            if fallback:
                return fallback
        except Exception:
            pass
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
