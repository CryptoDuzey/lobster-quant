# coding: utf-8
from __future__ import annotations

import ast
import asyncio
import json
import math
import os
import pickle
import re
import shutil
import sys
import tempfile
import textwrap
import time
import uuid
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any

import pandas as pd
try:
    import talib  # noqa: F401
except Exception:
    talib = None  # type: ignore[assignment]

from fastapi import APIRouter, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.backtest.backtest_validator import BacktestValidationError, BacktestValidator
from app.backtest.benchmark_service import BenchmarkService
from app.backtest.factor_backtester import run_factor_selection_backtest
from app.backtest.performance_metrics import (
    build_equity_curve,
    build_equity_curve_from_portfolio,
    build_standard_curves,
    compute_metrics,
)
from app.backtest.result_auditor import BacktestResultAuditor
from app.backtest.result_normalizer import make_backtest_id, safe_json_response, stable_hash
from app.backtest.snapshot_service import SnapshotService
from app.data_providers.base import EmptyMarketDataError, MarketDataError
from app.data_providers.provider_router import get_market_provider
from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

DEFAULT_STARTING_CASH = 1_000_000
DEFAULT_BACKTEST_TIMEOUT_SECONDS = int(os.getenv("RQALPHA_BACKTEST_TIMEOUT", "300"))
DEFAULT_LIVE_DATA_TIMEOUT_SECONDS = int(os.getenv("LIVE_DATA_TIMEOUT_SECONDS", "3"))
DEFAULT_LIVE_DATA_RETRIES = int(os.getenv("LIVE_DATA_RETRIES", "3"))
STOCK_ID_PATTERN = re.compile(r"^\d{6}\.(XSHE|XSHG)$")
ALLOWED_LOGIC_NAMES = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ma20",
    "atr",
    "atr_ma20",
    "volume_ma20",
    "ma5",
    "ma10",
    "ma30",
    "ma60",
    "rsi",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "cci",
    "drawdown",
    "cash",
    "position_quantity",
    "closable",
    "cost_basis",
    "stop_loss_price",
    "macd",
    "macd_signal",
    "macd_hist",
}
DYNAMIC_LOGIC_NAME_PATTERN = re.compile(r"^(ma|volume_ma|atr_ma|high_max|low_min|return_|rsi)\d{1,3}$")
ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UAdd,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


class LogicValidationError(ValueError):
    pass


def validate_logic_expression(expression: str) -> None:
    if not expression or not expression.strip():
        raise LogicValidationError("策略条件不能为空。")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise LogicValidationError(f"策略条件语法不正确：{exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise LogicValidationError("策略条件只支持数字、变量、四则运算、比较和 and/or/not 组合。")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_LOGIC_NAMES and not DYNAMIC_LOGIC_NAME_PATTERN.match(node.id):
            allowed = "、".join(sorted(ALLOWED_LOGIC_NAMES))
            raise LogicValidationError(f"策略条件里出现了未知变量：{node.id}。可用变量：{allowed}，以及 maN / volume_maN / atr_maN / high_maxN / low_minN / return_N / rsiN。")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise LogicValidationError("策略条件里只能直接填写数字或布尔值。")

    compile(tree, "<strategy-logic>", "eval")


def extract_logic_names(*expressions: str) -> set[str]:
    names: set[str] = set()
    for expression in expressions:
        if not expression:
            continue
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
    return names


def dynamic_logic_names(*expressions: str) -> list[str]:
    names = [name for name in extract_logic_names(*expressions) if DYNAMIC_LOGIC_NAME_PATTERN.match(name)]
    return sorted(names)


def logic_history_count(*expressions: str, minimum: int = 80) -> int:
    windows = [minimum]
    for name in dynamic_logic_names(*expressions):
        match = re.search(r"(\d{1,3})$", name)
        if match:
            windows.append(int(match.group(1)) + 5)
    return max(windows)


class BacktestRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    mode: str = "single_stock"
    stock_id: str = Field(
        ...,
        validation_alias=AliasChoices("stock_id", "symbol"),
        examples=["000001.XSHE", "600519.XSHG"],
    )
    start_date: date = Field(..., examples=["2024-01-01"])
    end_date: date = Field(..., examples=["2024-12-31"])
    buy_logic: str = Field(
        ...,
        validation_alias=AliasChoices("buy_logic", "buy_idea"),
        examples=["close > ma20 + 2 * atr"],
    )
    sell_logic: str = Field(
        ...,
        validation_alias=AliasChoices("sell_logic", "sell_idea"),
        examples=["close < ma20 - 2 * atr"],
    )
    risk_idea: str = ""
    period: str = "day"
    strategy_name: str = "龙虾量化策略"
    rules: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    atr_period: int = Field(14, ge=2, le=120)
    stop_loss_multiplier: float = Field(2.0, gt=0, le=20)
    starting_cash: float = Field(DEFAULT_STARTING_CASH, gt=0)
    commission: float = Field(0.0003, ge=0)
    slippage: float = Field(0.0005, ge=0)
    stamp_tax: float = Field(0.001, ge=0)
    round_lot: int = Field(100, ge=1)
    t_plus_one: bool = True
    execution_time: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_structured_rules(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        params = data.get("params") or {}
        if data.get("mode") in {"factor_selection", "stock_pool"} or (isinstance(params, dict) and params.get("strategy_mode") == "factor_selection"):
            data.setdefault("symbol", "000001.XSHE")
            data["buy_logic"] = "close > ma20"
            data["sell_logic"] = "close < ma20"
        rules = data.get("rules") or {}

        def first_expression(group_name: str) -> str:
            group = rules.get(group_name) or []
            if isinstance(group, list):
                expressions = []
                for item in group:
                    if isinstance(item, dict):
                        value = item.get("expression")
                    else:
                        value = str(item)
                    if value:
                        expressions.append(str(value).strip())
                return " and ".join(f"({value})" for value in expressions if value)
            return ""

        if rules and not data.get("buy_logic") and not data.get("buy_idea"):
            data["buy_logic"] = first_expression("buy_rules") or "close > ma20"
        if rules and not data.get("sell_logic") and not data.get("sell_idea"):
            sell_logic = first_expression("sell_rules") or "close < ma20"
            risk_logic = first_expression("risk_rules")
            data["sell_logic"] = f"({sell_logic}) or ({risk_logic})" if risk_logic else sell_logic
        if isinstance(params, dict):
            if "initial_cash" in params:
                data["starting_cash"] = params["initial_cash"]
            if "commission" in params:
                data["commission"] = params["commission"]
            if "slippage" in params:
                data["slippage"] = params["slippage"]
            if "stamp_tax" in params:
                data["stamp_tax"] = params["stamp_tax"]
            if "round_lot" in params:
                data["round_lot"] = params["round_lot"]
            if "t_plus_one" in params:
                data["t_plus_one"] = params["t_plus_one"]
            if "atr_window" in params:
                data["atr_period"] = params["atr_window"]
            if "execution_time" in params:
                data["execution_time"] = params["execution_time"]
        return data

    @field_validator("stock_id")
    @classmethod
    def validate_stock_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not STOCK_ID_PATTERN.match(normalized):
            raise ValueError("股票代码格式不正确，请使用类似 000001.XSHE 或 600519.XSHG 的格式。")
        return normalized

    @field_validator("buy_logic", "sell_logic")
    @classmethod
    def validate_logic(cls, value: str) -> str:
        expression = value.strip()
        try:
            validate_logic_expression(expression)
        except LogicValidationError as exc:
            raise ValueError(str(exc)) from exc
        return expression

    @field_validator("execution_time")
    @classmethod
    def normalize_execution_time(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        text = str(value).strip().replace("：", ":")
        match = re.match(r"^([01]?\d|2[0-3]):([0-5]?\d)(?::([0-5]?\d))?$", text)
        if not match:
            raise ValueError("执行时间格式不正确，请使用 09:31 或 09:31:00。")
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3) or 0)
        return f"{hour:02d}:{minute:02d}:{second:02d}"

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestRequest":
        if self.start_date >= self.end_date:
            raise ValueError("开始日期必须早于结束日期。")
        return self


def generate_strategy_code(request: BacktestRequest) -> str:
    stock_id = json.dumps(request.stock_id, ensure_ascii=False)
    buy_logic = json.dumps(request.buy_logic, ensure_ascii=False)
    sell_logic = json.dumps(request.sell_logic, ensure_ascii=False)
    signal_frequency = json.dumps(_signal_frequency(request.period), ensure_ascii=False)
    execution_time_value = request.execution_time if _engine_frequency(request.period, request.execution_time) == "1m" else None
    execution_time = repr(execution_time_value)
    atr_period = int(request.atr_period)
    stop_loss_multiplier = float(request.stop_loss_multiplier)
    dynamic_names = dynamic_logic_names(request.buy_logic, request.sell_logic)
    dynamic_names_json = json.dumps(dynamic_names, ensure_ascii=False)
    history_count = max(atr_period + 1, logic_history_count(request.buy_logic, request.sell_logic))

    strategy_code = f"""
# coding: utf-8
import ast
import math

import numpy as np
import pandas as pd

try:
    import talib
except Exception:
    talib = None

from rqalpha.api import history_bars, order_shares


STOCK = {stock_id}
BUY_LOGIC = {buy_logic}
SELL_LOGIC = {sell_logic}
ATR_PERIOD = {atr_period}
STOP_LOSS_MULTIPLIER = {stop_loss_multiplier}
HISTORY_COUNT = {history_count}
DYNAMIC_NAMES = {dynamic_names_json}
SIGNAL_FREQUENCY = {signal_frequency}
EXECUTION_TIME = {execution_time}
ALLOWED_NAMES = {{
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ma20",
    "atr",
    "atr_ma20",
    "volume_ma20",
    "ma5",
    "ma10",
    "ma30",
    "ma60",
    "rsi",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "cci",
    "drawdown",
    "cash",
    "position_quantity",
    "closable",
    "cost_basis",
    "stop_loss_price",
    "macd",
    "macd_signal",
    "macd_hist",
}}
ALLOWED_NAMES.update(DYNAMIC_NAMES)
ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UAdd,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def init(context):
    context.stock = STOCK
    context.buy_logic = BUY_LOGIC
    context.sell_logic = SELL_LOGIC
    context.compiled_buy_logic = _compile_logic(BUY_LOGIC)
    context.compiled_sell_logic = _compile_logic(SELL_LOGIC)


def _compile_logic(expression):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RuntimeError("策略条件语法不正确：" + exc.msg)

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise RuntimeError("策略条件只支持数字、变量、四则运算、比较和 and/or/not 组合。")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise RuntimeError("策略条件里出现了未知变量：" + node.id)
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise RuntimeError("策略条件里只能直接填写数字或布尔值。")
    return compile(tree, "<strategy-logic>", "eval")


def _safe_eval(compiled_expression, values):
    return bool(eval(compiled_expression, {{"__builtins__": {{}}}}, values))


def _as_float(value, default=0.0):
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _history_column(bars, field):
    try:
        return np.asarray(bars[field], dtype=float)
    except Exception:
        index_map = {{"open": 0, "high": 1, "low": 2, "close": 3, "volume": 4}}
        return np.asarray(bars[:, index_map[field]], dtype=float)


def _fallback_atr(high, low, close, period):
    high_s = pd.Series(high, dtype="float64")
    low_s = pd.Series(low, dtype="float64")
    close_s = pd.Series(close, dtype="float64")
    prev_close = close_s.shift(1)
    true_range = pd.concat(
        [
            high_s - low_s,
            (high_s - prev_close).abs(),
            (low_s - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(true_range.rolling(period).mean().iloc[-1])


def _rsi(close_s, period):
    delta = close_s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])


def _dynamic_indicator_values(name, close_s, high_s, low_s, volume_s, atr_series):
    try:
        if name.startswith("volume_ma"):
            window = int(name.replace("volume_ma", ""))
            return float(volume_s.rolling(window).mean().iloc[-1])
        if name.startswith("atr_ma"):
            window = int(name.replace("atr_ma", ""))
            return float(pd.Series(atr_series, dtype="float64").rolling(window, min_periods=1).mean().iloc[-1])
        if name.startswith("high_max"):
            window = int(name.replace("high_max", ""))
            return float(high_s.shift(1).rolling(window).max().iloc[-1])
        if name.startswith("low_min"):
            window = int(name.replace("low_min", ""))
            return float(low_s.shift(1).rolling(window).min().iloc[-1])
        if name.startswith("return_"):
            window = int(name.replace("return_", ""))
            base = float(close_s.shift(window).iloc[-1])
            return float(close_s.iloc[-1] / base - 1) if base else np.nan
        if name.startswith("rsi") and name != "rsi":
            window = int(name.replace("rsi", ""))
            return _rsi(close_s, window)
        if name.startswith("ma"):
            window = int(name.replace("ma", ""))
            return float(close_s.rolling(window).mean().iloc[-1])
    except Exception:
        return np.nan
    return np.nan


def _parse_bar_datetime(value):
    if value is None:
        return None
    try:
        text = str(int(value))
        if len(text) >= 14:
            return pd.to_datetime(text[:14], format="%Y%m%d%H%M%S", errors="coerce")
        if len(text) >= 8:
            return pd.to_datetime(text[:8], format="%Y%m%d", errors="coerce")
    except Exception:
        pass
    return pd.to_datetime(value, errors="coerce")


def _current_bar_datetime(context, bar_dict, stock):
    try:
        now = getattr(context, "now", None)
        if now is not None:
            return pd.to_datetime(now, errors="coerce")
    except Exception:
        pass
    try:
        bar = bar_dict[stock]
        for field in ("datetime", "date", "trading_datetime"):
            value = getattr(bar, field, None)
            if value is not None:
                parsed = _parse_bar_datetime(value)
                if parsed is not None and not pd.isna(parsed):
                    return parsed
    except Exception:
        pass
    return None


def _is_scheduled_time(context, bar_dict, stock):
    if not EXECUTION_TIME:
        return True
    try:
        current_dt = _current_bar_datetime(context, bar_dict, stock)
        return current_dt is not None and not pd.isna(current_dt) and current_dt.strftime("%H:%M:%S") == EXECUTION_TIME
    except Exception:
        return False


def _indicators(stock):
    bars = history_bars(
        stock,
        HISTORY_COUNT,
        SIGNAL_FREQUENCY,
        fields=["open", "high", "low", "close", "volume"],
        skip_suspended=True,
        include_now=True,
    )
    if bars is None or len(bars) < HISTORY_COUNT:
        return None

    open_values = _history_column(bars, "open")
    high_values = _history_column(bars, "high")
    low_values = _history_column(bars, "low")
    close_values = _history_column(bars, "close")
    volume_values = _history_column(bars, "volume")

    close_s = pd.Series(close_values, dtype="float64")
    high_s = pd.Series(high_values, dtype="float64")
    low_s = pd.Series(low_values, dtype="float64")
    volume_s = pd.Series(volume_values, dtype="float64")

    if talib is not None:
        atr_series = talib.ATR(high_values, low_values, close_values, timeperiod=ATR_PERIOD)
        atr_value = float(atr_series[-1])
        ma20_value = float(talib.SMA(close_values, timeperiod=20)[-1])
        ma5_value = float(talib.SMA(close_values, timeperiod=5)[-1])
        ma10_value = float(talib.SMA(close_values, timeperiod=10)[-1])
        ma30_value = float(talib.SMA(close_values, timeperiod=30)[-1])
        ma60_value = float(talib.SMA(close_values, timeperiod=60)[-1])
        rsi_value = float(talib.RSI(close_values, timeperiod=14)[-1])
        bb_upper, bb_mid, bb_lower = talib.BBANDS(close_values, timeperiod=20, nbdevup=2, nbdevdn=2)
        bb_upper_value = float(bb_upper[-1])
        bb_mid_value = float(bb_mid[-1])
        bb_lower_value = float(bb_lower[-1])
        cci_value = float(talib.CCI(high_values, low_values, close_values, timeperiod=20)[-1])
        macd_line, macd_signal_line, macd_hist_line = talib.MACD(close_values, fastperiod=12, slowperiod=26, signalperiod=9)
        macd_value = float(macd_line[-1])
        macd_signal_value = float(macd_signal_line[-1])
        macd_hist_value = float(macd_hist_line[-1])
    else:
        atr_value = _fallback_atr(high_values, low_values, close_values, ATR_PERIOD)
        ma20_value = float(close_s.rolling(20).mean().iloc[-1])
        ma5_value = float(close_s.rolling(5).mean().iloc[-1])
        ma10_value = float(close_s.rolling(10).mean().iloc[-1])
        ma30_value = float(close_s.rolling(30).mean().iloc[-1])
        ma60_value = float(close_s.rolling(60).mean().iloc[-1])
        rsi_value = _rsi(close_s, 14)
        bb_mid_series = close_s.rolling(20).mean()
        bb_std = close_s.rolling(20).std(ddof=0)
        bb_mid_value = float(bb_mid_series.iloc[-1])
        bb_upper_value = float((bb_mid_series + 2 * bb_std).iloc[-1])
        bb_lower_value = float((bb_mid_series - 2 * bb_std).iloc[-1])
        typical_price = (high_s + low_s + close_s) / 3
        cci_ma = typical_price.rolling(20).mean()
        mean_dev = typical_price.rolling(20).apply(lambda x: float(np.mean(np.abs(x - np.mean(x)))), raw=True)
        cci_value = float(((typical_price - cci_ma) / (0.015 * mean_dev.replace(0, np.nan))).fillna(0).iloc[-1])
        atr_series = pd.Series(
            [
                max(
                    high_values[i] - low_values[i],
                    abs(high_values[i] - close_values[i - 1]) if i > 0 else high_values[i] - low_values[i],
                    abs(low_values[i] - close_values[i - 1]) if i > 0 else high_values[i] - low_values[i],
                )
                for i in range(len(close_values))
            ],
            dtype="float64",
        ).rolling(ATR_PERIOD).mean().to_numpy()
        ema12 = close_s.ewm(span=12, adjust=False).mean()
        ema26 = close_s.ewm(span=26, adjust=False).mean()
        macd_series = ema12 - ema26
        macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
        macd_value = float(macd_series.iloc[-1])
        macd_signal_value = float(macd_signal_series.iloc[-1])
        macd_hist_value = float((macd_series - macd_signal_series).iloc[-1])

    current_close = float(close_values[-1])
    atr_ma20_value = float(pd.Series(atr_series, dtype="float64").rolling(20, min_periods=1).mean().iloc[-1])
    volume_ma20_value = float(volume_s.rolling(20, min_periods=1).mean().iloc[-1])
    required_values = [
        atr_value,
        ma20_value,
        ma5_value,
        ma10_value,
        ma30_value,
        ma60_value,
        rsi_value,
        bb_mid_value,
        bb_upper_value,
        bb_lower_value,
        cci_value,
        current_close,
        macd_value,
        macd_signal_value,
        macd_hist_value,
    ]
    dynamic_values = {{
        name: _dynamic_indicator_values(name, close_s, high_s, low_s, volume_s, atr_series)
        for name in DYNAMIC_NAMES
    }}
    required_values.extend(dynamic_values.values())
    if any(math.isnan(v) or math.isinf(v) for v in required_values):
        return None

    values = {{
        "open": float(open_values[-1]),
        "high": float(high_values[-1]),
        "low": float(low_values[-1]),
        "close": current_close,
        "volume": float(volume_values[-1]),
        "ma20": ma20_value,
        "ma5": ma5_value,
        "ma10": ma10_value,
        "ma30": ma30_value,
        "ma60": ma60_value,
        "atr": atr_value,
        "atr_ma20": atr_ma20_value,
        "volume_ma20": volume_ma20_value,
        "rsi": rsi_value,
        "bb_mid": bb_mid_value,
        "bb_upper": bb_upper_value,
        "bb_lower": bb_lower_value,
        "cci": cci_value,
        "macd": macd_value,
        "macd_signal": macd_signal_value,
        "macd_hist": macd_hist_value,
    }}
    values.update(dynamic_values)
    return values


def handle_bar(context, bar_dict):
    stock = context.stock
    if not _is_scheduled_time(context, bar_dict, stock):
        return
    values = _indicators(stock)
    if values is None:
        return

    position_proxy = context.portfolio.positions[stock]
    # rqalpha 的股票持仓在新版本中通常包在 PositionProxy.long 里。
    # 如果直接读 proxy.quantity，会得到 0，导致卖出信号触发后也无法平仓。
    position = getattr(position_proxy, "long", position_proxy)
    quantity = int(getattr(position, "quantity", 0) or 0)
    closable = int(getattr(position, "closable", 0) or 0)
    cash = _as_float(getattr(context.portfolio, "cash", 0.0))
    cost_basis = _as_float(getattr(position, "avg_price", 0.0))
    stop_loss_price = cost_basis - STOP_LOSS_MULTIPLIER * values["atr"] if cost_basis > 0 else 0.0
    drawdown = max(0.0, (cost_basis - values["close"]) / cost_basis) if cost_basis > 0 else 0.0

    values.update(
        {{
            "cash": cash,
            "position_quantity": quantity,
            "closable": closable,
            "cost_basis": cost_basis,
            "stop_loss_price": stop_loss_price,
            "drawdown": drawdown,
        }}
    )

    buy_signal = _safe_eval(context.compiled_buy_logic, values)
    sell_signal = _safe_eval(context.compiled_sell_logic, values)
    stop_loss_signal = quantity > 0 and cost_basis > 0 and values["close"] <= stop_loss_price

    if quantity > 0 and closable > 0 and (sell_signal or stop_loss_signal):
        sell_amount = int(closable // 100 * 100)
        if sell_amount >= 100:
            order_shares(stock, -sell_amount)
        return

    if quantity == 0 and buy_signal:
        buy_amount = int(cash / values["close"] // 100 * 100)
        if buy_amount >= 100:
            order_shares(stock, buy_amount)
"""
    return textwrap.dedent(strategy_code).strip() + "\n"


LIVE_RQALPHA_RUNNER_TEMPLATE = r'''
# coding: utf-8
from __future__ import annotations

import contextlib
import json
import math
import os
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd

from rqalpha import main as rqalpha_main
from rqalpha.const import INSTRUMENT_TYPE, MARKET, TRADING_CALENDAR_TYPE
from rqalpha.data.base_data_source import BaseDataSource
from rqalpha.interface import ExchangeRate
from rqalpha.model.instrument import Instrument
from rqalpha.utils.config import parse_config
from rqalpha.utils.datetime_func import convert_date_to_int
from rqalpha.utils.functools import clear_all_cached_functions


BAR_FIELDS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "total_turnover",
    "limit_up",
    "limit_down",
    "open_interest",
    "settlement",
    "prev_settlement",
]
FLOAT_BAR_FIELDS = [field for field in BAR_FIELDS if field != "datetime"]
YIELD_TENORS = [
    "0S",
    "1M",
    "2M",
    "3M",
    "6M",
    "9M",
    "1Y",
    "2Y",
    "3Y",
    "4Y",
    "5Y",
    "6Y",
    "7Y",
    "8Y",
    "9Y",
    "10Y",
    "15Y",
    "20Y",
    "30Y",
    "40Y",
    "50Y",
]


@contextlib.contextmanager
def requests_timeout(seconds: int):
    try:
        import requests
    except Exception:
        yield
        return

    original = requests.sessions.Session.request

    def request_with_timeout(self, method, url, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return original(self, method, url, **kwargs)

    requests.sessions.Session.request = request_with_timeout
    try:
        yield
    finally:
        requests.sessions.Session.request = original


class LiveStockDataSource(BaseDataSource):
    def __init__(
        self,
        order_book_ids: Sequence[str],
        start_date: Union[str, date],
        end_date: Union[str, date],
        timeout_seconds: int = 3,
        retries: int = 3,
        adjust: str = "qfq",
        provider_url: Optional[str] = None,
        lookback_days: int = 500,
    ) -> None:
        self.order_book_ids = sorted(set(order_book_ids))
        self.start_date = pd.Timestamp(start_date).date()
        self.end_date = pd.Timestamp(end_date).date()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.retries = max(1, int(retries))
        self.adjust = adjust
        self.provider_url = provider_url.rstrip("/") if provider_url else None
        self.lookback_days = max(120, int(lookback_days))
        self._bars_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._instrument_cache: dict[str, Instrument] = {}
        self._calendar = pd.DatetimeIndex([])

        for order_book_id in self.order_book_ids:
            self._ensure_bars(order_book_id, "1d")
        self._refresh_calendar_from_cache()

    def _order_book_id(self, instrument_or_id: Any) -> str:
        return getattr(instrument_or_id, "order_book_id", instrument_or_id)

    def _akshare_symbol(self, order_book_id: str) -> str:
        return order_book_id.split(".", 1)[0]

    def _exchange(self, order_book_id: str) -> str:
        return order_book_id.split(".", 1)[1]

    def _akshare_market_symbol(self, order_book_id: str) -> str:
        prefix = "sh" if self._exchange(order_book_id) == "XSHG" else "sz"
        return f"{prefix}{self._akshare_symbol(order_book_id)}"

    def _board_type(self, order_book_id: str) -> str:
        code = self._akshare_symbol(order_book_id)
        if code.startswith("688"):
            return "KSH"
        if code.startswith(("8", "4", "9")):
            return "BJS"
        if code.startswith(("300", "301")):
            return "GEM"
        return "MainBoard"

    def _instrument(self, order_book_id: str) -> Instrument:
        if order_book_id not in self._instrument_cache:
            symbol = self._akshare_symbol(order_book_id)
            self._instrument_cache[order_book_id] = Instrument(
                {
                    "order_book_id": order_book_id,
                    "symbol": symbol,
                    "abbrev_symbol": symbol,
                    "type": "CS",
                    "round_lot": 100,
                    "listed_date": "1990-01-01",
                    "de_listed_date": "2999-12-31",
                    "exchange": self._exchange(order_book_id),
                    "board_type": self._board_type(order_book_id),
                    "status": "Active",
                    "special_type": "Normal",
                    "market_tplus": 1,
                    "trading_code": symbol,
                },
                market=MARKET.CN,
            )
        return self._instrument_cache[order_book_id]

    def _run_with_timeout(self, func):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(func)
        try:
            return future.result(timeout=max(self.timeout_seconds * 4, self.timeout_seconds + 8))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _fetch_with_retry(self, cache_key: tuple[str, str], fetcher):
        if cache_key in self._bars_cache:
            return self._bars_cache[cache_key]

        last_error: Optional[BaseException] = None
        for attempt in range(self.retries):
            try:
                with requests_timeout(self.timeout_seconds):
                    df = self._run_with_timeout(fetcher)
                if df is None or df.empty:
                    raise RuntimeError("行情接口返回了空数据")
                self._bars_cache[cache_key] = df
                return df
            except FutureTimeoutError as exc:
                last_error = RuntimeError(f"行情接口超过 {self.timeout_seconds} 秒仍未返回")
            except Exception as exc:
                last_error = exc
            time.sleep(min(0.2 * (attempt + 1), 1.0))

        if cache_key in self._bars_cache:
            return self._bars_cache[cache_key]
        raise RuntimeError(f"实时行情拉取失败：{last_error}")

    def _fetch_from_provider_url(self, order_book_id: str, frequency: str) -> pd.DataFrame:
        import requests

        response = requests.get(
            f"{self.provider_url}/api/v1/stock/history",
            params={
                "symbol": self._akshare_symbol(order_book_id),
                "order_book_id": order_book_id,
                "frequency": frequency,
                "start_date": (self.start_date - timedelta(days=self.lookback_days)).isoformat(),
                "end_date": self.end_date.isoformat(),
                "adjust": self.adjust,
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        return pd.DataFrame(rows)

    def _fetch_from_akshare(self, order_book_id: str, frequency: str) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("当前 Python 环境缺少 akshare，请先安装 akshare。") from exc

        symbol = self._akshare_symbol(order_book_id)
        market_symbol = self._akshare_market_symbol(order_book_id)
        start = (self.start_date - timedelta(days=self.lookback_days)).strftime("%Y%m%d")
        end = self.end_date.strftime("%Y%m%d")
        errors = []

        if frequency == "1d":
            try:
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust=self.adjust,
                )
                if df is not None and not df.empty:
                    return df
                errors.append("东方财富日线接口返回空数据")
            except Exception as exc:
                errors.append(f"东方财富日线接口失败：{exc}")

            try:
                df = ak.stock_zh_a_daily(
                    symbol=market_symbol,
                    start_date=start,
                    end_date=end,
                    adjust=self.adjust,
                )
                if df is not None and not df.empty:
                    return df
                errors.append("备用日线接口返回空数据")
            except Exception as exc:
                errors.append(f"备用日线接口失败：{exc}")

            raise RuntimeError("；".join(errors))

        start_dt = f"{(self.start_date - timedelta(days=10)).isoformat()} 09:30:00"
        end_dt = f"{self.end_date.isoformat()} 15:00:00"
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period="1",
                start_date=start_dt,
                end_date=end_dt,
                adjust=self.adjust,
            )
            if df is not None and not df.empty:
                return df
            errors.append("东方财富分钟线接口返回空数据")
        except Exception as exc:
            errors.append(f"东方财富分钟线接口失败：{exc}")

        try:
            df = ak.stock_zh_a_minute(symbol=market_symbol, period="1", adjust=self.adjust)
            if df is not None and not df.empty:
                return df
            errors.append("备用分钟线接口返回空数据")
        except Exception as exc:
            errors.append(f"备用分钟线接口失败：{exc}")

        raise RuntimeError("；".join(errors))

    def _raw_fetch(self, order_book_id: str, frequency: str) -> pd.DataFrame:
        if self.provider_url:
            return self._fetch_from_provider_url(order_book_id, frequency)
        return self._fetch_from_akshare(order_book_id, frequency)

    def _ensure_bars(self, order_book_id: str, frequency: str) -> pd.DataFrame:
        cache_key = (order_book_id, frequency)

        def fetcher():
            raw = self._raw_fetch(order_book_id, frequency)
            return self._normalize_bars(raw, frequency)

        return self._fetch_with_retry(cache_key, fetcher)

    def _normalize_bars(self, raw: pd.DataFrame, frequency: str) -> pd.DataFrame:
        df = raw.copy()
        df.columns = [str(col).strip() for col in df.columns]
        rename_map = {
            "日期": "datetime",
            "时间": "datetime",
            "date": "datetime",
            "day": "datetime",
            "time": "datetime",
            "datetime": "datetime",
            "开盘": "open",
            "open": "open",
            "收盘": "close",
            "close": "close",
            "最高": "high",
            "high": "high",
            "最低": "low",
            "low": "low",
            "成交量": "volume",
            "volume": "volume",
            "成交额": "total_turnover",
            "amount": "total_turnover",
            "turnover": "total_turnover",
        }
        df = df.rename(columns={col: rename_map[col] for col in df.columns if col in rename_map})
        df = df.loc[:, ~df.columns.duplicated()]
        required = {"datetime", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise RuntimeError(f"行情字段缺失：{sorted(missing)}")

        df["datetime"] = pd.to_datetime(df["datetime"])
        for field in ["open", "high", "low", "close", "volume", "total_turnover"]:
            if field not in df.columns:
                df[field] = 0.0
            df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0.0)

        if "成交量" in raw.columns:
            df["volume"] = df["volume"] * 100.0

        df = df.sort_values("datetime").drop_duplicates("datetime", keep="last")
        if frequency == "1d":
            df["date_key"] = df["datetime"].dt.normalize()
            df["datetime_int"] = df["date_key"].dt.strftime("%Y%m%d").astype(np.int64)
        else:
            df["date_key"] = df["datetime"]
            df["datetime_int"] = df["datetime"].dt.strftime("%Y%m%d%H%M%S").astype(np.int64)

        prev_close = df["close"].shift(1).fillna(df["close"])
        df["limit_up"] = (prev_close * 1.1).round(2)
        df["limit_down"] = (prev_close * 0.9).round(2)
        df["open_interest"] = 0.0
        df["settlement"] = df["close"]
        df["prev_settlement"] = prev_close
        df = df.set_index("date_key", drop=False).sort_index()
        return df[["datetime", "datetime_int", *FLOAT_BAR_FIELDS]]

    def _refresh_calendar_from_cache(self) -> None:
        calendars = []
        for (order_book_id, frequency), bars in self._bars_cache.items():
            if frequency == "1d" and not bars.empty:
                calendars.append(pd.DatetimeIndex(bars.index.normalize()))
        if calendars:
            merged = calendars[0]
            for calendar in calendars[1:]:
                merged = merged.union(calendar)
            self._calendar = merged.sort_values().unique()
        else:
            self._calendar = pd.date_range(self.start_date, self.end_date, freq="B")

    def get_instruments(
        self,
        id_or_syms: Optional[Iterable[str]] = None,
        types: Optional[Iterable[INSTRUMENT_TYPE]] = None,
    ) -> Iterable[Instrument]:
        if types is not None and INSTRUMENT_TYPE.CS not in set(types):
            return []

        ids = list(id_or_syms) if id_or_syms is not None else self.order_book_ids
        result = []
        for item in ids:
            order_book_id = str(item).upper()
            if "." not in order_book_id and len(order_book_id) == 6:
                for suffix in ("XSHE", "XSHG"):
                    candidate = f"{order_book_id}.{suffix}"
                    if candidate in self.order_book_ids:
                        order_book_id = candidate
                        break
            if order_book_id in self.order_book_ids:
                result.append(self._instrument(order_book_id))
        return result

    def get_trading_calendars(self):
        if self._calendar.empty:
            self._refresh_calendar_from_cache()
        return {TRADING_CALENDAR_TYPE.CN_STOCK: self._calendar}

    def available_data_range(self, frequency):
        bars = [
            df
            for (order_book_id, cache_frequency), df in self._bars_cache.items()
            if cache_frequency == "1d" and not df.empty
        ]
        if not bars:
            return self.start_date, self.end_date
        min_date = min(df.index.min().date() for df in bars)
        max_date = max(df.index.max().date() for df in bars)
        return min_date, max_date

    def _row_to_bar(self, row: pd.Series) -> dict[str, Any]:
        data = {"datetime": int(row["datetime_int"])}
        for field in FLOAT_BAR_FIELDS:
            data[field] = float(row.get(field, np.nan))
        return data

    def get_bar(self, instrument, dt, frequency):
        order_book_id = self._order_book_id(instrument)
        if dt is None:
            return None
        bars = self._ensure_bars(order_book_id, frequency)
        key = pd.Timestamp(dt).normalize() if frequency == "1d" else pd.Timestamp(dt)
        if key not in bars.index:
            return None
        row = bars.loc[key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        return self._row_to_bar(row)

    def get_open_auction_bar(self, instrument, dt):
        bar = self.get_bar(instrument, dt, "1d")
        if bar is None:
            return {field: np.nan for field in ["datetime", "open", "limit_up", "limit_down", "volume", "total_turnover", "last"]}
        return {
            "datetime": bar["datetime"],
            "open": bar["open"],
            "limit_up": bar["limit_up"],
            "limit_down": bar["limit_down"],
            "volume": bar["volume"],
            "total_turnover": bar["total_turnover"],
            "last": bar["open"],
        }

    def get_open_auction_volume(self, instrument, dt):
        bar = self.get_open_auction_bar(instrument, dt)
        return bar["volume"]

    def history_bars(
        self,
        instrument,
        bar_count,
        frequency,
        fields,
        dt,
        skip_suspended=True,
        include_now=False,
        adjust_type="pre",
        adjust_orig=None,
    ):
        order_book_id = self._order_book_id(instrument)
        bars = self._ensure_bars(order_book_id, frequency)
        if bars.empty:
            return None

        if frequency == "1d":
            key = pd.Timestamp(dt).normalize()
            timestamp = pd.Timestamp(dt)
            if timestamp.time() != dt_time(0, 0) and timestamp.time() < dt_time(15, 0):
                filtered = bars[bars.index < key]
            else:
                filtered = bars[bars.index <= key]
        else:
            key = pd.Timestamp(dt)
            filtered = bars[bars.index <= key] if include_now else bars[bars.index < key]

        if skip_suspended:
            filtered = filtered[filtered["volume"] > 0]
        if bar_count is not None:
            filtered = filtered.tail(int(bar_count))

        requested_fields = BAR_FIELDS if fields is None else fields
        single_field = isinstance(requested_fields, str)
        if single_field:
            requested_fields = [requested_fields]

        records = np.empty(
            len(filtered),
            dtype=[
                (field, "<i8" if field == "datetime" else "<f8")
                for field in requested_fields
            ],
        )
        for field in requested_fields:
            if field == "datetime":
                records[field] = filtered["datetime_int"].astype(np.int64).to_numpy()
            elif field in filtered.columns:
                records[field] = filtered[field].astype(float).to_numpy()
            else:
                records[field] = np.nan

        return records[requested_fields[0]] if single_field else records

    def get_yield_curve(self, start_date, end_date, tenor=None):
        index = pd.date_range(start_date, end_date, freq="D")
        columns = tenor if tenor is not None else YIELD_TENORS
        if isinstance(columns, str):
            columns = [columns]
        return pd.DataFrame(0.03, index=index, columns=list(columns))

    def get_dividend(self, instrument):
        return None

    def get_split(self, instrument):
        return None

    def get_share_transformation(self, order_book_id):
        return None

    def get_settle_price(self, instrument, date):
        bar = self.get_bar(instrument, date, "1d")
        return np.nan if bar is None else bar["settlement"]

    def current_snapshot(self, instrument, frequency, dt):
        bar_frequency = frequency or "1d"
        bar = self.get_bar(instrument, dt, bar_frequency)
        if bar is None:
            return None
        snapshot = dict(bar)
        snapshot["last"] = bar["close"]
        snapshot["prev_close"] = bar["prev_settlement"]
        return snapshot

    def get_trading_minutes_for(self, instrument, trading_dt):
        day = pd.Timestamp(trading_dt).date()
        morning = pd.date_range(
            datetime.combine(day, dt_time(9, 31)),
            datetime.combine(day, dt_time(11, 30)),
            freq="min",
        )
        afternoon = pd.date_range(
            datetime.combine(day, dt_time(13, 1)),
            datetime.combine(day, dt_time(15, 0)),
            freq="min",
        )
        return [item.to_pydatetime() for item in morning.append(afternoon)]

    def history_ticks(self, instrument, count, dt):
        raise NotImplementedError("实时数据源暂不提供 tick 数据。")

    def get_futures_trading_parameters(self, instrument, dt):
        raise NotImplementedError("实时数据源只支持 A 股股票。")

    def get_merge_ticks(self, order_book_id_list, trading_date, last_dt=None):
        raise NotImplementedError("实时数据源暂不提供合并 tick 数据。")

    def get_algo_bar(self, id_or_ins, start_min, end_min, dt):
        return None

    def get_exchange_rate(self, trading_date, local, settlement=MARKET.CN):
        return ExchangeRate(1, 1, 1, 1, 1, 1)

    def is_suspended(self, order_book_id: str, dates: Sequence[Any]):
        bars = self._ensure_bars(order_book_id, "1d")
        result = []
        for item in dates:
            key = pd.Timestamp(item).normalize()
            if key not in bars.index:
                result.append(True)
                continue
            row = bars.loc[key]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            result.append(float(row.get("volume", 0.0)) <= 0)
        return result

    def is_st_stock(self, order_book_id: str, dates: Sequence[Any]):
        return [False] * len(dates)


def _safe_float(value):
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def _format_date(value):
    if value is None:
        return None
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _has_intraday_time(value):
    if value is None:
        return False
    try:
        timestamp = pd.to_datetime(value)
        if pd.isna(timestamp):
            return False
        return timestamp.time() != dt_time(0, 0)
    except Exception:
        return False


def _format_datetime(value, default_time="09:31:00"):
    if value is None:
        return None
    try:
        timestamp = pd.to_datetime(value)
        if pd.isna(timestamp):
            return str(value)
        if timestamp.time() == dt_time(0, 0):
            return f"{timestamp.strftime('%Y-%m-%d')} {default_time}"
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        text = str(value)
        if len(text) == 10:
            return f"{text} {default_time}"
        return text


def _execution_phase(value):
    formatted = _format_datetime(value)
    if not formatted or len(formatted) < 19:
        return "盘中运行"
    clock = formatted[11:19]
    if clock < "09:30:00":
        return "盘前运行"
    if clock >= "15:00:00":
        return "日线收盘撮合"
    return "盘中运行"


def _format_runner_trades(trades):
    if trades is None:
        return []
    trades_df = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame(trades)
    if trades_df.empty:
        return []
    if "trading_datetime" not in trades_df.columns and "datetime" not in trades_df.columns and isinstance(trades_df.index, pd.DatetimeIndex):
        trades_df = trades_df.reset_index()
        trades_df = trades_df.rename(columns={trades_df.columns[0]: "trading_datetime"})
    else:
        trades_df = trades_df.reset_index(drop=True)

    normalized = []
    for _, trade in trades_df.iterrows():
        raw_time = trade.get("trading_datetime") or trade.get("datetime")
        side = str(trade.get("side", "")).upper()
        if "BUY" in side:
            action = "BUY"
        elif "SELL" in side:
            action = "SELL"
        else:
            action = side
        normalized.append(
            {
                "date": _format_date(raw_time),
                "time": _format_datetime(raw_time),
                "execution_time": _format_datetime(raw_time),
                "execution_phase": _execution_phase(raw_time),
                "time_source": "rqalpha_trading_datetime" if _has_intraday_time(raw_time) else "daily_bar_execution_slot",
                "time_note": "日线回测按盘中撮合时点展示，非分钟线逐笔行情。",
                "order_id": str(trade.get("order_id", "")),
                "action": action,
                "price": _safe_float(trade.get("last_price")),
                "amount": int(trade.get("last_quantity", 0) or 0),
                "transaction_cost": _safe_float(trade.get("transaction_cost")),
            }
        )
    return normalized


def _format_runner_portfolio(portfolio):
    if portfolio is None:
        return []
    portfolio_df = portfolio.copy() if isinstance(portfolio, pd.DataFrame) else pd.DataFrame(portfolio)
    if portfolio_df.empty:
        return []
    if "date" not in portfolio_df.columns:
        portfolio_df = portfolio_df.reset_index()
        if "date" not in portfolio_df.columns:
            portfolio_df = portfolio_df.rename(columns={portfolio_df.columns[0]: "date"})

    rows = []
    for _, row in portfolio_df.reset_index(drop=True).iterrows():
        total_value = row.get("total_value")
        unit_net_value = row.get("unit_net_value")
        if total_value is None and unit_net_value is None:
            continue
        rows.append(
            {
                "time": _format_datetime(row.get("date")),
                "portfolio_value": _safe_float(total_value),
                "unit_net_value": _safe_float(unit_net_value),
                "cash": _safe_float(row.get("cash")),
                "market_value": _safe_float(row.get("market_value")),
            }
        )
    return [row for row in rows if row["time"] and row["portfolio_value"] is not None]


def _format_runner_chart_data(bars, start_date, end_date, atr_period):
    if bars is None:
        return []
    df = bars.copy() if isinstance(bars, pd.DataFrame) else pd.DataFrame(bars)
    if df.empty:
        return []

    df = df.reset_index(drop=True)
    df["date_key"] = pd.to_datetime(df["datetime"]).dt.normalize()
    for field in ["open", "high", "low", "close", "volume"]:
        df[field] = pd.to_numeric(df[field], errors="coerce")

    prev_close = df["close"].shift(1).fillna(df["close"])
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ma20"] = df["close"].rolling(20, min_periods=1).mean()
    df["atr"] = true_range.rolling(int(atr_period), min_periods=1).mean()
    df["atr_upper"] = df["ma20"] + df["atr"]
    df["atr_lower"] = df["ma20"] - df["atr"]

    start_key = pd.Timestamp(start_date).normalize()
    end_key = pd.Timestamp(end_date).normalize()
    visible = df[(df["date_key"] >= start_key) & (df["date_key"] <= end_key)].copy()

    rows = []
    for _, row in visible.iterrows():
        rows.append(
            {
                "time": row["date_key"].strftime("%Y-%m-%d"),
                "open": _safe_float(row["open"]),
                "high": _safe_float(row["high"]),
                "low": _safe_float(row["low"]),
                "close": _safe_float(row["close"]),
                "volume": _safe_float(row["volume"]),
                "ma20": _safe_float(row["ma20"]),
                "atr": _safe_float(row["atr"]),
                "atr_upper": _safe_float(row["atr_upper"]),
                "atr_lower": _safe_float(row["atr_lower"]),
            }
        )
    return rows


def _format_runner_result(result, chart_data=None):
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    trades = result.get("trades") if isinstance(result, dict) else None
    portfolio = result.get("portfolio") if isinstance(result, dict) else None
    return {
        "success": True,
        "message": "回测完成。",
        "statistics": {
            "total_returns": _safe_float(summary.get("total_returns")),
            "annualized_returns": _safe_float(summary.get("annualized_returns")),
            "max_drawdown": _safe_float(summary.get("max_drawdown")),
            "sharpe_ratio": _safe_float(summary.get("sharpe")),
            "volatility": _safe_float(summary.get("volatility")),
            "turnover": _safe_float(summary.get("turnover")),
        },
        "trades": _format_runner_trades(trades),
        "portfolio_curve": _format_runner_portfolio(portfolio),
        "chart_data": chart_data or [],
    }


def run_live_rqalpha(strategy_source: str, runner_request: dict[str, Any], output_file: str, strategy_file: str) -> None:
    live_source = LiveStockDataSource(
        order_book_ids=[runner_request["stock_id"]],
        start_date=runner_request["start_date"],
        end_date=runner_request["end_date"],
        timeout_seconds=runner_request["timeout_seconds"],
        retries=runner_request["retries"],
        adjust=runner_request["adjust"],
        provider_url=runner_request.get("provider_url"),
    )
    config_dict = {
        "base": {
            "strategy_file": strategy_file,
            "start_date": runner_request["start_date"],
            "end_date": runner_request["end_date"],
            "frequency": runner_request["engine_frequency"],
            "run_type": "b",
            "accounts": {"stock": runner_request["starting_cash"]},
            "persist": False,
        },
        "extra": {
            "log_level": "error",
            "locale": "cn",
        },
        "mod": {
            "sys_progress": {"enabled": False},
            "sys_accounts": {
                "enabled": True,
                "stock_t1": True,
                "validate_stock_position": True,
            },
            "sys_simulation": {
                "enabled": True,
                "matching_type": "current_bar",
                "slippage_model": "PriceRatioSlippage",
                "slippage": runner_request["slippage"],
                "volume_limit": True,
                "volume_percent": 0.25,
                "inactive_limit": True,
            },
            "sys_transaction_cost": {
                "enabled": True,
                "stock_commission_multiplier": runner_request["commission_multiplier"],
                "stock_min_commission": 5,
                "tax_multiplier": runner_request["tax_multiplier"],
            },
            "sys_analyser": {
                "enabled": True,
                "record": True,
                "output_file": output_file,
            },
        },
    }

    config = parse_config(config_dict, source_code=strategy_source)
    config.data_source = live_source

    def build_live_data_source(base_config):
        return config.data_source

    rqalpha_main.BaseDataSource = build_live_data_source
    clear_all_cached_functions()
    result = rqalpha_main.run(config, source_code=strategy_source)
    if isinstance(result, dict) and "sys_analyser" in result:
        result = result["sys_analyser"]
    chart_data = _format_runner_chart_data(
        live_source._ensure_bars(runner_request["stock_id"], "1d"),
        runner_request["start_date"],
        runner_request["end_date"],
        runner_request["atr_period"],
    )
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(_format_runner_result(result, chart_data), file, ensure_ascii=False)
'''


def generate_live_runner_code(strategy_code: str, request: BacktestRequest, strategy_file: Path, output_file: Path) -> str:
    runner_request = {
        "stock_id": request.stock_id,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "starting_cash": request.starting_cash,
        "commission": request.commission,
        "commission_multiplier": request.commission / 0.0008 if request.commission is not None else 1,
        "slippage": request.slippage,
        "stamp_tax": request.stamp_tax,
        "tax_multiplier": request.stamp_tax / 0.001 if request.stamp_tax is not None else 1,
        "round_lot": request.round_lot,
        "t_plus_one": request.t_plus_one,
        "timeout_seconds": DEFAULT_LIVE_DATA_TIMEOUT_SECONDS,
        "retries": DEFAULT_LIVE_DATA_RETRIES,
        "atr_period": request.atr_period,
        "adjust": os.getenv("LIVE_DATA_ADJUST", "qfq"),
        "provider_url": os.getenv("A_STOCK_DATA_URL"),
        "engine_frequency": _engine_frequency(request.period, request.execution_time),
        "signal_frequency": _signal_frequency(request.period),
    }
    return (
        LIVE_RQALPHA_RUNNER_TEMPLATE
        + "\n\nSTRATEGY_SOURCE = "
        + repr(strategy_code)
        + "\nRUNNER_REQUEST = "
        + repr(runner_request)
        + "\nOUTPUT_FILE = "
        + repr(str(output_file))
        + "\nSTRATEGY_FILE = "
        + repr(str(strategy_file))
        + "\n\nif __name__ == \"__main__\":\n"
        + "    Path(STRATEGY_FILE).write_text(STRATEGY_SOURCE, encoding=\"utf-8\")\n"
        + "    run_live_rqalpha(STRATEGY_SOURCE, RUNNER_REQUEST, OUTPUT_FILE, STRATEGY_FILE)\n"
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_rqalpha_python() -> str:
    configured = os.getenv("RQALPHA_PYTHON")
    if configured:
        return configured

    local_python = _project_root() / ".venv-rqsdk" / "Scripts" / "python.exe"
    if local_python.exists():
        return str(local_python)

    return sys.executable


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def _format_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _has_intraday_time(value: Any) -> bool:
    if value is None:
        return False
    try:
        timestamp = pd.to_datetime(value)
        if pd.isna(timestamp):
            return False
        return timestamp.time() != dt_time(0, 0)
    except Exception:
        return False


def _format_datetime(value: Any, default_time: str = "09:31:00") -> str | None:
    if value is None:
        return None
    try:
        timestamp = pd.to_datetime(value)
        if pd.isna(timestamp):
            return str(value)
        if timestamp.time() == dt_time(0, 0):
            return f"{timestamp.strftime('%Y-%m-%d')} {default_time}"
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        text = str(value)
        if len(text) == 10:
            return f"{text} {default_time}"
        return text


def _execution_phase(value: Any) -> str:
    formatted = _format_datetime(value)
    if not formatted or len(formatted) < 19:
        return "盘中运行"
    clock = formatted[11:19]
    if clock < "09:30:00":
        return "盘前运行"
    if clock >= "15:00:00":
        return "日线收盘撮合"
    return "盘中运行"


def _format_trades(trades: Any) -> list[dict[str, Any]]:
    if trades is None:
        return []

    trades_df = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame(trades)
    if trades_df.empty:
        return []
    if "trading_datetime" not in trades_df.columns and "datetime" not in trades_df.columns and isinstance(trades_df.index, pd.DatetimeIndex):
        trades_df = trades_df.reset_index()
        trades_df = trades_df.rename(columns={trades_df.columns[0]: "trading_datetime"})
    else:
        trades_df = trades_df.reset_index(drop=True)

    normalized: list[dict[str, Any]] = []
    for _, trade in trades_df.iterrows():
        raw_time = trade.get("trading_datetime") or trade.get("datetime")
        action = str(trade.get("side", "")).upper()
        normalized.append(
            {
                "date": _format_date(raw_time),
                "time": _format_datetime(raw_time),
                "execution_time": _format_datetime(raw_time),
                "execution_phase": _execution_phase(raw_time),
                "time_source": "rqalpha_trading_datetime" if _has_intraday_time(raw_time) else "daily_bar_execution_slot",
                "time_note": "日线回测按盘中撮合时点展示，非分钟线逐笔行情。",
                "order_id": str(trade.get("order_id", "")),
                "action": action,
                "price": _safe_float(trade.get("last_price")),
                "amount": int(trade.get("last_quantity", 0) or 0),
                "transaction_cost": _safe_float(trade.get("transaction_cost")),
            }
        )
    return normalized


def _format_portfolio_curve(portfolio: Any) -> list[dict[str, Any]]:
    if portfolio is None:
        return []
    portfolio_df = portfolio.copy() if isinstance(portfolio, pd.DataFrame) else pd.DataFrame(portfolio)
    if portfolio_df.empty:
        return []
    if "date" not in portfolio_df.columns:
        portfolio_df = portfolio_df.reset_index()
        if "date" not in portfolio_df.columns and len(portfolio_df.columns):
            portfolio_df = portfolio_df.rename(columns={portfolio_df.columns[0]: "date"})

    rows: list[dict[str, Any]] = []
    for _, row in portfolio_df.reset_index(drop=True).iterrows():
        total_value = row.get("total_value")
        unit_net_value = row.get("unit_net_value")
        if total_value is None and unit_net_value is None:
            continue
        rows.append(
            {
                "time": _format_datetime(row.get("date")),
                "portfolio_value": _safe_float(total_value),
                "unit_net_value": _safe_float(unit_net_value),
                "cash": _safe_float(row.get("cash")),
                "market_value": _safe_float(row.get("market_value")),
            }
        )
    return [row for row in rows if row["time"] and row["portfolio_value"] is not None]


def _format_result(output_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(output_file.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "statistics" in payload and "trades" in payload:
            return payload
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    with output_file.open("rb") as file:
        result = pickle.load(file)

    if isinstance(result, dict) and "sys_analyser" in result:
        result = result["sys_analyser"]

    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    trades = result.get("trades") if isinstance(result, dict) else None
    portfolio = result.get("portfolio") if isinstance(result, dict) else None
    return {
        "success": True,
        "message": "回测完成。",
        "statistics": {
            "total_returns": _safe_float(summary.get("total_returns")),
            "annualized_returns": _safe_float(summary.get("annualized_returns")),
            "max_drawdown": _safe_float(summary.get("max_drawdown")),
            "sharpe_ratio": _safe_float(summary.get("sharpe")),
            "volatility": _safe_float(summary.get("volatility")),
            "turnover": _safe_float(summary.get("turnover")),
        },
        "trades": _format_trades(trades),
        "portfolio_curve": _format_portfolio_curve(portfolio),
    }


def _compat_trade(row: dict[str, Any], stock_id: str) -> dict[str, Any]:
    raw_direction = str(row.get("direction") or row.get("action") or row.get("side") or "").upper()
    if "SELL" in raw_direction:
        direction = "SELL"
    elif "BUY" in raw_direction:
        direction = "BUY"
    else:
        direction = raw_direction or "UNKNOWN"

    quantity = row.get("quantity", row.get("amount", row.get("qty", 0)))
    try:
        quantity = int(quantity or 0)
    except (TypeError, ValueError):
        quantity = 0

    raw_time = row.get("time") or row.get("execution_time") or row.get("trading_datetime") or row.get("datetime") or row.get("date")
    execution_time = _format_datetime(raw_time)

    return {
        **row,
        "date": _format_date(raw_time),
        "time": execution_time,
        "execution_time": execution_time,
        "execution_phase": row.get("execution_phase") or _execution_phase(raw_time),
        "time_source": row.get("time_source") or ("rqalpha_trading_datetime" if _has_intraday_time(raw_time) else "daily_bar_execution_slot"),
        "time_note": row.get("time_note") or "日线回测按盘中撮合时点展示，非分钟线逐笔行情。",
        "symbol": row.get("symbol") or row.get("code") or stock_id,
        "name": row.get("name") or get_market_provider().get_name(stock_id),
        "direction": direction,
        "price": row.get("price") or row.get("last_price"),
        "quantity": quantity,
        "amount": row.get("turnover") or row.get("trade_amount") or ((row.get("price") or row.get("last_price") or 0) * quantity if quantity else 0),
        "fee": row.get("fee") or row.get("transaction_cost") or 0,
        "slippage": row.get("slippage") or 0,
        "status": row.get("status") or "已成交",
        "reason": row.get("reason") or ("买入条件触发" if direction == "BUY" else "卖出或风控条件触发"),
        "audit": row.get("audit") or ("买入信号确认，已通过 A 股 100 股整手校验" if direction == "BUY" else "卖出信号确认，已通过 A 股 T+1 可卖校验"),
    }

def _merge_date_time(raw_time: Any, clock: str | None) -> str | None:
    if not clock:
        return _format_datetime(raw_time)
    day = _format_date(raw_time)
    if not day:
        return _format_datetime(raw_time)
    return f"{day} {clock}"


DAILY_EXECUTION_NOTE = (
    "当前为日线回测：信号和成交价格来自日K数据，展示的盘中时间只是策略调度标签，"
    "不代表真实1分钟逐笔撮合。若要验证09:31精确成交，需要接入分钟线回测。"
)


def _is_daily_backtest_period(period: str | None) -> bool:
    return str(period or "day").lower() in {"day", "1d", "daily"}


def _engine_frequency(period: str | None, user_execution_time: str | None = None) -> str:
    if user_execution_time:
        return "1m"
    return "1d" if _is_daily_backtest_period(period) else "1m"


def _signal_frequency(period: str | None) -> str:
    return "1d" if _is_daily_backtest_period(period) else "1m"


def _market_data_period(period: str | None, user_execution_time: str | None = None) -> str:
    return "1m" if _engine_frequency(period, user_execution_time) == "1m" else "day"


def _minute_data_unavailable_response(request: BacktestRequest, data_source: str = "market_provider", detail: str | None = None) -> dict[str, Any]:
    execution_time = request.execution_time or "指定分钟"
    return {
        "success": False,
        "error_code": "MINUTE_MARKET_DATA_UNAVAILABLE",
        "message": (
            f"分钟级行情不足，无法按 {execution_time} 对 {request.start_date} 至 {request.end_date} "
            "做真实分钟级成交回测。请缩短回测区间、切换可提供分钟历史的数据源，或去掉执行时间改用日线估算口径。"
        ),
        "diagnosis": {
            "symbol": request.stock_id,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "period": request.period,
            "requested_execution_time": request.execution_time,
            "requested_data_period": "1m",
            "data_source": data_source,
            "detail": detail or "",
        },
        "warnings": [
            "系统没有用日线数据冒充分钟级成交结果，因此本次回测已停止。",
            "若需要长期 9:31 / 10:00 等分钟级调仓，需要接入覆盖该区间的分钟历史数据源。",
        ],
    }


def _execution_model(period: str | None, user_execution_time: str | None = None) -> dict[str, Any]:
    if _is_daily_backtest_period(period) and user_execution_time:
        return {
            "granularity": "minute",
            "precision": "intraday_scheduled",
            "label": "日线信号 + 分钟级调仓",
            "price_source": "minute_bar",
            "signal_source": "previous_completed_daily_bar",
            "requested_execution_time": user_execution_time,
            "is_precise_intraday": True,
            "note": "当前以 1 分钟频率运行 rqalpha：策略信号使用上一根已完成日K，成交按用户指定分钟调仓时点撮合。",
        }
    if _is_daily_backtest_period(period):
        return {
            "granularity": "day",
            "precision": "daily_estimated",
            "label": "日线估算成交",
            "price_source": "daily_bar",
            "signal_source": "daily_bar",
            "requested_execution_time": user_execution_time,
            "is_precise_intraday": False,
            "note": DAILY_EXECUTION_NOTE,
        }
    return {
        "granularity": "minute",
        "precision": "intraday",
        "label": "分钟级撮合",
        "price_source": "minute_bar",
        "signal_source": "minute_bar",
        "requested_execution_time": user_execution_time,
        "is_precise_intraday": True,
        "note": "当前回测使用分钟级行情，成交时间按分钟线撮合口径展示。",
    }


def _execution_warnings(period: str | None, user_execution_time: str | None = None) -> list[str]:
    if user_execution_time and _is_daily_backtest_period(period):
        return ["当前为日线信号 + 分钟级执行：系统用上一根已完成日K判断信号，并用 1 分钟行情在指定时点撮合，避免偷看当天收盘价。"]
    if not _is_daily_backtest_period(period):
        return []
    suffix = f"用户指定的 {user_execution_time} 会作为调度标签显示，但不是分钟级真实成交。" if user_execution_time else ""
    return [f"当前为日线回测，成交时间和价格为日K估算口径；不能等同于分钟级真实撮合。{suffix}".strip()]


def _compat_trade_with_time(
    row: dict[str, Any],
    stock_id: str,
    user_execution_time: str | None = None,
    period: str | None = "day",
) -> dict[str, Any]:
    trade = _compat_trade(row, stock_id)
    model = _execution_model(period, user_execution_time)
    is_precise_intraday = bool(model["is_precise_intraday"])
    trade.update(
        {
            "execution_precision": row.get("execution_precision") or model["precision"],
            "execution_label": row.get("execution_label") or model["label"],
            "price_source": row.get("price_source") or model["price_source"],
            "signal_source": row.get("signal_source") or model["signal_source"],
            "is_precise_intraday": bool(row.get("is_precise_intraday", is_precise_intraday)),
            "time_source": row.get("time_source") or ("minute_bar_execution_slot" if is_precise_intraday else "daily_bar_execution_slot"),
            "time_note": row.get("time_note") or model["note"],
        }
    )
    if not user_execution_time:
        return trade
    raw_time = row.get("time") or row.get("execution_time") or row.get("trading_datetime") or row.get("datetime") or row.get("date")
    rqalpha_time = trade.get("rqalpha_time") or trade.get("time") or _format_datetime(raw_time)
    display_time = _format_datetime(raw_time) if is_precise_intraday and _has_intraday_time(raw_time) else _merge_date_time(raw_time, user_execution_time)
    trade.update(
        {
            "time": display_time,
            "execution_time": display_time,
            "rqalpha_time": rqalpha_time,
            "execution_phase": _execution_phase(display_time),
            "time_source": "minute_bar_user_schedule" if is_precise_intraday else "daily_bar_user_schedule",
            "time_note": model["note"],
        }
    )
    return trade


def _display_symbol(symbol: str) -> str:
    return symbol.replace(".XSHE", ".SZ").replace(".XSHG", ".SH")


def _execution_logs_from_trades(trades: list[dict[str, Any]], stock_id: str) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for trade in trades:
        trade_time = trade.get("execution_time") or trade.get("time")
        if not trade_time:
            continue
        direction = str(trade.get("direction") or "").upper()
        action_cn = "买入" if direction == "BUY" else "卖出" if direction == "SELL" else "交易"
        reason = trade.get("reason") or ("买入条件触发" if direction == "BUY" else "卖出或风控条件触发")
        logs.append(
            {
                "time": trade_time,
                "level": "INFO",
                "phase": trade.get("execution_phase") or "盘中运行",
                "message": f"{trade_time} {reason}, {action_cn} {_display_symbol(str(trade.get('symbol') or stock_id))}",
            }
        )
    return logs


def _baseline_ai_audit(metrics: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": "已完成真实 A 股行情回测。请重点关注交易次数、最大回撤、夏普率和样本区间是否足够稳定。",
        "strengths": [
            "策略规则清晰，便于后续参数复盘。",
            "回测结果已纳入 A 股整手交易与 T+1 约束。",
        ],
        "risks": [
            f"交易次数为 {len(trades)}，样本过少时不能证明策略稳定。",
            f"最大回撤为 {metrics.get('max_drawdown')}，上线前需要重新检查仓位控制。",
            f"夏普率为 {metrics.get('sharpe')}，若长期低于 1，说明收益质量偏弱。",
        ],
        "suggestions": [
            "加入成交量确认条件，例如 volume > volume_ma20 * 1.2。",
            "扩大股票和时间样本，避免单一区间过拟合。",
            "增加固定止损、最大持仓天数和仓位上限。",
        ],
        "score": 60,
    }


def _actual_bar_range(bars: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not bars:
        return None, None
    values = [_format_date(row.get("time") or row.get("date")) for row in bars]
    values = [value for value in values if value]
    return (values[0], values[-1]) if values else (None, None)


def _missing_ratio(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 1.0
    fields = ["open", "high", "low", "close"]
    total = len(bars) * len(fields)
    missing = 0
    for row in bars:
        for field_name in fields:
            if _safe_float(row.get(field_name)) is None:
                missing += 1
    return round(missing / total, 6) if total else 1.0


def _rqalpha_version() -> str:
    try:
        import rqalpha  # type: ignore

        return str(getattr(rqalpha, "__version__", "unknown"))
    except Exception:
        return "unknown"


def _strategy_snapshot(request: BacktestRequest) -> dict[str, Any]:
    rules = request.rules or {
        "buy_rules": [{"description": "买入条件", "expression": request.buy_logic}],
        "sell_rules": [{"description": "卖出条件", "expression": request.sell_logic}],
        "risk_rules": [{"description": "风控条件", "expression": request.risk_idea}],
    }
    return {
        "strategy_name": request.strategy_name,
        "mode": request.mode,
        "symbols": [request.stock_id],
        "period": request.period,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "rules": rules,
        "params": {
            "initial_cash": request.starting_cash,
            "commission": request.commission,
            "slippage": request.slippage,
            "stamp_tax": request.stamp_tax,
            "t_plus_one": request.t_plus_one,
            "round_lot": request.round_lot,
            "execution_time": request.execution_time,
            **(request.params or {}),
        },
    }


def _same_result_warnings(response: dict[str, Any]) -> list[str]:
    """Warn when two different strategy fingerprints produce identical visible results."""

    def expression_signature(payload: dict[str, Any]) -> str:
        strategy_json = payload.get("strategy_json") or {}
        rules = strategy_json.get("rules") or {}
        parts: list[str] = []
        # Buy/sell rules define the executed signal path.  Risk rules may be
        # present but not trigger in a period, so they should not by themselves
        # make a repeat of the same signal look like a broken backtest.
        for key in ("buy_rules", "sell_rules"):
            for item in rules.get(key) or []:
                if isinstance(item, dict):
                    expression = str(item.get("expression") or "").strip().lower()
                else:
                    expression = str(item or "").strip().lower()
                if expression:
                    parts.append(f"{key}:{expression}")
        return "|".join(parts)

    current_strategy_hash = response.get("strategy_hash")
    if not current_strategy_hash:
        return []
    current_signature = expression_signature(response)
    current_curve_hash = stable_hash((response.get("curves") or {}).get("strategy_curve") or [])
    current_metrics_hash = stable_hash(response.get("metrics") or {})
    symbol = response.get("symbol")
    period = response.get("period")
    time_range = response.get("time_range") or {}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT result_json FROM backtest_runs
                WHERE symbol = ?
                ORDER BY id DESC
                LIMIT 30
                """,
                (symbol,),
            ).fetchall()
    except Exception:
        return []

    for row in rows:
        try:
            previous = json.loads(row["result_json"] or "{}")
        except Exception:
            continue
        if previous.get("strategy_hash") == current_strategy_hash:
            continue
        if expression_signature(previous) == current_signature:
            continue
        previous_debug = previous.get("debug") or {}
        if not previous.get("code_hash") or not previous_debug.get("executed_generated_code"):
            continue
        previous_range = previous.get("time_range") or {}
        if previous.get("period") != period:
            continue
        if previous_range.get("requested_start") != time_range.get("requested_start"):
            continue
        if previous_range.get("requested_end") != time_range.get("requested_end"):
            continue
        previous_curve_hash = stable_hash((previous.get("curves") or {}).get("strategy_curve") or [])
        previous_metrics_hash = stable_hash(previous.get("metrics") or {})
        if previous_curve_hash == current_curve_hash and previous_metrics_hash == current_metrics_hash:
            return ["检测到不同策略产生完全相同结果，请检查策略是否真实执行。"]
    return []


def _save_backtest_run(response: dict[str, Any]) -> None:
    try:
        created_at = (response.get("engine_info") or {}).get("run_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trust_level = ((response.get("trust_audit") or {}).get("trust_level") or "")
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs
                (backtest_id, user_id, symbol, strategy_name, period, result_json, trust_level, created_at)
                VALUES (?, 0, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(backtest_id) DO UPDATE SET
                    result_json=excluded.result_json,
                    trust_level=excluded.trust_level
                """,
                (
                    response.get("backtest_id"),
                    response.get("symbol"),
                    response.get("strategy_name") or "",
                    response.get("period") or "",
                    json.dumps(response, ensure_ascii=False, default=str),
                    trust_level,
                    created_at,
                ),
            )
    except Exception:
        return


@router.get("/runs")
def list_backtest_runs(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT backtest_id, symbol, strategy_name, period, result_json, trust_level, created_at
            FROM backtest_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            result = json.loads(row["result_json"] or "{}")
        except Exception:
            result = {}
        items.append(
            {
                "backtest_id": row["backtest_id"],
                "symbol": row["symbol"],
                "name": result.get("name") or row["symbol"],
                "strategy_name": row["strategy_name"],
                "period": row["period"],
                "metrics": result.get("metrics") or {},
                "strategy_json": result.get("strategy_json") or {},
                "time_range": result.get("time_range") or {},
                "data_info": result.get("data_info") or {},
                "trust_level": row["trust_level"],
                "created_at": row["created_at"],
            }
        )
    return {"items": items}


class BacktestRunUpdate(BaseModel):
    strategy_name: str | None = None
    name: str | None = None


@router.patch("/runs/{backtest_id}")
def update_backtest_run(backtest_id: str, payload: BacktestRunUpdate) -> dict[str, Any]:
    next_name = (payload.strategy_name or payload.name or "").strip()
    if not next_name:
        return {"success": False, "error_code": "EMPTY_BACKTEST_NAME", "message": "回测记录名称不能为空"}
    if len(next_name) > 80:
        return {"success": False, "error_code": "BACKTEST_NAME_TOO_LONG", "message": "回测记录名称不能超过 80 个字符"}

    with get_connection() as conn:
        row = conn.execute(
            "SELECT result_json FROM backtest_runs WHERE backtest_id = ?",
            (backtest_id,),
        ).fetchone()
        if not row:
            return {"success": False, "error_code": "BACKTEST_RUN_NOT_FOUND", "message": "未找到该回测记录"}
        try:
            result = json.loads(row["result_json"] or "{}")
        except Exception:
            result = {}
        result["strategy_name"] = next_name
        conn.execute(
            """
            UPDATE backtest_runs
            SET strategy_name = ?, result_json = ?
            WHERE backtest_id = ?
            """,
            (next_name, json.dumps(result, ensure_ascii=False, default=str), backtest_id),
        )
    return {"success": True, "backtest_id": backtest_id, "strategy_name": next_name}


@router.delete("/runs/{backtest_id}")
def delete_backtest_run(backtest_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM backtest_runs WHERE backtest_id = ?", (backtest_id,))
        if cursor.rowcount == 0:
            return {"success": False, "error_code": "BACKTEST_RUN_NOT_FOUND", "message": "未找到该回测记录"}
    return {"success": True, "backtest_id": backtest_id}


@router.get("/runs/{backtest_id}")
def get_backtest_run(backtest_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT result_json FROM backtest_runs WHERE backtest_id = ?", (backtest_id,)).fetchone()
    if not row:
        return {"success": False, "error_code": "BACKTEST_RUN_NOT_FOUND", "message": "未找到该回测记录"}
    try:
        return json.loads(row["result_json"] or "{}")
    except Exception:
        return {"success": False, "error_code": "BACKTEST_RUN_DAMAGED", "message": "回测记录损坏，无法读取"}

def _compat_backtest_response(
    request: BacktestRequest,
    result: dict[str, Any],
    validated_bars: list[dict[str, Any]],
    data_source: str,
    latency_ms: int,
    strategy_code: str,
    validation_warnings: list[str],
    run_started_at: datetime,
) -> dict[str, Any]:
    market_period = _market_data_period(request.period, request.execution_time)
    engine_frequency = _engine_frequency(request.period, request.execution_time)
    signal_frequency = _signal_frequency(request.period)
    trades = [_compat_trade_with_time(row, request.stock_id, request.execution_time, request.period) for row in result.get("trades", [])]
    bars = result.get("bars") or result.get("chart_data") or result.get("kline") or result.get("daily_data") or validated_bars
    actual_start, actual_end = _actual_bar_range(validated_bars if market_period == "1m" else bars)
    benchmark_start = actual_start or request.start_date.isoformat()
    benchmark_end = actual_end or request.end_date.isoformat()
    benchmark_result = BenchmarkService().get_default_benchmark(benchmark_start, benchmark_end)
    benchmark_bars = benchmark_result.bars
    benchmark_warnings = benchmark_result.warnings
    portfolio_curve = result.get("portfolio_curve") or []
    equity_curve = build_equity_curve_from_portfolio(
        portfolio_curve,
        benchmark_bars,
        float(request.starting_cash),
    ) or build_equity_curve(bars, trades, benchmark_bars, float(request.starting_cash))
    metrics, metric_warnings = compute_metrics(equity_curve, trades, benchmark_bars, float(request.starting_cash))
    statistics = result.get("statistics") or {}
    if _safe_float(statistics.get("total_returns")) is not None:
        metrics["total_return"] = _safe_float(statistics.get("total_returns"))
    if _safe_float(statistics.get("annualized_returns")) is not None:
        metrics["annual_return"] = _safe_float(statistics.get("annualized_returns"))
    if _safe_float(statistics.get("max_drawdown")) is not None:
        metrics["max_drawdown"] = -abs(float(_safe_float(statistics.get("max_drawdown"))))
    if _safe_float(statistics.get("sharpe_ratio")) is not None:
        metrics["sharpe"] = _safe_float(statistics.get("sharpe_ratio"))
    if _safe_float(statistics.get("volatility")) is not None:
        metrics["volatility"] = _safe_float(statistics.get("volatility"))
    if _safe_float(statistics.get("turnover")) is not None:
        metrics["turnover"] = _safe_float(statistics.get("turnover"))
    curves, curve_warnings = build_standard_curves(equity_curve)
    if not curves.get("benchmark_curve"):
        metrics["alpha"] = None
        metrics["beta"] = None
    run_at_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    run_at_display = run_started_at.strftime("%Y-%m-%d %H:%M:%S")
    strategy_json = _strategy_snapshot(request)
    snapshots = SnapshotService().build_snapshot(strategy_code=strategy_code, strategy_json=strategy_json, bars=bars)
    warnings = [
        *validation_warnings,
        *benchmark_warnings,
        *metric_warnings,
        *curve_warnings,
        *_execution_warnings(request.period, request.execution_time),
    ]
    execution_logs = _execution_logs_from_trades(trades, request.stock_id)

    response = {
        "success": True,
        "backtest_id": make_backtest_id(request.stock_id, run_at_id),
        "symbol": request.stock_id,
        "name": get_market_provider().get_name(request.stock_id),
        "period": request.period,
        "strategy_name": request.strategy_name,
        "benchmark": {
            "symbol": benchmark_result.symbol,
            "name": benchmark_result.name,
            "available": benchmark_result.available,
            "source": benchmark_result.source or None,
            "bars_count": len(benchmark_bars),
            "actual_start": benchmark_result.actual_start,
            "actual_end": benchmark_result.actual_end,
            "error": benchmark_result.error,
        },
        "time_range": {
            "requested_start": request.start_date.isoformat(),
            "requested_end": request.end_date.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "bars_count": len(validated_bars if market_period == "1m" else bars),
            "chart_bars_count": len(bars),
        },
        "data_info": {
            "data_source": data_source,
            "benchmark_source": benchmark_result.source,
            "adjust": os.getenv("LIVE_DATA_ADJUST", "qfq"),
            "bar_period": market_period,
            "engine_frequency": engine_frequency,
            "signal_frequency": signal_frequency,
            "execution_bars_count": len(validated_bars),
            "chart_bars_count": len(bars),
            "benchmark_symbol": benchmark_result.symbol,
            "benchmark_name": benchmark_result.name,
            "benchmark_bars_count": len(benchmark_bars),
            "missing_ratio": _missing_ratio(bars),
            "latency_ms": latency_ms,
            "is_mock": False,
        },
        "engine_info": {
            "engine": "rqalpha",
            "engine_version": _rqalpha_version(),
            "run_at": run_at_display,
            "cost_model": {
                "commission": request.commission,
                "slippage": request.slippage,
                "stamp_tax": request.stamp_tax,
                "round_lot": request.round_lot,
                "t_plus_one": request.t_plus_one,
                "execution_time": request.execution_time,
            },
            "execution_model": _execution_model(request.period, request.execution_time),
            "engine_frequency": engine_frequency,
            "signal_frequency": signal_frequency,
        },
        "metrics": metrics,
        "curves": curves,
        "bars": bars,
        "trades": trades,
        "warnings": warnings,
        "strategy_json": strategy_json,
        "strategy_hash": snapshots["strategy_hash"],
        "code_hash": snapshots["code_hash"],
        "config_hash": snapshots["config_hash"],
        "strategy_code_hash": snapshots["strategy_code_hash"],
        "config_snapshot_hash": snapshots["config_snapshot_hash"],
        "data_hash": snapshots["data_hash"],
        "debug": {
            "used_strategy_hash": snapshots["strategy_hash"],
            "used_code_hash": snapshots["code_hash"],
            "received_strategy_json": bool(request.rules),
            "executed_generated_code": True,
            "cache_hit": False,
            "equity_curve_source": "rqalpha_portfolio" if portfolio_curve else "reconstructed_from_trades",
            "buy_logic": request.buy_logic,
            "sell_logic": request.sell_logic,
        },
        "raw_statistics": result.get("statistics") or {},
        "logs": [
            {"level": "系统", "message": "校验 A 股 T+1 与 100 股整手交易约束"},
            {"level": "数据", "message": f"获取真实前复权行情，周期：{market_period}，数据源：{data_source}"},
            {"level": "引擎", "message": "rqalpha 撮合回测完成"},
            {"level": "完成", "message": f"回测完成，生成 {len(trades)} 条交割记录"},
        ],
        "execution_logs": execution_logs,
        "ai_audit": result.get("ai_audit") or _baseline_ai_audit(metrics, trades),
    }
    if len(curves.get("strategy_curve") or []) < 2 or len(curves.get("drawdown_curve") or []) < 2:
        response["success"] = False
        response["error_code"] = "MISSING_EQUITY_CURVE"
        response["message"] = "回测成功但权益曲线缺失，结果不可信，已停止展示。"
        response["warnings"] = response["warnings"] + ["策略收益曲线或回撤曲线缺失，禁止展示为正式回测结果。"]
    response["warnings"] = response["warnings"] + _same_result_warnings(response)
    response["trust_audit"] = BacktestResultAuditor().audit(response)
    if response["trust_audit"]["blocking_errors"]:
        response["warnings"] = response["warnings"] + response["trust_audit"]["blocking_errors"]
    response = safe_json_response(response)
    _save_backtest_run(response)
    return response


def _normalize_subprocess_text(stdout: bytes, stderr: bytes) -> str:
    combined = b"\n".join(part for part in [stdout, stderr] if part)
    text = combined.decode("utf-8", errors="replace").strip()
    if not text:
        text = combined.decode("gbk", errors="replace").strip()
    return text[-4000:]


def _friendly_rqalpha_error(raw_text: str) -> str:
    if not raw_text:
        return "米筐没有返回具体错误信息。"

    if "user_system_log: Traceback" in raw_text or "Traceback (most recent call last)" in raw_text:
        meaningful = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip()
            and not line.strip().startswith("File ")
            and not line.strip().startswith("Traceback")
            and "user_system_log: Traceback" not in line
        ]
        if meaningful:
            return " / ".join(meaningful[-6:])[:1200]

    def pick_exception_message(marker: str) -> str:
        for line in reversed(raw_text.splitlines()):
            stripped = line.strip()
            if marker not in stripped:
                continue
            if stripped.startswith("RuntimeError:"):
                return stripped.replace("RuntimeError:", "", 1).strip()
            if stripped.startswith("ValueError:"):
                return stripped.replace("ValueError:", "", 1).strip()
            if stripped.startswith("Exception:"):
                return stripped.replace("Exception:", "", 1).strip()
        for line in reversed(raw_text.splitlines()):
            stripped = line.strip()
            if marker in stripped and "raise RuntimeError" not in stripped:
                return stripped
        return marker

    if "No module named 'rqalpha'" in raw_text:
        return "运行回测的 Python 环境缺少 rqalpha，请先安装米筐或设置 RQALPHA_PYTHON。"
    if "No module named 'akshare'" in raw_text or "缺少 akshare" in raw_text:
        return "运行回测的 Python 环境缺少 akshare，请先安装 akshare。"
    if "No module named 'talib'" in raw_text or "No module named talib" in raw_text:
        return "运行回测的 Python 环境缺少 TA-Lib，请先安装 TA-Lib。"
    if "实时行情拉取失败" in raw_text:
        message = pick_exception_message("实时行情拉取失败")
        if any(token in raw_text for token in ("ProxyError", "RemoteDisconnected", "ConnectionError", "ReadTimeout", "TimeoutError")):
            return f"{message}。当前行情接口连接失败，请检查网络或代理后重试。"
        return message
    if "策略条件" in raw_text:
        return pick_exception_message("策略条件")

    useful_lines = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Traceback") or stripped.startswith("File "):
            continue
        if stripped.startswith("RuntimeError:"):
            return stripped.replace("RuntimeError:", "", 1).strip()
        if "ERROR:" in stripped:
            useful_lines.append(stripped.split("ERROR:", 1)[-1].strip())
    if useful_lines:
        return useful_lines[-1]

    return raw_text.splitlines()[-1].strip()[:1000]


async def _run_rqalpha_script(runner_file: Path, output_file: Path) -> None:
    command = [_default_rqalpha_python(), str(runner_file)]
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("NO_PROXY", "*")
    env.setdefault("no_proxy", "*")

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_project_root()),
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=DEFAULT_BACKTEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("回测运行超时，请缩短日期范围或检查实时行情接口是否正常。") from exc

    if process.returncode != 0:
        detail = _normalize_subprocess_text(stdout, stderr)
        raise RuntimeError(f"米筐回测执行失败：{_friendly_rqalpha_error(detail)}")

    if not output_file.exists():
        raise RuntimeError("米筐回测结束了，但没有生成结果文件，请检查实时行情接口和策略条件。")


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    temp_root = Path(tempfile.gettempdir()) / "rqalpha_backtests" / uuid.uuid4().hex
    strategy_file = temp_root / "strategy.py"
    runner_file = temp_root / "live_runner.py"
    output_file = temp_root / "result.pkl"
    run_started_at = datetime.now()

    try:
        validator = BacktestValidator()
        validator.validate_request(request)
        if request.period == "1d":
            request.period = "day"
        if request.mode in {"factor_selection", "stock_pool"} or (request.params or {}).get("strategy_mode") == "factor_selection":
            response = await asyncio.to_thread(run_factor_selection_backtest, request, run_started_at)
            if response.get("success"):
                _save_backtest_run(response)
            return response

        data_period = _market_data_period(request.period, request.execution_time)
        data_started = time.perf_counter()
        market_bars, data_source = get_market_provider().get_bars(
            request.stock_id,
            data_period,
            request.start_date.isoformat(),
            request.end_date.isoformat(),
            os.getenv("LIVE_DATA_ADJUST", "qfq"),
        )
        latency_ms = int((time.perf_counter() - data_started) * 1000)
        validated_bars = [
            bar.to_dict() if hasattr(bar, "to_dict") else dict(bar)
            for bar in market_bars
        ]
        validation_warnings = validator.validate_bars(validated_bars, request, data_source)

        temp_root.mkdir(parents=True, exist_ok=False)
        strategy_code = generate_strategy_code(request)
        runner_code = generate_live_runner_code(strategy_code, request, strategy_file, output_file)
        compile(strategy_code, str(strategy_file), "exec")
        compile(runner_code, str(runner_file), "exec")
        strategy_file.write_text(strategy_code, encoding="utf-8")
        runner_file.write_text(runner_code, encoding="utf-8")

        await _run_rqalpha_script(runner_file, output_file)
        return _compat_backtest_response(
            request,
            _format_result(output_file),
            validated_bars,
            data_source,
            latency_ms,
            strategy_code,
            validation_warnings,
            run_started_at,
        )
    except BacktestValidationError as exc:
        if exc.error_code == "EMPTY_MARKET_DATA" and request.execution_time and _market_data_period(request.period, request.execution_time) == "1m":
            return safe_json_response(
                _minute_data_unavailable_response(
                    request,
                    str(exc.diagnosis.get("data_source") or "market_provider"),
                    str(exc.diagnosis),
                )
            )
        return safe_json_response(exc.to_response())
    except EmptyMarketDataError as exc:
        if request.execution_time and _market_data_period(request.period, request.execution_time) == "1m":
            return safe_json_response(_minute_data_unavailable_response(request, "market_provider", str(exc)))
        return safe_json_response(
            {
                "success": False,
                "error_code": "EMPTY_MARKET_DATA",
                "message": f"{request.stock_id} 在 {request.start_date} 至 {request.end_date} 区间未获取到有效行情数据，已停止回测。",
                "diagnosis": {
                    "symbol": request.stock_id,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "data_source": "market_provider",
                    "detail": str(exc),
                },
            }
        )
    except MarketDataError as exc:
        return safe_json_response(
            {
                "success": False,
                "error_code": "DATA_SOURCE_ERROR",
                "message": f"本次回测失败：真实行情数据源不可用，{exc}",
                "diagnosis": {
                    "symbol": request.stock_id,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "data_source": "market_provider",
                },
            }
        )
    except LogicValidationError as exc:
        return safe_json_response(
            {
                "success": False,
                "error_code": "INVALID_STRATEGY_LOGIC",
                "message": str(exc),
                "diagnosis": {"symbol": request.stock_id, "strategy_name": request.strategy_name},
            }
        )
    except RuntimeError as exc:
        return safe_json_response(
            {
                "success": False,
                "error_code": "RQALPHA_EXECUTION_FAILED",
                "message": f"本次回测失败：{exc}",
                "diagnosis": {
                    "symbol": request.stock_id,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "engine": "rqalpha",
                },
            }
        )
    except Exception as exc:
        return safe_json_response(
            {
                "success": False,
                "error_code": "BACKTEST_SERVICE_ERROR",
                "message": f"本次回测失败：回测服务发生异常，{exc}",
                "diagnosis": {
                    "symbol": request.stock_id,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                },
            }
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
