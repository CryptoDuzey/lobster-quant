from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd


SUPPORTED_PERIODS = {"1m", "5m", "15m", "30m", "60m", "day", "1d"}
SYMBOL_RE = re.compile(r"^\d{6}\.(XSHE|XSHG)$")


@dataclass
class BacktestValidationError(Exception):
    error_code: str
    message: str
    diagnosis: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message,
            "diagnosis": self.diagnosis,
        }


class BacktestValidator:
    min_bars = 30

    def validate_request(self, request: Any) -> None:
        if not SYMBOL_RE.match(request.stock_id):
            raise BacktestValidationError(
                "INVALID_SYMBOL",
                "股票代码格式不正确，已停止回测。",
                {"symbol": request.stock_id},
            )
        if request.period not in SUPPORTED_PERIODS:
            raise BacktestValidationError(
                "UNSUPPORTED_PERIOD",
                "当前回测周期暂不支持，已停止回测。",
                {"period": request.period, "supported": sorted(SUPPORTED_PERIODS)},
            )
        if request.start_date >= request.end_date:
            raise BacktestValidationError(
                "INVALID_DATE_RANGE",
                "开始日期必须早于结束日期，已停止回测。",
                {"start_date": str(request.start_date), "end_date": str(request.end_date)},
            )
        params = request.params or {}
        for key in ["initial_cash", "commission", "slippage", "stamp_tax", "round_lot"]:
            if key not in params:
                continue
            try:
                value = float(params[key])
            except (TypeError, ValueError) as exc:
                raise BacktestValidationError(
                    "INVALID_COST_MODEL",
                    f"成本参数 {key} 不是有效数字，已停止回测。",
                    {"param": key, "value": params.get(key)},
                ) from exc
            if math.isnan(value) or math.isinf(value):
                raise BacktestValidationError(
                    "INVALID_COST_MODEL",
                    f"成本参数 {key} 不是有效数字，已停止回测。",
                    {"param": key, "value": params.get(key)},
                )

    def validate_bars(self, bars: list[dict[str, Any]], request: Any, data_source: str = "") -> list[str]:
        if not bars:
            raise BacktestValidationError(
                "EMPTY_MARKET_DATA",
                f"{request.stock_id} 在 {request.start_date} 至 {request.end_date} 区间未获取到有效行情数据，已停止回测。",
                {
                    "symbol": request.stock_id,
                    "start_date": str(request.start_date),
                    "end_date": str(request.end_date),
                    "data_source": data_source,
                },
            )

        frame = pd.DataFrame(bars)
        required = ["time", "open", "high", "low", "close"]
        missing = [field for field in required if field not in frame.columns]
        if missing:
            raise BacktestValidationError(
                "MISSING_BAR_FIELDS",
                f"行情字段缺失：{', '.join(missing)}，已停止回测。",
                {"missing": missing, "symbol": request.stock_id},
            )

        warnings: list[str] = []
        frame["timestamp"] = pd.to_datetime(frame["time"], errors="coerce")
        if frame["timestamp"].isna().any():
            raise BacktestValidationError(
                "INVALID_BAR_TIME",
                "行情时间字段存在无法解析的值，已停止回测。",
                {"symbol": request.stock_id},
            )
        if not frame["timestamp"].is_monotonic_increasing:
            raise BacktestValidationError(
                "BARS_NOT_SORTED",
                "行情数据不是按时间升序排列，已停止回测。",
                {"symbol": request.stock_id},
            )
        duplicated = int(frame["timestamp"].duplicated().sum())
        if duplicated:
            raise BacktestValidationError(
                "DUPLICATE_BARS",
                "行情数据存在重复日期或时间，已停止回测。",
                {"symbol": request.stock_id, "duplicates": duplicated},
            )
        for field_name in ["open", "high", "low", "close"]:
            series = pd.to_numeric(frame[field_name], errors="coerce")
            invalid_count = int(series.isna().sum() + (~series.apply(lambda value: math.isfinite(float(value)) if pd.notna(value) else False)).sum())
            if invalid_count:
                raise BacktestValidationError(
                    "INVALID_BAR_VALUE",
                    f"行情字段 {field_name} 存在 NaN 或 Inf，已停止回测。",
                    {"field": field_name, "invalid_count": invalid_count},
                )
        if len(frame) < self.min_bars:
            warnings.append(f"有效行情数据只有 {len(frame)} 条，样本较短，统计意义有限。")
        null_ratio = float(frame[["open", "high", "low", "close"]].isna().mean().mean())
        if null_ratio > 0.02:
            warnings.append(f"行情缺失比例约 {null_ratio:.2%}，请谨慎解读回测结果。")
        return warnings


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, pd.Timestamp)):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value
