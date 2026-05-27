from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from app.data.cache_service import FinancialFactorCacheService, MacroFactorCacheService
from app.data_providers.akshare_provider import ak_code, normalize_symbol, no_proxy_env


FINANCIAL_FACTOR_LABELS = {
    "roe": "净资产收益率(ROE)",
    "roa": "总资产报酬率(ROA)",
    "revenue_growth": "营业总收入增长率",
    "net_profit_growth": "归母净利润增长率",
    "debt_ratio": "资产负债率",
    "net_margin": "销售净利率",
    "cashflow_quality": "经营活动净现金/营业总收入",
    "eps": "基本每股收益",
    "bps": "每股净资产",
}

FINANCIAL_METRIC_ALIASES = {
    "roe": ("净资产收益率(ROE)", "净资产收益率_平均"),
    "roa": ("总资产报酬率(ROA)", "总资产报酬率"),
    "revenue_growth": ("营业总收入增长率",),
    "net_profit_growth": ("归属母公司净利润增长率",),
    "debt_ratio": ("资产负债率",),
    "net_margin": ("销售净利率",),
    "cashflow_quality": ("经营性现金净流量/营业总收入", "经营活动净现金/销售收入"),
    "eps": ("基本每股收益",),
    "bps": ("每股净资产",),
}

FUNDAMENTAL_FACTORS = set(FINANCIAL_FACTOR_LABELS)
MACRO_FACTORS = {"pmi", "cpi_yoy", "gdp_yoy", "lpr1y"}
FACTOR_DIRECTIONS = {
    "momentum_60": "higher",
    "ma_trend": "higher",
    "amount_20": "higher",
    "rsi_14": "higher",
    "low_volatility_60": "lower",
    "roe": "higher",
    "roa": "higher",
    "revenue_growth": "higher",
    "net_profit_growth": "higher",
    "debt_ratio": "lower",
    "net_margin": "higher",
    "cashflow_quality": "higher",
    "eps": "higher",
    "bps": "higher",
    "pmi": "higher",
    "cpi_yoy": "neutral",
    "gdp_yoy": "higher",
    "lpr1y": "lower",
}


@dataclass
class FactorValue:
    value: float | None
    source: str = ""
    report_date: str | None = None
    available_date: str | None = None
    warning: str | None = None


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def _report_available_date(report_date: str) -> str:
    timestamp = pd.to_datetime(report_date, errors="coerce")
    if pd.isna(timestamp):
        return report_date
    month_day = timestamp.strftime("%m%d")
    lag_days = 45
    if month_day == "0630":
        lag_days = 60
    elif month_day == "1231":
        lag_days = 120
    return (timestamp + pd.Timedelta(days=lag_days)).strftime("%Y-%m-%d")


def _parse_financial_abstract(frame: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    data = pd.DataFrame(frame).copy()
    if data.shape[1] < 3:
        return []
    metric_col = "指标" if "指标" in data.columns else data.columns[1]
    period_columns = [column for column in data.columns if re.fullmatch(r"\d{8}", str(column))]
    rows: list[dict[str, Any]] = []
    for factor_name, aliases in FINANCIAL_METRIC_ALIASES.items():
        matched = data[data[metric_col].astype(str).isin(aliases)]
        if matched.empty:
            continue
        metric_row = matched.iloc[0]
        for period in period_columns:
            value = _safe_float(metric_row.get(period))
            if value is None:
                continue
            report_date = pd.to_datetime(str(period), format="%Y%m%d", errors="coerce")
            if pd.isna(report_date):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "report_date": report_date.strftime("%Y-%m-%d"),
                    "available_date": _report_available_date(report_date.strftime("%Y-%m-%d")),
                    "factor_name": factor_name,
                    "factor_value": value,
                }
            )
    return rows


class FinancialFactorService:
    source = "akshare_stock_financial_abstract"

    def __init__(self) -> None:
        self.cache = FinancialFactorCacheService()
        self._loaded_symbols: set[str] = set()

    def ensure_symbol(self, symbol: str) -> list[str]:
        normalized = normalize_symbol(symbol)
        if normalized in self._loaded_symbols:
            return []
        cached = self.cache.get_factors(normalized)
        if cached:
            self._loaded_symbols.add(normalized)
            return []
        try:
            import akshare as ak

            with no_proxy_env():
                frame = ak.stock_financial_abstract(symbol=ak_code(normalized))
            rows = _parse_financial_abstract(frame, normalized)
            if not rows:
                return [f"{normalized} 财务摘要接口返回空数据。"]
            self.cache.upsert_factors(normalized, rows, self.source)
            self._loaded_symbols.add(normalized)
            return []
        except Exception as exc:
            return [f"{normalized} 财务因子获取失败：{exc}"]

    def get_asof(self, symbol: str, factor_name: str, as_of_date: str) -> FactorValue:
        normalized = normalize_symbol(symbol)
        warnings = self.ensure_symbol(normalized)
        if factor_name not in FUNDAMENTAL_FACTORS:
            return FactorValue(None, warning=f"未知财务因子：{factor_name}")
        row = self.cache.get_factor_asof(normalized, factor_name, as_of_date)
        if not row:
            warning = warnings[0] if warnings else f"{normalized} 在 {as_of_date} 之前没有可用的 {FINANCIAL_FACTOR_LABELS.get(factor_name, factor_name)}。"
            return FactorValue(None, warning=warning)
        return FactorValue(
            value=_safe_float(row.get("factor_value")),
            source=row.get("source") or self.source,
            report_date=row.get("report_date"),
            available_date=row.get("available_date"),
        )


def _month_end(text: str) -> str | None:
    match = re.search(r"(\d{4})年(\d{1,2})月份", str(text))
    if not match:
        return None
    return pd.Period(f"{int(match.group(1)):04d}-{int(match.group(2)):02d}", freq="M").end_time.strftime("%Y-%m-%d")


def _quarter_end(text: str) -> str | None:
    text = str(text)
    match = re.search(r"(\d{4})年第1-(\d)季度", text)
    if not match:
        match = re.search(r"(\d{4})年第(\d)季度", text)
    if not match:
        return None
    year = int(match.group(1))
    quarter = int(match.group(2))
    return pd.Period(f"{year}Q{quarter}", freq="Q").end_time.strftime("%Y-%m-%d")


class MacroFactorService:
    def __init__(self) -> None:
        self.cache = MacroFactorCacheService()
        self._loaded_indicators: set[str] = set()

    def ensure_indicator(self, indicator: str) -> list[str]:
        if indicator in self._loaded_indicators:
            return []
        cached = self.cache.get_indicator(indicator)
        if cached:
            self._loaded_indicators.add(indicator)
            return []
        fetchers = {
            "pmi": self._fetch_pmi,
            "cpi_yoy": self._fetch_cpi,
            "gdp_yoy": self._fetch_gdp,
            "lpr1y": self._fetch_lpr,
        }
        fetcher = fetchers.get(indicator)
        if not fetcher:
            return [f"未知宏观因子：{indicator}"]
        try:
            rows, source = fetcher()
            if not rows:
                return [f"{indicator} 宏观接口返回空数据。"]
            self.cache.upsert_indicator(indicator, rows, source)
            self._loaded_indicators.add(indicator)
            return []
        except Exception as exc:
            return [f"{indicator} 宏观因子获取失败：{exc}"]

    def get_asof(self, indicator: str, as_of_date: str) -> FactorValue:
        warnings = self.ensure_indicator(indicator)
        row = self.cache.get_asof(indicator, as_of_date)
        if not row:
            warning = warnings[0] if warnings else f"{as_of_date} 之前没有可用的 {indicator} 宏观数据。"
            return FactorValue(None, warning=warning)
        return FactorValue(value=_safe_float(row.get("value")), source=row.get("source") or "", report_date=row.get("time"))

    def get_context(self, as_of_date: str) -> dict[str, FactorValue]:
        return {indicator: self.get_asof(indicator, as_of_date) for indicator in MACRO_FACTORS}

    def _fetch_pmi(self) -> tuple[list[dict[str, Any]], str]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.macro_china_pmi_yearly()
        rows: list[dict[str, Any]] = []
        for _, row in pd.DataFrame(frame).iterrows():
            if str(row.get("商品")) != "中国官方制造业PMI":
                continue
            value = _safe_float(row.get("今值"))
            time_value = pd.to_datetime(row.get("日期"), errors="coerce")
            if value is not None and not pd.isna(time_value):
                rows.append({"time": time_value.strftime("%Y-%m-%d"), "value": value})
        return rows, "akshare_macro_china_pmi_yearly"

    def _fetch_cpi(self) -> tuple[list[dict[str, Any]], str]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.macro_china_cpi()
        rows: list[dict[str, Any]] = []
        for _, row in pd.DataFrame(frame).iterrows():
            time_value = _month_end(str(row.get("月份")))
            value = _safe_float(row.get("全国-同比增长"))
            if time_value and value is not None:
                rows.append({"time": time_value, "value": value})
        return rows, "akshare_macro_china_cpi"

    def _fetch_gdp(self) -> tuple[list[dict[str, Any]], str]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.macro_china_gdp()
        rows: list[dict[str, Any]] = []
        for _, row in pd.DataFrame(frame).iterrows():
            time_value = _quarter_end(str(row.get("季度")))
            value = _safe_float(row.get("国内生产总值-同比增长"))
            if time_value and value is not None:
                rows.append({"time": time_value, "value": value})
        return rows, "akshare_macro_china_gdp"

    def _fetch_lpr(self) -> tuple[list[dict[str, Any]], str]:
        import akshare as ak

        with no_proxy_env():
            frame = ak.macro_china_lpr()
        rows: list[dict[str, Any]] = []
        for _, row in pd.DataFrame(frame).iterrows():
            time_value = pd.to_datetime(row.get("TRADE_DATE"), errors="coerce")
            value = _safe_float(row.get("LPR1Y") if row.get("LPR1Y") is not None else row.get("RATE_1"))
            if value is not None and not pd.isna(time_value):
                rows.append(
                    {
                        "time": time_value.strftime("%Y-%m-%d"),
                        "value": value,
                        "extra_json": json.dumps({"lpr5y": _safe_float(row.get("LPR5Y"))}, ensure_ascii=False),
                    }
                )
        return rows, "akshare_macro_china_lpr"
