from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import pandas as pd

from app.backtest.benchmark_service import validate_benchmark_bars


TRADING_DAYS_PER_YEAR = 252


def _finite_float(value: Any, digits: int = 6) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _date_key(value: Any) -> str:
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value or "")


def _trade_amount(trade: dict[str, Any]) -> float:
    price = _finite_float(trade.get("price") or trade.get("last_price")) or 0.0
    quantity = int(trade.get("quantity") or trade.get("qty") or trade.get("amount") or 0)
    amount = _finite_float(trade.get("turnover") or trade.get("trade_amount") or trade.get("amount"))
    if amount is not None and amount > 0 and amount != quantity:
        return amount
    return price * quantity


def build_equity_curve(
    bars: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    benchmark_bars: list[dict[str, Any]],
    starting_cash: float,
) -> list[dict[str, Any]]:
    """Reconstruct a conservative daily portfolio curve from real bars and trades."""

    if not bars:
        return []

    bars_frame = pd.DataFrame(bars).copy()
    bars_frame["date"] = pd.to_datetime(bars_frame["time"], errors="coerce")
    bars_frame = bars_frame.dropna(subset=["date"]).sort_values("date")
    bars_frame["key"] = bars_frame["date"].dt.strftime("%Y-%m-%d")

    benchmark_by_date: dict[str, float] = {}
    if benchmark_bars:
        benchmark_frame = pd.DataFrame(benchmark_bars).copy()
        benchmark_frame["date"] = pd.to_datetime(benchmark_frame["time"], errors="coerce")
        benchmark_frame = benchmark_frame.dropna(subset=["date"]).sort_values("date")
        for _, row in benchmark_frame.iterrows():
            close = _finite_float(row.get("close"))
            if close is not None:
                benchmark_by_date[row["date"].strftime("%Y-%m-%d")] = close

    benchmark_start = None
    trades_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        key = _date_key(trade.get("time") or trade.get("date") or trade.get("trading_datetime"))
        if key:
            trades_by_date[key].append(trade)

    cash = float(starting_cash)
    position = 0
    running_high = float(starting_cash)
    curve: list[dict[str, Any]] = []

    for _, row in bars_frame.iterrows():
        key = row["key"]
        close = _finite_float(row.get("close"))
        if close is None:
            continue

        for trade in trades_by_date.get(key, []):
            direction = str(trade.get("direction") or trade.get("action") or trade.get("side") or "").upper()
            quantity = int(trade.get("quantity") or trade.get("qty") or trade.get("amount") or 0)
            price = _finite_float(trade.get("price") or trade.get("last_price")) or close
            fee = _finite_float(trade.get("fee") or trade.get("transaction_cost")) or 0.0
            gross = price * quantity
            if "BUY" in direction:
                cash -= gross + fee
                position += quantity
            elif "SELL" in direction:
                cash += gross - fee
                position = max(0, position - quantity)

        value = cash + position * close
        running_high = max(running_high, value)
        benchmark_close = benchmark_by_date.get(key)
        if benchmark_start is None and benchmark_close is not None:
            benchmark_start = benchmark_close
        benchmark_return = None
        if benchmark_start and benchmark_close:
            benchmark_return = benchmark_close / benchmark_start - 1

        curve.append(
            {
                "time": key,
                "portfolio_value": _finite_float(value, 2),
                "return": _finite_float(value / starting_cash - 1),
                "benchmark_return": _finite_float(benchmark_return),
                "drawdown": _finite_float(value / running_high - 1),
            }
        )

    return curve


def build_equity_curve_from_portfolio(
    portfolio_curve: list[dict[str, Any]],
    benchmark_bars: list[dict[str, Any]],
    starting_cash: float,
) -> list[dict[str, Any]]:
    """Build the displayed equity curve from rqalpha's real portfolio records."""

    if not portfolio_curve:
        return []

    frame = pd.DataFrame(portfolio_curve).copy()
    frame["date"] = pd.to_datetime(frame.get("time"), errors="coerce")
    frame["portfolio_value"] = pd.to_numeric(frame.get("portfolio_value"), errors="coerce")
    if "unit_net_value" in frame.columns:
        frame["unit_net_value"] = pd.to_numeric(frame["unit_net_value"], errors="coerce")
    else:
        frame["unit_net_value"] = frame["portfolio_value"] / float(starting_cash)
    frame = frame.dropna(subset=["date", "portfolio_value", "unit_net_value"]).sort_values("date")
    if frame.empty:
        return []
    frame["day_key"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame = frame.groupby("day_key", as_index=False).tail(1).sort_values("date")

    benchmark_by_date: dict[str, float] = {}
    if benchmark_bars:
        benchmark_frame = pd.DataFrame(benchmark_bars).copy()
        benchmark_frame["date"] = pd.to_datetime(benchmark_frame["time"], errors="coerce")
        benchmark_frame = benchmark_frame.dropna(subset=["date"]).sort_values("date")
        for _, row in benchmark_frame.iterrows():
            close = _finite_float(row.get("close"))
            if close is not None:
                benchmark_by_date[row["date"].strftime("%Y-%m-%d")] = close

    benchmark_start = None
    running_high = None
    curve: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        key = row["date"].strftime("%Y-%m-%d")
        unit_net_value = float(row["unit_net_value"])
        running_high = unit_net_value if running_high is None else max(running_high, unit_net_value)
        benchmark_close = benchmark_by_date.get(key)
        if benchmark_start is None and benchmark_close is not None:
            benchmark_start = benchmark_close
        benchmark_return = None
        if benchmark_start and benchmark_close:
            benchmark_return = benchmark_close / benchmark_start - 1
        curve.append(
            {
                "time": key,
                "portfolio_value": _finite_float(row["portfolio_value"], 2),
                "return": _finite_float(unit_net_value - 1),
                "benchmark_return": _finite_float(benchmark_return),
                "drawdown": _finite_float(unit_net_value / running_high - 1) if running_high else None,
            }
        )
    return curve


def build_standard_curves(equity_curve: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    warnings: list[str] = []
    strategy_curve = [
        {"time": item["time"], "value": _finite_float(item.get("return"))}
        for item in equity_curve
        if _finite_float(item.get("return")) is not None
    ]
    benchmark_curve = [
        {"time": item["time"], "value": _finite_float(item.get("benchmark_return"))}
        for item in equity_curve
        if _finite_float(item.get("benchmark_return")) is not None
    ]
    drawdown_curve = [
        {"time": item["time"], "value": _finite_float(item.get("drawdown"))}
        for item in equity_curve
        if _finite_float(item.get("drawdown")) is not None
    ]

    valid_benchmark, reason = is_valid_return_curve(benchmark_curve)
    if not valid_benchmark:
        if benchmark_curve:
            warnings.append(f"基准曲线无效，已禁止展示为真实基准：{reason}")
        benchmark_curve = []

    return {
        "strategy_curve": strategy_curve,
        "benchmark_curve": benchmark_curve,
        "drawdown_curve": drawdown_curve,
        "equity_curve": equity_curve,
    }, warnings


def is_valid_return_curve(curve: list[dict[str, Any]]) -> tuple[bool, str]:
    if not curve or len(curve) < 2:
        return False, "曲线少于 2 个有效点"
    values = [_finite_float(item.get("value")) for item in curve]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return False, "曲线有效数值少于 2 个"
    if abs(max(values) - min(values)) < 1e-8:
        return False, "曲线为常数"
    return True, ""


def _pct_returns(values: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous:
            value = current / previous - 1
            if math.isfinite(value):
                returns.append(value)
    return returns


def _annual_return(total_return: float | None, count: int) -> float | None:
    if total_return is None or count <= 1 or total_return <= -1:
        return None
    return _finite_float((1 + total_return) ** (TRADING_DAYS_PER_YEAR / count) - 1)


def _round_trip_win_rate(trades: list[dict[str, Any]]) -> float | None:
    entry_price: float | None = None
    wins = 0
    completed = 0
    for trade in trades:
        direction = str(trade.get("direction") or trade.get("action") or "").upper()
        price = _finite_float(trade.get("price") or trade.get("last_price"))
        if price is None:
            continue
        if "BUY" in direction and entry_price is None:
            entry_price = price
        elif "SELL" in direction and entry_price is not None:
            completed += 1
            if price > entry_price:
                wins += 1
            entry_price = None
    if not completed:
        return None
    return _finite_float(wins / completed)


def compute_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    benchmark_bars: list[dict[str, Any]],
    starting_cash: float,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not equity_curve:
        warnings.append("收益曲线为空，核心指标暂无法计算。")
        return _empty_metrics(len(trades)), warnings

    values = [
        float(item["portfolio_value"])
        for item in equity_curve
        if _finite_float(item.get("portfolio_value")) is not None
    ]
    daily_returns = _pct_returns(values)
    total_return = _finite_float(values[-1] / starting_cash - 1) if values else None
    annual_return = _annual_return(total_return, len(values))
    max_drawdown = min((item.get("drawdown") for item in equity_curve if item.get("drawdown") is not None), default=None)
    max_drawdown = _finite_float(max_drawdown)

    volatility = None
    sharpe = None
    if len(daily_returns) >= 2:
        return_series = pd.Series(daily_returns, dtype="float64")
        std = float(return_series.std(ddof=1))
        if std > 0 and math.isfinite(std):
            volatility = _finite_float(std * math.sqrt(TRADING_DAYS_PER_YEAR))
            sharpe = _finite_float(float(return_series.mean()) / std * math.sqrt(TRADING_DAYS_PER_YEAR))
        else:
            warnings.append("策略日收益波动为 0，夏普率和波动率暂无法有效计算。")
    else:
        warnings.append("收益曲线样本不足，夏普率和波动率暂无法计算。")

    alpha, beta = _compute_alpha_beta(equity_curve, benchmark_bars, annual_return, warnings)
    win_rate = _round_trip_win_rate(trades)
    if win_rate is None and trades:
        warnings.append("卖出闭环交易不足，胜率暂无法计算。")
    elif win_rate is None:
        warnings.append("本次回测没有交易，胜率暂无法计算。")

    turnover = None
    total_trade_amount = sum(_trade_amount(trade) for trade in trades)
    mean_value = float(pd.Series(values).mean()) if values else 0.0
    if mean_value > 0:
        turnover = _finite_float(total_trade_amount / mean_value)

    return (
        {
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "alpha": alpha,
            "beta": beta,
            "volatility": volatility,
            "win_rate": win_rate,
            "trade_count": len(trades),
            "turnover": turnover,
        },
        warnings,
    )


def _compute_alpha_beta(
    equity_curve: list[dict[str, Any]],
    benchmark_bars: list[dict[str, Any]],
    annual_return: float | None,
    warnings: list[str],
) -> tuple[float | None, float | None]:
    if not benchmark_bars:
        warnings.append("基准数据为空，Alpha/Beta 暂无法计算。")
        return None, None
    benchmark_valid, benchmark_reason = validate_benchmark_bars(benchmark_bars)
    if not benchmark_valid:
        warnings.append(f"基准收益序列无效，Alpha/Beta 暂不可用：{benchmark_reason}")
        return None, None

    curve_frame = pd.DataFrame(equity_curve)
    curve_frame["date"] = pd.to_datetime(curve_frame["time"], errors="coerce")
    curve_frame = curve_frame.dropna(subset=["date", "portfolio_value"]).sort_values("date")
    curve_frame["strategy_return"] = pd.to_numeric(curve_frame["portfolio_value"], errors="coerce").pct_change()

    benchmark_frame = pd.DataFrame(benchmark_bars)
    benchmark_frame["date"] = pd.to_datetime(benchmark_frame["time"], errors="coerce")
    benchmark_frame["close"] = pd.to_numeric(benchmark_frame["close"], errors="coerce")
    benchmark_frame = benchmark_frame.dropna(subset=["date", "close"]).sort_values("date")
    benchmark_frame["benchmark_return"] = benchmark_frame["close"].pct_change()

    merged = curve_frame[["date", "strategy_return"]].merge(
        benchmark_frame[["date", "benchmark_return"]],
        on="date",
        how="inner",
    ).dropna()
    if len(merged) < 2:
        warnings.append("基准收益序列与策略收益序列重合样本不足，Alpha/Beta 暂无法计算。")
        return None, None

    strategy_var = float(merged["strategy_return"].var(ddof=1))
    if strategy_var <= 0 or not math.isfinite(strategy_var):
        warnings.append("策略收益序列波动为 0，Alpha/Beta 暂无法作为有效指标展示。")
        return None, None

    benchmark_var = float(merged["benchmark_return"].var(ddof=1))
    if benchmark_var <= 0 or not math.isfinite(benchmark_var):
        warnings.append("基准收益序列波动不足，Alpha/Beta 暂无法计算。")
        return None, None

    covariance = float(merged["strategy_return"].cov(merged["benchmark_return"]))
    beta = _finite_float(covariance / benchmark_var)
    benchmark_total = float(benchmark_frame["close"].iloc[-1] / benchmark_frame["close"].iloc[0] - 1)
    benchmark_annual = _annual_return(benchmark_total, len(benchmark_frame))
    alpha = None
    if beta is not None and annual_return is not None and benchmark_annual is not None:
        alpha = _finite_float(annual_return - beta * benchmark_annual)
    else:
        warnings.append("年化收益或基准年化收益不足，Alpha 暂无法计算。")
    return alpha, beta


def _empty_metrics(trade_count: int) -> dict[str, Any]:
    return {
        "total_return": None,
        "annual_return": None,
        "max_drawdown": None,
        "sharpe": None,
        "alpha": None,
        "beta": None,
        "volatility": None,
        "win_rate": None,
        "trade_count": trade_count,
        "turnover": None,
    }
