from __future__ import annotations

import json
import sys
import time
import urllib.request
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


def post(path: str, payload: dict[str, Any], timeout: int = 420) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_generated_strategy(text: str, *, factor_limit: int | None = None) -> dict[str, Any]:
    chat = post(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": text}], "use_defaults": False},
        timeout=120,
    )
    require(chat.get("complete") is True, f"策略没有生成完整规格：{chat.get('message')}")
    strategy = chat.get("strategy") or {}
    strategy_json = strategy.get("strategy_json") or {}
    require(strategy_json.get("rules"), "策略缺少结构化规则")
    require(strategy.get("generated_code"), "策略缺少生成代码说明")
    params = {
        **(strategy_json.get("params") or {}),
        "initial_cash": 1_000_000,
        "commission": 0.0003,
        "slippage": 0.0005,
        "stamp_tax": 0.001,
    }
    if factor_limit:
        params["universe_limit"] = factor_limit
    slots = chat.get("slots") or {}
    payload = {
        "mode": strategy_json.get("mode", "single_stock"),
        "symbol": strategy_json.get("symbol") or slots.get("symbol") or "000001.XSHE",
        "start_date": slots.get("start_date") or "2025-01-01",
        "end_date": slots.get("end_date") or "2026-04-30",
        "period": strategy_json.get("period") or "day",
        "strategy_name": strategy.get("strategy_name") or strategy_json.get("strategy_name") or "自然语言策略",
        "rules": strategy_json.get("rules"),
        "params": params,
    }
    started = time.perf_counter()
    result = post("/api/v1/backtest/run", payload, timeout=420)
    elapsed = round(time.perf_counter() - started, 1)
    require(result.get("success") is True, f"回测失败：{result.get('message')}")
    require((result.get("data_info") or {}).get("is_mock") is False, "回测结果包含 mock 数据")
    require(result.get("strategy_hash"), "缺少策略指纹")
    require(result.get("code_hash"), "缺少代码指纹")
    require((result.get("debug") or {}).get("executed_generated_code") is True, "没有确认执行生成策略")
    curves = result.get("curves") or {}
    require(len(curves.get("strategy_curve") or []) >= 2, "缺少策略收益曲线")
    require(len(curves.get("drawdown_curve") or []) >= 2, "缺少回撤曲线")
    metrics = result.get("metrics") or {}
    print(
        f"PASS | {text[:28]} | engine={result.get('engine_info', {}).get('engine')} "
        f"return={metrics.get('total_return')} trades={metrics.get('trade_count')} elapsed={elapsed}s"
    )
    return result


def main() -> int:
    cases = [
        "用平安银行，2025.1.1到2026.4.30，日线，开盘9:31交易，突破20日新高且放量买入，跌破10日低点卖出，8%止损，满仓",
        "用平安银行，2025.1.1到2026.4.30，日线，MACD金叉买入，死叉卖出，满仓",
        "用平安银行，2025.1.1到2026.4.30，日线，20日动量为正且ATR放大买入，跌破30日均线卖出，6%止损",
    ]
    outputs = [run_generated_strategy(case) for case in cases]
    factor = run_generated_strategy(
        "用沪深300股票池，动量+低波动+成交额三个因子，每月调仓，选前10只，2025.1.1到2026.4.30回测",
        factor_limit=12,
    )
    signatures = {
        (
            item.get("strategy_hash"),
            (item.get("metrics") or {}).get("total_return"),
            (item.get("metrics") or {}).get("trade_count"),
        )
        for item in outputs
    }
    require(len(signatures) == len(outputs), "灵活策略结果出现重复，疑似仍在跑模板")
    require((factor.get("debug") or {}).get("mode") == "factor_selection", "多因子策略没有进入多因子实验回测")
    print("全部泛化策略检查通过。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL | {exc}")
        raise SystemExit(1)
