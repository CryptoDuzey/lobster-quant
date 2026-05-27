from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.data.cache_service import BenchmarkCacheService
from app.data_providers.akshare_provider import no_proxy_env


BENCHMARK_CODE_MAP = {
    "CSI300": {
        "internal": "000300.XSHG",
        "akshare_index": "000300",
        "akshare_stock_zh_index_daily": "sh000300",
        "eastmoney": "000300",
        "eastmoney_secid": "1.000300",
        "display_name": "沪深300",
    },
    "SSE": {
        "internal": "000001.XSHG",
        "akshare_index": "000001",
        "akshare_stock_zh_index_daily": "sh000001",
        "eastmoney": "000001",
        "eastmoney_secid": "1.000001",
        "display_name": "上证指数",
    },
    "CSI500": {
        "internal": "000905.XSHG",
        "akshare_index": "000905",
        "akshare_stock_zh_index_daily": "sh000905",
        "eastmoney": "000905",
        "eastmoney_secid": "1.000905",
        "display_name": "中证500",
    },
}


@dataclass
class BenchmarkResult:
    symbol: str
    name: str
    bars: list[dict[str, Any]]
    source: str
    available: bool
    warnings: list[str]
    actual_start: str | None = None
    actual_end: str | None = None
    error: str | None = None


class BenchmarkService:
    default_key = "CSI300"
    default_symbol = BENCHMARK_CODE_MAP[default_key]["internal"]
    default_name = BENCHMARK_CODE_MAP[default_key]["display_name"]

    def __init__(self) -> None:
        self.cache = BenchmarkCacheService()

    def get_default_benchmark(self, start_date: str, end_date: str) -> BenchmarkResult:
        return self.get_benchmark(self.default_key, start_date, end_date)

    def get_benchmark(self, benchmark_key: str, start_date: str, end_date: str) -> BenchmarkResult:
        config = BENCHMARK_CODE_MAP.get(benchmark_key, BENCHMARK_CODE_MAP[self.default_key])
        internal_symbol = config["internal"]
        display_name = config["display_name"]
        warnings: list[str] = []

        cached, cache_source = self.cache.get_bars(internal_symbol, start_date, end_date)
        cached_valid, cached_reason = validate_benchmark_bars(cached)
        cached_covers, cached_coverage_reason = _covers_requested_range(cached, start_date, end_date)
        if cached and cached_valid and cached_covers:
            return BenchmarkResult(
                symbol=internal_symbol,
                name=display_name,
                bars=cached,
                source=f"{cache_source or 'cache'}_cache",
                available=True,
                warnings=[],
                actual_start=cached[0]["time"],
                actual_end=cached[-1]["time"],
            )
        if cached and not cached_valid:
            warnings.append(f"本地缓存基准数据无效，已尝试重新拉取：{cached_reason}")
        elif cached and not cached_covers:
            warnings.append(f"本地缓存基准数据不足，已尝试重新拉取：{cached_coverage_reason}")

        fetchers = [
            ("akshare_index_zh_a_hist", lambda: self._fetch_akshare_hist(config, start_date, end_date)),
            ("akshare_stock_zh_index_daily", lambda: self._fetch_akshare_index_daily(config, start_date, end_date)),
            ("eastmoney", lambda: self._fetch_eastmoney(config, start_date, end_date)),
        ]
        for source_name, fetcher in fetchers:
            try:
                bars = fetcher()
                bars_valid, bars_reason = validate_benchmark_bars(bars)
                bars_cover, bars_coverage_reason = _covers_requested_range(bars, start_date, end_date)
                if bars and bars_valid and bars_cover:
                    self.cache.upsert_bars(internal_symbol, bars, source_name)
                    return BenchmarkResult(
                        symbol=internal_symbol,
                        name=display_name,
                        bars=bars,
                        source=source_name,
                        available=True,
                        warnings=warnings,
                        actual_start=bars[0]["time"],
                        actual_end=bars[-1]["time"],
                    )
                reason = bars_reason if not bars_valid else bars_coverage_reason
                warnings.append(f"{source_name} 返回的基准数据无效：{reason}")
            except Exception as exc:
                warnings.append(f"{source_name} 获取失败：{exc}")

        error = "基准数据获取失败，Alpha/Beta 暂不可用"
        warnings.append(error)
        return BenchmarkResult(
            symbol=internal_symbol,
            name=display_name,
            bars=[],
            source="",
            available=False,
            warnings=warnings,
            error=error,
        )

    def get_benchmark_bars(self, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], list[str]]:
        result = self.get_default_benchmark(start_date, end_date)
        return result.bars, result.warnings

    def _fetch_akshare_hist(self, config: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.index_zh_a_hist(
                symbol=config["akshare_index"],
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
        return _normalize_frame(frame, start_date, end_date)

    def _fetch_akshare_index_daily(self, config: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.stock_zh_index_daily(symbol=config["akshare_stock_zh_index_daily"])
        return _normalize_frame(frame, start_date, end_date)

    def _fetch_eastmoney(self, config: dict[str, str], start_date: str, end_date: str) -> list[dict[str, Any]]:
        import requests

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": config["eastmoney_secid"],
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "0",
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
        }
        with no_proxy_env():
            response = requests.get(url, params=params, timeout=12)
        response.raise_for_status()
        payload = response.json()
        klines = ((payload.get("data") or {}).get("klines") or [])
        rows: list[dict[str, Any]] = []
        for item in klines:
            fields = str(item).split(",")
            if len(fields) < 7:
                continue
            rows.append(
                {
                    "time": fields[0],
                    "open": _safe_float(fields[1]),
                    "close": _safe_float(fields[2]),
                    "high": _safe_float(fields[3]),
                    "low": _safe_float(fields[4]),
                    "volume": _safe_float(fields[5]),
                    "amount": _safe_float(fields[6]),
                }
            )
        return _sort_and_filter_bars(rows, start_date, end_date)


def validate_benchmark_bars(bars: list[dict[str, Any]]) -> tuple[bool, str]:
    if not bars:
        return False, "基准数据为空"
    closes = [_safe_float(row.get("close")) for row in bars]
    closes = [value for value in closes if value is not None]
    if len(closes) < 2:
        return False, "基准数据少于 2 条"
    if max(closes) <= 0:
        return False, "基准收盘价异常"
    if abs(max(closes) - min(closes)) < 1e-8:
        return False, "基准收盘价为常数"
    return True, ""


def _covers_requested_range(bars: list[dict[str, Any]], start_date: str, end_date: str) -> tuple[bool, str]:
    if not bars:
        return False, "基准数据为空"
    try:
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        times = pd.to_datetime([row.get("time") for row in bars], errors="coerce").dropna()
    except Exception:
        return False, "基准日期无法解析"
    if len(times) < 2:
        return False, "基准日期少于 2 条"
    actual_start = times.min()
    actual_end = times.max()
    if actual_start > start + pd.Timedelta(days=7):
        return False, f"实际开始日期 {actual_start.strftime('%Y-%m-%d')} 晚于请求开始日期过多"
    if actual_end < end - pd.Timedelta(days=7):
        return False, f"实际结束日期 {actual_end.strftime('%Y-%m-%d')} 早于请求结束日期过多"
    return True, ""


def _normalize_frame(frame: Any, start_date: str, end_date: str) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    data = pd.DataFrame(frame).copy()
    column_map = {
        "日期": "time",
        "date": "time",
        "开盘": "open",
        "open": "open",
        "最高": "high",
        "high": "high",
        "最低": "low",
        "low": "low",
        "收盘": "close",
        "close": "close",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
    }
    data = data.rename(columns={key: value for key, value in column_map.items() if key in data.columns})
    if "time" not in data.columns:
        return []
    data["timestamp"] = pd.to_datetime(data["time"], errors="coerce")
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    data = data.dropna(subset=["timestamp"])
    data = data[(data["timestamp"] >= start) & (data["timestamp"] <= end)].sort_values("timestamp")
    rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        close = _safe_float(row.get("close"))
        if close is None:
            continue
        rows.append(
            {
                "time": row["timestamp"].strftime("%Y-%m-%d"),
                "open": _safe_float(row.get("open")) or close,
                "high": _safe_float(row.get("high")) or close,
                "low": _safe_float(row.get("low")) or close,
                "close": close,
                "volume": _safe_float(row.get("volume")),
                "amount": _safe_float(row.get("amount")),
            }
        )
    return rows


def _sort_and_filter_bars(rows: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    frame = frame[(frame["timestamp"] >= start) & (frame["timestamp"] <= end)].sort_values("timestamp")
    result: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        close = _safe_float(row.get("close"))
        if close is None:
            continue
        result.append(
            {
                "time": row["timestamp"].strftime("%Y-%m-%d"),
                "open": _safe_float(row.get("open")) or close,
                "high": _safe_float(row.get("high")) or close,
                "low": _safe_float(row.get("low")) or close,
                "close": close,
                "volume": _safe_float(row.get("volume")),
                "amount": _safe_float(row.get("amount")),
            }
        )
    return result


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return round(number, 6)
