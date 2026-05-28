from __future__ import annotations

import math
import os
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
import requests

from app.data_providers.base import EmptyMarketDataError, MarketBar, MarketDataError, StockItem


PERIOD_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "day": "daily",
    "1d": "daily",
}

COMMON_STOCKS = [
    StockItem("000001.XSHE", "000001", "平安银行", "深交所", pinyin="payh"),
    StockItem("601318.XSHG", "601318", "中国平安", "上交所", pinyin="zgpa"),
    StockItem("600519.XSHG", "600519", "贵州茅台", "上交所", pinyin="gzmt"),
    StockItem("000858.XSHE", "000858", "五粮液", "深交所", pinyin="wly"),
    StockItem("300750.XSHE", "300750", "宁德时代", "深交所", pinyin="ndsd"),
    StockItem("600036.XSHG", "600036", "招商银行", "上交所", pinyin="zsyh"),
    StockItem("000333.XSHE", "000333", "美的集团", "深交所", pinyin="mdjt"),
    StockItem("002594.XSHE", "002594", "比亚迪", "深交所", pinyin="byd"),
    StockItem("601398.XSHG", "601398", "工商银行", "上交所", pinyin="gsyh"),
    StockItem("601857.XSHG", "601857", "中国石油", "上交所", pinyin="zgsy"),
    StockItem("600028.XSHG", "600028", "中国石化", "上交所", pinyin="zgsh"),
    StockItem("601888.XSHG", "601888", "中国中免", "上交所", pinyin="zgzm"),
    StockItem("600030.XSHG", "600030", "中信证券", "上交所", pinyin="zxzq"),
    StockItem("688981.XSHG", "688981", "中芯国际", "上交所", pinyin="zxgj"),
    StockItem("000063.XSHE", "000063", "中兴通讯", "深交所", pinyin="zxtx"),
    StockItem("300124.XSHE", "300124", "汇川技术", "深交所", pinyin="hcjs"),
    StockItem("002230.XSHE", "002230", "科大讯飞", "深交所", pinyin="kdxf"),
    StockItem("603986.XSHG", "603986", "兆易创新", "上交所", pinyin="zycx"),
]


@contextmanager
def no_proxy_env():
    keys = [
        "NO_PROXY",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ]
    old_values = {key: os.environ.get(key) for key in keys}
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def normalize_symbol(symbol: str) -> str:
    value = (symbol or "").strip().upper()
    if not value:
        raise ValueError("股票代码不能为空")
    if value.endswith(".SH"):
        value = value[:-3] + ".XSHG"
    if value.endswith(".SZ"):
        value = value[:-3] + ".XSHE"
    if "." not in value and value.isdigit() and len(value) == 6:
        suffix = ".XSHG" if value.startswith(("6", "9")) else ".XSHE"
        value = value + suffix
    code, _, exchange = value.partition(".")
    if len(code) != 6 or not code.isdigit() or exchange not in {"XSHE", "XSHG"}:
        raise ValueError("股票格式不正确，请输入类似 000001、000001.XSHE 或 600519.XSHG")
    return value


def ak_code(symbol: str) -> str:
    return normalize_symbol(symbol).split(".", 1)[0]


def ak_market_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    code, exchange = normalized.split(".", 1)
    return f"sh{code}" if exchange == "XSHG" else f"sz{code}"


def exchange_name(symbol: str) -> str:
    return "上交所" if normalize_symbol(symbol).endswith(".XSHG") else "深交所"


def clean_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def first_existing(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _normalize_bars_frame(df: pd.DataFrame, period: str, start_date: str, end_date: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    frame = df.copy()
    rename_map = {
        "date": "time",
        "datetime": "time",
        "day": "time",
        "日期": "time",
        "时间": "time",
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
        "turnover": "amount",
    }
    frame = frame.rename(columns={column: rename_map.get(column, column) for column in frame.columns})
    frame = frame.loc[:, ~frame.columns.duplicated()]
    required = ["time", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise MarketDataError(f"行情字段缺失：{', '.join(missing)}")

    frame["timestamp"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame.sort_values("timestamp")

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    if period in {"day", "1d"} or len(str(end_date)) <= 10:
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    frame = frame[(frame["timestamp"] >= start) & (frame["timestamp"] <= end)]

    previous_close = frame["close"].shift(1).fillna(frame["close"])
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["ma20"] = frame["close"].rolling(20, min_periods=1).mean()
    frame["atr"] = true_range.rolling(14, min_periods=1).mean()
    frame["atr_upper"] = frame["ma20"] + frame["atr"]
    frame["atr_lower"] = frame["ma20"] - frame["atr"]
    return frame


def _frame_to_bars(frame: pd.DataFrame, period: str) -> list[MarketBar]:
    rows: list[MarketBar] = []
    for _, row in frame.iterrows():
        time_value = row["timestamp"].strftime("%Y-%m-%d") if period in {"day", "1d"} else row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        rows.append(
            MarketBar(
                time=time_value,
                open=clean_float(row["open"]) or 0,
                high=clean_float(row["high"]) or 0,
                low=clean_float(row["low"]) or 0,
                close=clean_float(row["close"]) or 0,
                volume=clean_float(row["volume"]) or 0,
                amount=clean_float(row.get("amount")),
                ma20=clean_float(row["ma20"]),
                atr=clean_float(row["atr"]),
                atr_upper=clean_float(row["atr_upper"]),
                atr_lower=clean_float(row["atr_lower"]),
            )
        )
    return rows


def _fetch_sina_minute_frame(symbol: str, period: str, timeout: int = 12) -> pd.DataFrame:
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
    response = requests.get(
        url,
        params={
            "symbol": ak_market_symbol(symbol),
            "scale": period,
            "ma": "no",
            "datalen": "1970",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    text = response.text
    data = json.loads(text.split("=(")[1].split(");")[0])
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data).iloc[:, :7]


def _eastmoney_secid(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    code, exchange = normalized.split(".", 1)
    market_code = "1" if exchange == "XSHG" else "0"
    return f"{market_code}.{code}"


def _fetch_eastmoney_quote(symbol: str, timeout: int = 8) -> dict[str, Any]:
    params = {
        "secid": _eastmoney_secid(symbol),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    last_error: Exception | None = None
    data: dict[str, Any] = {}
    for url in (
        "https://push2delay.eastmoney.com/api/qt/stock/get",
        "https://push2.eastmoney.com/api/qt/stock/get",
    ):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json().get("data") or {}
            if data:
                break
        except Exception as exc:
            last_error = exc
    if not data:
        if last_error:
            raise last_error
        raise EmptyMarketDataError(f"未获取到实时行情：{normalize_symbol(symbol)}")

    def scaled_price(field: str) -> float | None:
        value = clean_float(data.get(field))
        return round(value / 100, 6) if value is not None else None

    change = clean_float(data.get("f169"))
    change_pct = clean_float(data.get("f170"))
    return {
        "symbol": normalize_symbol(symbol),
        "name": data.get("f58") or ak_code(symbol),
        "price": scaled_price("f43"),
        "change": round(change / 100, 6) if change is not None else None,
        "change_pct": round(change_pct / 100, 6) if change_pct is not None else None,
        "open": scaled_price("f46"),
        "high": scaled_price("f44"),
        "low": scaled_price("f45"),
        "pre_close": scaled_price("f60"),
        "volume": clean_float(data.get("f47")),
        "amount": clean_float(data.get("f48")),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@lru_cache(maxsize=1)
def _stock_list() -> list[StockItem]:
    items = {item.symbol: item for item in COMMON_STOCKS}
    try:
        import akshare as ak

        with no_proxy_env():
            df = ak.stock_info_a_code_name()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                code = str(row.get("code") or row.get("代码") or "").zfill(6)
                name = str(row.get("name") or row.get("名称") or "")
                if len(code) != 6 or not name:
                    continue
                symbol = normalize_symbol(code)
                items.setdefault(symbol, StockItem(symbol, code, name, exchange_name(symbol)))
    except Exception:
        pass
    return list(items.values())


class AkshareProvider:
    name = "akshare"

    def search_stocks(self, keyword: str) -> list[StockItem]:
        key = (keyword or "").strip().lower()
        if not key:
            return [StockItem(**{**item.__dict__, "match_reason": "热门股票"}) for item in COMMON_STOCKS[:8]]
        normalized = ""
        try:
            normalized = normalize_symbol(key).lower()
        except Exception:
            normalized = key
        matches = []
        for item in _stock_list():
            haystacks = [item.symbol.lower(), item.code, item.name.lower(), item.pinyin.lower()]
            if any(key in haystack or normalized in haystack for haystack in haystacks):
                reason = "名称匹配"
                if key and (key in item.code or normalized == item.symbol.lower()):
                    reason = "代码匹配"
                elif key and item.pinyin and key in item.pinyin.lower():
                    reason = "拼音匹配"
                matches.append(StockItem(item.symbol, item.code, item.name, item.exchange, item.type, item.pinyin, reason))
        return matches[:20]

    def get_bars(self, symbol: str, period: str, start_date: str, end_date: str, adjust: str = "qfq") -> tuple[list[MarketBar], str]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise MarketDataError("当前 Python 环境缺少 akshare") from exc

        normalized_period = PERIOD_MAP.get(period)
        if normalized_period is None:
            raise MarketDataError("周期必须是 1m、5m、15m、30m、60m 或 day")

        code = ak_code(symbol)
        try:
            with no_proxy_env():
                if normalized_period == "daily":
                    try:
                        frame = ak.stock_zh_a_hist(
                            symbol=code,
                            period="daily",
                            start_date=start_date.replace("-", ""),
                            end_date=end_date.replace("-", ""),
                            adjust=adjust or "qfq",
                            timeout=10,
                        )
                        source = "akshare-eastmoney"
                    except Exception:
                        frame = ak.stock_zh_a_daily(
                            symbol=ak_market_symbol(symbol),
                            start_date=start_date.replace("-", ""),
                            end_date=end_date.replace("-", ""),
                            adjust=adjust or "qfq",
                        )
                        source = "akshare-sina"
                else:
                    try:
                        frame = _fetch_sina_minute_frame(symbol, normalized_period)
                        source = "sina-minute"
                    except Exception:
                        frame = ak.stock_zh_a_hist_min_em(
                            symbol=code,
                            start_date=f"{start_date} 09:30:00",
                            end_date=f"{end_date} 15:00:00",
                            period=normalized_period,
                            adjust="",
                        )
                        source = "akshare-eastmoney-minute"
        except Exception as exc:
            raise MarketDataError(f"数据源接口失败：{exc}") from exc

        normalized = _normalize_bars_frame(frame, period, start_date, end_date)
        bars = _frame_to_bars(normalized, period)
        if not bars:
            raise EmptyMarketDataError(f"当前周期暂无行情数据：{normalize_symbol(symbol)}")
        return bars, source

    def get_quote(self, symbol: str) -> tuple[dict[str, Any], str]:
        normalized_symbol = normalize_symbol(symbol)
        try:
            with no_proxy_env():
                quote = _fetch_eastmoney_quote(normalized_symbol)
            return quote, "eastmoney"
        except Exception:
            pass

        try:
            import akshare as ak
        except ImportError as exc:
            raise MarketDataError("当前 Python 环境缺少 akshare") from exc

        code = ak_code(normalized_symbol)
        try:
            with no_proxy_env():
                spot = ak.stock_zh_a_spot_em()
            if spot is None or spot.empty or "代码" not in spot.columns:
                raise EmptyMarketDataError(f"未获取到实时行情：{normalized_symbol}")
            row_frame = spot[spot["代码"].astype(str).str.zfill(6) == code]
            if row_frame.empty:
                raise EmptyMarketDataError(f"未获取到实时行情：{normalized_symbol}")
            row = row_frame.iloc[0]
            price = clean_float(first_existing(row, ["最新价", "price", "最新"]))
            pre_close = clean_float(first_existing(row, ["昨收", "pre_close"]))
            change = (price - pre_close) if price is not None and pre_close is not None else None
            return {
                "symbol": normalized_symbol,
                "name": first_existing(row, ["名称", "name"]) or code,
                "price": price,
                "change": clean_float(change),
                "change_pct": clean_float(first_existing(row, ["涨跌幅", "change_pct"])),
                "open": clean_float(first_existing(row, ["今开", "open"])),
                "high": clean_float(first_existing(row, ["最高", "high"])),
                "low": clean_float(first_existing(row, ["最低", "low"])),
                "pre_close": pre_close,
                "volume": clean_float(first_existing(row, ["成交量", "volume"])),
                "amount": clean_float(first_existing(row, ["成交额", "turnover", "amount"])),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, "eastmoney"
        except Exception:
            end = datetime.now().date()
            start = end - timedelta(days=45)
            bars, source = self.get_bars(normalized_symbol, "day", start.isoformat(), end.isoformat(), "qfq")
            latest = bars[-1]
            previous = bars[-2] if len(bars) > 1 else latest
            change = latest.close - previous.close
            change_pct = (change / previous.close * 100) if previous.close else 0
            return {
                "symbol": normalized_symbol,
                "name": self.get_name(normalized_symbol),
                "price": latest.close,
                "change": round(change, 6),
                "change_pct": round(change_pct, 6),
                "open": latest.open,
                "high": latest.high,
                "low": latest.low,
                "pre_close": previous.close,
                "volume": latest.volume,
                "amount": latest.amount,
                "timestamp": latest.time,
            }, source

    def get_name(self, symbol: str) -> str:
        normalized = normalize_symbol(symbol)
        for item in _stock_list():
            if item.symbol == normalized:
                return item.name
        return ak_code(normalized)
