from __future__ import annotations

import math
import os
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.backtest.benchmark_service import BenchmarkService
from app.backtest.performance_metrics import build_standard_curves, compute_metrics
from app.backtest.result_auditor import BacktestResultAuditor
from app.backtest.result_normalizer import make_backtest_id, safe_json_response, stable_hash
from app.backtest.snapshot_service import SnapshotService
from app.data.fundamental_macro_service import FACTOR_DIRECTIONS, FUNDAMENTAL_FACTORS, MACRO_FACTORS
from app.data.fundamental_macro_service import FinancialFactorService, MacroFactorService
from app.data_providers.provider_router import get_market_provider


POOL_CODE_MAP = {
    "CSI300": {"index": "000300", "name": "沪深300股票池", "benchmark": "000300.XSHG"},
    "CSI500": {"index": "000905", "name": "中证500股票池", "benchmark": "000905.XSHG"},
    "A_SHARE_SAMPLE": {"index": "000300", "name": "全A样本池", "benchmark": "000300.XSHG"},
}


DAILY_EXECUTION_NOTE = (
    "当前为日线股票池回测：调仓信号和成交价格来自日K数据，展示的盘中时间只是调仓调度标签，"
    "不代表真实1分钟逐笔撮合。若要验证09:31精确成交，需要接入分钟线股票池回测。"
)


def _normalize_symbol(code: str) -> str:
    code = str(code).strip().zfill(6)
    return f"{code}.XSHG" if code.startswith(("6", "9")) else f"{code}.XSHE"


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _load_pool_symbols(pool: str, limit: int) -> tuple[list[str], str, list[str]]:
    warnings: list[str] = []
    config = POOL_CODE_MAP.get(pool) or POOL_CODE_MAP["CSI300"]
    try:
        import akshare as ak

        frame = ak.index_stock_cons(config["index"])
        if frame is None or frame.empty:
            raise RuntimeError("指数成分接口返回空数据")
        code_col = "品种代码" if "品种代码" in frame.columns else "成分券代码"
        symbols = [_normalize_symbol(code) for code in frame[code_col].astype(str).tolist()]
    except Exception as exc:
        symbols = [
            "000001.XSHE",
            "600036.XSHG",
            "601318.XSHG",
            "600519.XSHG",
            "000858.XSHE",
            "300750.XSHE",
            "000333.XSHE",
            "002594.XSHE",
            "600030.XSHG",
            "688981.XSHG",
        ]
        warnings.append(f"股票池成分接口不可用，已改用内置A股样本池：{exc}")
    if limit and len(symbols) > limit:
        warnings.append(f"为控制本地演示耗时，本次使用股票池前 {limit} 只可获取样本；结果不能代表完整指数成分。")
        symbols = symbols[:limit]
    return symbols, config["name"], warnings


def _bars_to_frame(bars: list[Any]) -> pd.DataFrame:
    rows = [bar.to_dict() if hasattr(bar, "to_dict") else dict(bar) for bar in bars]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["time"], errors="coerce")
    for field in ["open", "high", "low", "close", "volume", "amount"]:
        if field in frame.columns:
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
    frame["amount"] = frame.get("amount", frame["close"] * frame["volume"])
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    frame["key"] = frame["date"].dt.strftime("%Y-%m-%d")
    return frame


def _fetch_symbol_frame(symbol: str, start_date: str, end_date: str) -> tuple[str, pd.DataFrame, str | None]:
    provider = get_market_provider()
    lookback_start = (pd.to_datetime(start_date) - timedelta(days=180)).strftime("%Y-%m-%d")
    bars, source = provider.get_bars(symbol, "day", lookback_start, end_date, os.getenv("LIVE_DATA_ADJUST", "qfq"))
    return symbol, _bars_to_frame(bars), source


def _technical_factor_values(frame: pd.DataFrame, trade_date: str, factors: list[str]) -> dict[str, float]:
    history = frame[frame["key"] <= trade_date].copy()
    if len(history) < 80:
        return {}
    close = history["close"]
    returns = close.pct_change()
    values: dict[str, float] = {}
    for factor in factors:
        if factor == "momentum_60":
            base = close.shift(60).iloc[-1]
            if base:
                values[factor] = float(close.iloc[-1] / base - 1)
        elif factor == "low_volatility_60":
            values[factor] = float(returns.tail(60).std())
        elif factor == "amount_20":
            values[factor] = float(history["amount"].tail(20).mean())
        elif factor == "rsi_14":
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, pd.NA)
            rsi = (100 - (100 / (1 + rs))).fillna(50)
            values[factor] = float(rsi.iloc[-1])
        elif factor == "ma_trend":
            values[factor] = float(close.rolling(20).mean().iloc[-1] / close.rolling(60).mean().iloc[-1] - 1)
    return {key: value for key, value in values.items() if math.isfinite(value)}


def _factor_values(
    symbol: str,
    frame: pd.DataFrame,
    trade_date: str,
    factors: list[str],
    financial_service: FinancialFactorService,
    macro_service: MacroFactorService,
    warning_keys: set[str],
    warnings: list[str],
) -> dict[str, float]:
    values = _technical_factor_values(frame, trade_date, factors)
    for factor in factors:
        if factor in FUNDAMENTAL_FACTORS:
            item = financial_service.get_asof(symbol, factor, trade_date)
            if item.value is not None:
                values[factor] = item.value
            elif item.warning:
                key = f"financial:{symbol}:{factor}:{item.warning}"
                if key not in warning_keys:
                    warning_keys.add(key)
                    warnings.append(item.warning)
        elif factor in MACRO_FACTORS:
            item = macro_service.get_asof(factor, trade_date)
            if item.value is not None:
                values[factor] = item.value
            elif item.warning:
                key = f"macro:{factor}:{item.warning}"
                if key not in warning_keys:
                    warning_keys.add(key)
                    warnings.append(item.warning)
    return values


def _rank_factor_scores(rows: list[tuple[str, dict[str, float]]], factors: list[str], warnings: list[str], warning_keys: set[str]) -> list[tuple[str, float]]:
    if not rows:
        return []
    scores = {symbol: [] for symbol, _ in rows}
    for factor in factors:
        if factor in MACRO_FACTORS:
            key = f"macro-score:{factor}"
            if key not in warning_keys:
                warning_keys.add(key)
                warnings.append(f"{factor} 是宏观因子，本次用于仓位/风险调节，不参与个股横截面排名。")
            continue
        values = [(symbol, item.get(factor)) for symbol, item in rows if item.get(factor) is not None and math.isfinite(float(item.get(factor)))]
        if len(values) < 2:
            key = f"coverage:{factor}"
            if key not in warning_keys:
                warning_keys.add(key)
                warnings.append(f"{factor} 有效样本不足，已从本次横截面打分中跳过。")
            continue
        lower_is_better = FACTOR_DIRECTIONS.get(factor) == "lower"
        values = sorted(values, key=lambda item: float(item[1]), reverse=not lower_is_better)
        denominator = max(1, len(values) - 1)
        for rank, (symbol, _) in enumerate(values):
            scores[symbol].append(1 - rank / denominator)
    ranked = [(symbol, sum(parts) / len(parts)) for symbol, parts in scores.items() if parts]
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def _macro_exposure_adjustment(macro_service: MacroFactorService, trade_date: str, factors: list[str], warnings: list[str], warning_keys: set[str]) -> float:
    if not any(factor in MACRO_FACTORS for factor in factors):
        return 1.0
    context = macro_service.get_context(trade_date)
    exposure = 1.0
    pmi = context.get("pmi")
    if pmi and pmi.value is not None and pmi.value < 50:
        exposure *= 0.75
    cpi = context.get("cpi_yoy")
    if cpi and cpi.value is not None and cpi.value > 3:
        exposure *= 0.85
    lpr = context.get("lpr1y")
    if lpr and lpr.value is not None and lpr.value > 4:
        exposure *= 0.9
    unavailable = [name for name, item in context.items() if item.warning]
    if unavailable:
        key = f"macro-context:{trade_date}:{','.join(unavailable)}"
        if key not in warning_keys:
            warning_keys.add(key)
            warnings.append(f"{trade_date} 宏观仓位调节数据不完整：{', '.join(unavailable)}。")
    return max(0.3, min(1.0, exposure))


def _rebalance_dates(calendar: list[str], rebalance: str) -> set[str]:
    frame = pd.DataFrame({"key": calendar})
    frame["date"] = pd.to_datetime(frame["key"])
    if rebalance == "daily":
        return set(calendar)
    if rebalance == "weekly":
        return set(frame.groupby(frame["date"].dt.to_period("W"))["key"].last().tolist())
    return set(frame.groupby(frame["date"].dt.to_period("M"))["key"].last().tolist())


def _available_calendar(frames: dict[str, pd.DataFrame], start_date: str, end_date: str) -> list[str]:
    date_sets: list[set[str]] = []
    for frame in frames.values():
        dates = set(frame[(frame["key"] >= start_date) & (frame["key"] <= end_date)]["key"].tolist())
        if dates:
            date_sets.append(dates)
    if not date_sets:
        return []
    return sorted(set().union(*date_sets))


def run_factor_selection_backtest(request: Any, run_started_at: datetime) -> dict[str, Any]:
    params = request.params or {}
    pool = str(params.get("stock_pool") or "CSI300")
    factors = list(params.get("factors") or ["momentum_60", "low_volatility_60", "amount_20"])
    top_n = int(params.get("top_n") or 10)
    rebalance = str(params.get("rebalance") or "monthly")
    universe_limit = int(params.get("universe_limit") or 80)
    start_date = request.start_date.isoformat()
    end_date = request.end_date.isoformat()
    initial_cash = float(request.starting_cash)
    commission = float(request.commission)
    slippage = float(request.slippage)
    stamp_tax = float(request.stamp_tax)
    run_started = time.perf_counter()
    financial_service = FinancialFactorService()
    macro_service = MacroFactorService()
    warning_keys: set[str] = set()

    symbols, pool_name, warnings = _load_pool_symbols(pool, universe_limit)
    if params.get("strategy_family") == "value_investing_proxy":
        warnings.append(
            "当前为巴菲特风格财务代理策略：已接入真实财务摘要中的ROE、成长、负债率和现金流质量；"
            "历史PE/PB/股息率仍未接入，不能等同于完整巴菲特基本面策略。"
        )
    elif params.get("strategy_family") in {"macro_reflexivity_proxy", "garp_proxy"}:
        warnings.append(
            f"当前为{params.get('strategy_family')}代理策略：会使用已接入的行情、财务或宏观因子；"
            "未覆盖该投资流派所需的全部外部数据，不能等同于原始大师策略。"
        )
    frames: dict[str, pd.DataFrame] = {}
    sources: set[str] = set()
    failed = 0
    for symbol in symbols:
        try:
            got_symbol, frame, source = _fetch_symbol_frame(symbol, start_date, end_date)
            if not frame.empty:
                frames[got_symbol] = frame
                if source:
                    sources.add(source)
        except Exception:
            failed += 1
    if len(frames) < max(3, min(top_n, 5)):
        return {
            "success": False,
            "error_code": "FACTOR_POOL_DATA_INSUFFICIENT",
            "message": f"股票池可用行情不足，无法完成多因子回测。成功获取 {len(frames)} 只，失败 {failed} 只。",
        }

    calendar = _available_calendar(frames, start_date, end_date)
    if len(calendar) < 40:
        return {"success": False, "error_code": "FACTOR_CALENDAR_INSUFFICIENT", "message": "股票池共同交易日期不足，无法完成多因子回测。"}
    rebalance_set = _rebalance_dates(calendar, rebalance)

    cash = initial_cash
    holdings: dict[str, int] = {}
    last_closes: dict[str, float] = {}
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    running_high = initial_cash
    execution_time = request.execution_time or "09:31:00"

    for key in calendar:
        closes: dict[str, float] = {}
        for symbol, frame in frames.items():
            today = frame.loc[frame["key"] == key]
            if not today.empty:
                close = float(today["close"].iloc[-1])
                closes[symbol] = close
                last_closes[symbol] = close
        if key in rebalance_set:
            factor_rows: list[tuple[str, dict[str, float]]] = []
            for symbol, frame in frames.items():
                if symbol not in closes:
                    continue
                values = _factor_values(symbol, frame, key, factors, financial_service, macro_service, warning_keys, warnings)
                if values:
                    factor_rows.append((symbol, values))
            scores = _rank_factor_scores(factor_rows, factors, warnings, warning_keys)
            selected = [symbol for symbol, _ in scores[:top_n]]
            for symbol, quantity in list(holdings.items()):
                if symbol not in selected and quantity > 0 and symbol in closes:
                    price = closes[symbol] * (1 - slippage)
                    gross = price * quantity
                    fee = gross * (commission + stamp_tax)
                    cash += gross - fee
                    trades.append({
                        "time": f"{key} {execution_time}",
                        "date": key,
                        "symbol": symbol,
                        "name": get_market_provider().get_name(symbol),
                        "direction": "SELL",
                        "price": _safe_float(price),
                        "quantity": quantity,
                        "amount": _safe_float(gross),
                        "fee": _safe_float(fee),
                        "time_source": "daily_bar_user_schedule",
                        "execution_precision": "daily_estimated",
                        "execution_label": "日线估算成交",
                        "price_source": "daily_bar",
                        "signal_source": "daily_bar",
                        "is_precise_intraday": False,
                        "time_note": DAILY_EXECUTION_NOTE,
                        "status": "已成交",
                        "reason": "调仓卖出：不在新一期多因子名单",
                    })
                    holdings.pop(symbol, None)
            if selected:
                macro_exposure = _macro_exposure_adjustment(macro_service, key, factors, warnings, warning_keys)
                total_value = cash + sum(holdings.get(sym, 0) * last_closes.get(sym, 0.0) for sym in holdings)
                target_value = total_value * macro_exposure / len(selected)
                for symbol in selected:
                    current_value = holdings.get(symbol, 0) * closes[symbol]
                    if current_value >= target_value * 0.8:
                        continue
                    budget = max(0.0, target_value - current_value)
                    price = closes[symbol] * (1 + slippage)
                    quantity = int(budget / price // 100 * 100)
                    if quantity >= 100:
                        gross = price * quantity
                        fee = gross * commission
                        if gross + fee <= cash:
                            cash -= gross + fee
                            holdings[symbol] = holdings.get(symbol, 0) + quantity
                            trades.append({
                                "time": f"{key} {execution_time}",
                                "date": key,
                                "symbol": symbol,
                                "name": get_market_provider().get_name(symbol),
                                "direction": "BUY",
                                "price": _safe_float(price),
                                "quantity": quantity,
                                "amount": _safe_float(gross),
                                "fee": _safe_float(fee),
                                "time_source": "daily_bar_user_schedule",
                                "execution_precision": "daily_estimated",
                                "execution_label": "日线估算成交",
                                "price_source": "daily_bar",
                                "signal_source": "daily_bar",
                                "is_precise_intraday": False,
                                "time_note": DAILY_EXECUTION_NOTE,
                                "status": "已成交",
                                "reason": "调仓买入：多因子综合排名入选",
                            })
        value = cash + sum(quantity * last_closes.get(symbol, 0.0) for symbol, quantity in holdings.items())
        running_high = max(running_high, value)
        equity_curve.append({
            "time": key,
            "portfolio_value": _safe_float(value, 2),
            "return": _safe_float(value / initial_cash - 1),
            "drawdown": _safe_float(value / running_high - 1),
        })

    actual_start = equity_curve[0]["time"]
    actual_end = equity_curve[-1]["time"]
    if actual_start != start_date or actual_end != end_date:
        warnings.append(
            f"请求回测区间为 {start_date} 至 {end_date}，真实可用行情区间为 {actual_start} 至 {actual_end}，本次已按真实可用数据执行。"
        )
    warnings.append(f"当前为日线回测，{execution_time} 只是调仓调度标签；成交价格按日K估算，非分钟线真实撮合。")
    benchmark_key = "CSI500" if pool == "CSI500" else "CSI300"
    benchmark_result = BenchmarkService().get_benchmark(benchmark_key, actual_start, actual_end)
    benchmark_bars = benchmark_result.bars
    if benchmark_bars:
        benchmark_by_date = {row["time"]: row["close"] for row in benchmark_bars if row.get("close") is not None}
        start_close = None
        for row in equity_curve:
            close = benchmark_by_date.get(row["time"])
            if close and start_close is None:
                start_close = close
            row["benchmark_return"] = _safe_float(close / start_close - 1) if close and start_close else None
    metrics, metric_warnings = compute_metrics(equity_curve, trades, benchmark_bars, initial_cash)
    curves, curve_warnings = build_standard_curves(equity_curve)
    strategy_json = {
        "strategy_name": request.strategy_name,
        "mode": "factor_selection",
        "symbols": symbols,
        "period": "day",
        "rules": request.rules,
        "params": params,
    }
    snapshots = SnapshotService().build_snapshot(
        strategy_code=f"factor_selection:{pool}:{factors}:{rebalance}:{top_n}",
        strategy_json=strategy_json,
        bars=[{"time": row["time"], "portfolio_value": row["portfolio_value"]} for row in equity_curve],
    )
    run_at_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    response = {
        "success": True,
        "backtest_id": make_backtest_id(f"factor_{pool}", run_at_id),
        "symbol": request.stock_id,
        "name": pool_name,
        "period": "day",
        "strategy_name": request.strategy_name,
        "benchmark": {
            "symbol": benchmark_result.symbol,
            "name": benchmark_result.name,
            "available": benchmark_result.available,
            "source": benchmark_result.source,
            "bars_count": len(benchmark_bars),
            "actual_start": benchmark_result.actual_start,
            "actual_end": benchmark_result.actual_end,
            "error": benchmark_result.error,
        },
        "time_range": {
            "requested_start": start_date,
            "requested_end": end_date,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "bars_count": len(equity_curve),
        },
        "data_info": {
            "data_source": "+".join(sorted(sources)) or "akshare",
            "benchmark_source": benchmark_result.source,
            "benchmark_symbol": benchmark_result.symbol,
            "benchmark_name": benchmark_result.name,
            "benchmark_bars_count": len(benchmark_bars),
            "adjust": os.getenv("LIVE_DATA_ADJUST", "qfq"),
            "is_mock": False,
            "stock_pool": pool,
            "factors": factors,
            "fundamental_factors": [factor for factor in factors if factor in FUNDAMENTAL_FACTORS],
            "macro_factors": [factor for factor in factors if factor in MACRO_FACTORS],
            "financial_factor_source": "akshare_stock_financial_abstract" if any(factor in FUNDAMENTAL_FACTORS for factor in factors) else "",
            "macro_factor_source": "akshare_macro" if any(factor in MACRO_FACTORS for factor in factors) else "",
            "symbols_count": len(frames),
            "failed_symbols_count": failed,
            "latency_ms": int((time.perf_counter() - run_started) * 1000),
        },
        "engine_info": {
            "engine": "factor_vector_backtester",
            "engine_version": "mvp",
            "run_at": run_started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "cost_model": {
                "commission": commission,
                "slippage": slippage,
                "stamp_tax": stamp_tax,
                "round_lot": request.round_lot,
                "t_plus_one": True,
                "execution_time": execution_time,
            },
            "execution_model": {
                "granularity": "day",
                "precision": "daily_estimated",
                "label": "日线估算成交",
                "price_source": "daily_bar",
                "signal_source": "daily_bar",
                "requested_execution_time": execution_time,
                "is_precise_intraday": False,
                "note": DAILY_EXECUTION_NOTE,
            },
        },
        "metrics": metrics,
        "curves": curves,
        "bars": [],
        "trades": trades,
        "warnings": [*warnings, *benchmark_result.warnings, *metric_warnings, *curve_warnings],
        "strategy_json": strategy_json,
        "strategy_hash": snapshots["strategy_hash"],
        "code_hash": snapshots["code_hash"],
        "config_hash": snapshots["config_hash"],
        "strategy_code_hash": snapshots["strategy_code_hash"],
        "config_snapshot_hash": snapshots["config_snapshot_hash"],
        "data_hash": snapshots["data_hash"],
        "debug": {
            "received_strategy_json": bool(request.rules),
            "executed_generated_code": True,
            "cache_hit": False,
            "equity_curve_source": "factor_vector_portfolio",
            "mode": "factor_selection",
        },
        "execution_logs": [
            {"time": trade["time"], "level": "调仓", "message": f"{trade['name']} {trade['direction']} {trade['quantity']} 股"}
            for trade in trades[:200]
        ],
        "ai_audit": {
            "summary": "这是多因子实验回测结果，使用真实行情和组合调仓计算。请重点检查股票池样本、调仓频率、交易成本和样本外稳定性。",
            "risks": ["多因子模块仍处于实验阶段，默认限制了股票池样本数量以控制本地运行耗时。", "因子未做行业中性化和停牌/涨跌停完整处理。"],
            "suggestions": ["扩大股票池并做分年度表现检查。", "增加行业约束、成交额过滤和样本外验证。"],
            "score": 55,
        },
    }
    response["trust_audit"] = BacktestResultAuditor().audit(response)
    return safe_json_response(response)
