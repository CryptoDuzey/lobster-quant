from __future__ import annotations

import math
import os
import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.benchmark_service import BenchmarkService
from app.backtest.performance_metrics import build_standard_curves, compute_metrics
from app.backtest.result_auditor import BacktestResultAuditor
from app.backtest.result_normalizer import make_backtest_id, safe_json_response
from app.backtest.snapshot_service import SnapshotService
from app.data_providers.provider_router import get_market_provider


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _bars_to_frame(bars: list[Any]) -> pd.DataFrame:
    rows = [bar.to_dict() if hasattr(bar, "to_dict") else dict(bar) for bar in bars]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["time"], errors="coerce")
    for field in ["open", "high", "low", "close", "volume", "amount"]:
        if field in frame.columns:
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
    frame = frame.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date")
    frame["key"] = frame["date"].dt.strftime("%Y-%m-%d")
    return frame


def _feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    close = data["close"]
    volume = data["volume"].replace(0, np.nan)
    data["ret_1"] = close.pct_change(1)
    data["ret_3"] = close.pct_change(3)
    data["ret_5"] = close.pct_change(5)
    data["ret_10"] = close.pct_change(10)
    data["ret_20"] = close.pct_change(20)
    data["ma5_gap"] = close / close.rolling(5).mean() - 1
    data["ma20_gap"] = close / close.rolling(20).mean() - 1
    data["volatility_20"] = data["ret_1"].rolling(20).std()
    data["volume_ratio_20"] = volume / volume.rolling(20).mean() - 1
    data["intraday_range"] = (data["high"] - data["low"]) / close.replace(0, np.nan)
    data["next_return"] = close.shift(-1) / close - 1
    return data


def _ridge_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray, alpha: float = 1.0) -> float:
    if train_x.shape[0] < train_x.shape[1] + 5:
        return 0.0
    mean = train_x.mean(axis=0)
    std = train_x.std(axis=0)
    std[std == 0] = 1.0
    x = (train_x - mean) / std
    tx = (test_x - mean) / std
    x = np.column_stack([np.ones(len(x)), x])
    tx = np.concatenate([[1.0], tx])
    regularizer = np.eye(x.shape[1]) * alpha
    regularizer[0, 0] = 0.0
    try:
        weights = np.linalg.solve(x.T @ x + regularizer, x.T @ train_y)
    except np.linalg.LinAlgError:
        weights = np.linalg.pinv(x.T @ x + regularizer) @ x.T @ train_y
    return float(tx @ weights)


def run_ml_basic_backtest(request: Any, run_started_at: datetime) -> dict[str, Any]:
    params = request.params or {}
    period = str(request.period or "day")
    if period not in {"day", "1d"}:
        return {
            "success": False,
            "error_code": "ML_BASIC_ONLY_DAILY_READY",
            "message": "基础机器学习回测当前先支持日线。分钟级机器学习需要更完整的分钟历史缓存和更严格的训练/验证切分，系统不会用短分钟数据冒充长期训练结果。",
        }

    train_window = int(params.get("train_window") or 120)
    threshold = float(params.get("prediction_threshold") or 0.0)
    initial_cash = float(request.starting_cash)
    commission = float(request.commission)
    slippage = float(request.slippage)
    stamp_tax = float(request.stamp_tax)
    run_started = time.perf_counter()

    bars, data_source = get_market_provider().get_bars(
        request.stock_id,
        "day",
        request.start_date.isoformat(),
        request.end_date.isoformat(),
        os.getenv("LIVE_DATA_ADJUST", "qfq"),
    )
    raw_bars = [bar.to_dict() if hasattr(bar, "to_dict") else dict(bar) for bar in bars]
    frame = _feature_frame(_bars_to_frame(raw_bars))
    feature_cols = [
        "ret_1",
        "ret_3",
        "ret_5",
        "ret_10",
        "ret_20",
        "ma5_gap",
        "ma20_gap",
        "volatility_20",
        "volume_ratio_20",
        "intraday_range",
    ]
    model_frame = frame.dropna(subset=[*feature_cols, "next_return"]).copy()
    warnings: list[str] = [
        "基础机器学习回测为实验模块：使用历史OHLCV特征和滚动训练，不代表XGBoost、LSTM或深度学习已接入。",
        "模型只使用当时可见的历史数据预测下一交易日收益，避免用未来数据训练当前信号。",
    ]
    if len(model_frame) < train_window + 30:
        return {
            "success": False,
            "error_code": "ML_SAMPLE_INSUFFICIENT",
            "message": f"可训练样本不足：需要至少 {train_window + 30} 条日线样本，当前只有 {len(model_frame)} 条。",
            "warnings": warnings,
        }

    cash = initial_cash
    position = 0
    running_high = initial_cash
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []

    for idx in range(train_window, len(model_frame) - 1):
        train = model_frame.iloc[:idx]
        current = model_frame.iloc[idx]
        next_bar = model_frame.iloc[idx + 1]
        train_x = train[feature_cols].to_numpy(dtype=float)
        train_y = train["next_return"].to_numpy(dtype=float)
        test_x = current[feature_cols].to_numpy(dtype=float)
        predicted = _ridge_predict(train_x, train_y, test_x)
        predictions.append({"time": current["key"], "predicted_next_return": _safe_float(predicted)})

        trade_time = f"{next_bar['key']} 09:31:00"
        trade_price = float(next_bar["open"])
        close_price = float(next_bar["close"])
        if predicted > threshold and position == 0:
            price = trade_price * (1 + slippage)
            quantity = int(cash / price // 100 * 100)
            if quantity >= 100:
                gross = price * quantity
                fee = gross * commission
                if gross + fee <= cash:
                    cash -= gross + fee
                    position += quantity
                    trades.append(
                        {
                            "time": trade_time,
                            "date": str(next_bar["key"]),
                            "symbol": request.stock_id,
                            "name": get_market_provider().get_name(request.stock_id),
                            "direction": "BUY",
                            "price": _safe_float(price),
                            "quantity": quantity,
                            "amount": _safe_float(gross),
                            "fee": _safe_float(fee),
                            "status": "已成交",
                            "reason": f"基础ML预测下一期收益为 {predicted:.4%}，高于阈值 {threshold:.4%}",
                            "execution_precision": "daily_next_open",
                            "is_precise_intraday": False,
                            "time_note": "日线机器学习信号在下一交易日开盘附近估算成交，非分钟逐笔撮合。",
                        }
                    )
        elif predicted <= threshold and position > 0:
            price = trade_price * (1 - slippage)
            quantity = position
            gross = price * quantity
            fee = gross * (commission + stamp_tax)
            cash += gross - fee
            position = 0
            trades.append(
                {
                    "time": trade_time,
                    "date": str(next_bar["key"]),
                    "symbol": request.stock_id,
                    "name": get_market_provider().get_name(request.stock_id),
                    "direction": "SELL",
                    "price": _safe_float(price),
                    "quantity": quantity,
                    "amount": _safe_float(gross),
                    "fee": _safe_float(fee),
                    "status": "已成交",
                    "reason": f"基础ML预测下一期收益为 {predicted:.4%}，低于或等于阈值 {threshold:.4%}",
                    "execution_precision": "daily_next_open",
                    "is_precise_intraday": False,
                    "time_note": "日线机器学习信号在下一交易日开盘附近估算成交，非分钟逐笔撮合。",
                }
            )

        value = cash + position * close_price
        running_high = max(running_high, value)
        equity_curve.append(
            {
                "time": str(next_bar["key"]),
                "portfolio_value": _safe_float(value, 2),
                "return": _safe_float(value / initial_cash - 1),
                "drawdown": _safe_float(value / running_high - 1),
            }
        )

    actual_start = equity_curve[0]["time"]
    actual_end = equity_curve[-1]["time"]
    benchmark_result = BenchmarkService().get_default_benchmark(actual_start, actual_end)
    if benchmark_result.bars:
        benchmark_by_date = {row["time"]: row["close"] for row in benchmark_result.bars if row.get("close") is not None}
        start_close = None
        for row in equity_curve:
            close = benchmark_by_date.get(row["time"])
            if close and start_close is None:
                start_close = close
            row["benchmark_return"] = _safe_float(close / start_close - 1) if close and start_close else None

    metrics, metric_warnings = compute_metrics(equity_curve, trades, benchmark_result.bars, initial_cash)
    curves, curve_warnings = build_standard_curves(equity_curve)
    strategy_json = {
        "strategy_name": request.strategy_name or "基础机器学习择时策略",
        "strategy_type": "基础机器学习实验策略",
        "mode": "ml_basic",
        "symbol": request.stock_id,
        "period": "day",
        "rules": request.rules or {},
        "params": {
            **params,
            "strategy_mode": "ml_basic",
            "model_type": "rolling_ridge_linear",
            "feature_columns": feature_cols,
            "train_window": train_window,
            "prediction_threshold": threshold,
            "initial_cash": initial_cash,
            "commission": commission,
            "slippage": slippage,
            "stamp_tax": stamp_tax,
        },
    }
    strategy_code = (
        "ml_basic: rolling_ridge_linear; features="
        + ",".join(feature_cols)
        + f"; train_window={train_window}; threshold={threshold}"
    )
    snapshots = SnapshotService().build_snapshot(
        strategy_code=strategy_code,
        strategy_json=strategy_json,
        bars=raw_bars,
    )
    run_at_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    response = {
        "success": True,
        "backtest_id": make_backtest_id(f"ml_{request.stock_id}", run_at_id),
        "symbol": request.stock_id,
        "name": get_market_provider().get_name(request.stock_id),
        "period": "day",
        "strategy_name": strategy_json["strategy_name"],
        "benchmark": {
            "symbol": benchmark_result.symbol,
            "name": benchmark_result.name,
            "available": benchmark_result.available,
            "source": benchmark_result.source,
            "bars_count": len(benchmark_result.bars),
            "actual_start": benchmark_result.actual_start,
            "actual_end": benchmark_result.actual_end,
            "error": benchmark_result.error,
        },
        "time_range": {
            "requested_start": request.start_date.isoformat(),
            "requested_end": request.end_date.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "bars_count": len(equity_curve),
            "raw_bars_count": len(raw_bars),
        },
        "data_info": {
            "data_source": data_source,
            "benchmark_source": benchmark_result.source,
            "adjust": os.getenv("LIVE_DATA_ADJUST", "qfq"),
            "is_mock": False,
            "model_type": "rolling_ridge_linear",
            "feature_count": len(feature_cols),
            "train_window": train_window,
            "latency_ms": int((time.perf_counter() - run_started) * 1000),
        },
        "engine_info": {
            "engine": "ml_basic_vector_backtester",
            "engine_version": "mvp",
            "run_at": run_started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "cost_model": {
                "commission": commission,
                "slippage": slippage,
                "stamp_tax": stamp_tax,
                "round_lot": request.round_lot,
                "t_plus_one": True,
                "execution_time": "09:31:00",
            },
        },
        "metrics": metrics,
        "curves": curves,
        "bars": raw_bars,
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
            "equity_curve_source": "ml_basic_vector_portfolio",
            "prediction_samples": len(predictions),
        },
        "ai_audit": {
            "summary": "这是基础机器学习实验回测，已使用真实日线数据、滚动训练和真实交易成本生成结果；它不是XGBoost或深度学习结果。",
            "risks": [
                "样本量较小或市场状态变化时，滚动线性模型容易失效。",
                "当前只做单股多空择时，不等同于多因子股票池机器学习选股。",
                "未做严格样本外参数寻优和行业中性化。",
            ],
            "suggestions": [
                "增加训练/验证/测试分段和逐年表现检查。",
                "扩展到股票池横截面特征后，再考虑XGBoost或深度学习模型。",
                "对滑点、交易频率和持仓天数做压力测试。",
            ],
            "score": 50,
        },
    }
    response["trust_audit"] = BacktestResultAuditor().audit(response)
    return safe_json_response(response)
