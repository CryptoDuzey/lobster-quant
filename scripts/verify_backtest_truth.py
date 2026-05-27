from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


API_URL = "http://127.0.0.1:8000/api/v1/backtest/run"


@dataclass(frozen=True)
class StrategyCase:
    name: str
    buy: str
    sell: str


CASES = [
    StrategyCase("5日20日双均线", "ma5 > ma20", "ma5 < ma20"),
    StrategyCase("RSI超跌反转", "rsi < 35", "rsi > 55"),
    StrategyCase("布林带均值回归", "close < bb_lower", "close > bb_mid"),
]


def run_case(case: StrategyCase) -> dict[str, Any]:
    payload = {
        "symbol": "000001.XSHE",
        "start_date": "2025-01-01",
        "end_date": "2026-04-30",
        "period": "day",
        "strategy_name": case.name,
        "rules": {
            "buy_rules": [{"description": case.name, "expression": case.buy}],
            "sell_rules": [{"description": case.name, "expression": case.sell}],
            "risk_rules": [],
        },
        "params": {
            "initial_cash": 1_000_000,
            "commission": 0.0003,
            "slippage": 0.0005,
            "stamp_tax": 0.001,
            "t_plus_one": True,
            "round_lot": 100,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"后端不可用，请先启动 FastAPI：{exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def metric_signature(result: dict[str, Any]) -> tuple[Any, ...]:
    metrics = result.get("metrics") or {}
    return (
        metrics.get("total_return"),
        metrics.get("annual_return"),
        metrics.get("alpha"),
        metrics.get("beta"),
        metrics.get("sharpe"),
        metrics.get("max_drawdown"),
        metrics.get("trade_count"),
    )


def main() -> int:
    results = []
    for case in CASES:
        result = run_case(case)
        require(result.get("success") is True, f"{case.name} 回测失败：{result.get('message')}")
        require((result.get("data_info") or {}).get("is_mock") is False, f"{case.name} 使用了 mock 数据")
        require(result.get("strategy_hash"), f"{case.name} 缺少策略 Hash")
        require(result.get("code_hash"), f"{case.name} 缺少代码 Hash")
        require((result.get("debug") or {}).get("executed_generated_code") is True, f"{case.name} 未确认执行策略代码")
        curves = result.get("curves") or {}
        require(len(curves.get("strategy_curve") or []) >= 2, f"{case.name} 缺少策略收益曲线")
        require(len(curves.get("drawdown_curve") or []) >= 2, f"{case.name} 缺少回撤曲线")
        benchmark = result.get("benchmark") or {}
        if benchmark.get("available"):
            require(len(curves.get("benchmark_curve") or []) >= 2, f"{case.name} 基准可用但缺少基准曲线")
        for trade in result.get("trades") or []:
            require(
                re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", str(trade.get("time") or "")) is not None,
                f"{case.name} trade time is not precise to seconds: {trade.get('time')}",
            )
        results.append((case, result))

    hashes = {item[1].get("strategy_hash") for item in results}
    signatures = {metric_signature(item[1]) for item in results}
    require(len(hashes) == len(results), "不同策略的 strategy_hash 出现重复")
    require(len(signatures) == len(results), "不同策略产生了完全相同的核心指标")

    print("回测真实性检查通过：")
    for case, result in results:
        metrics = result.get("metrics") or {}
        print(
            f"- {case.name}: 收益={metrics.get('total_return')}, "
            f"Alpha={metrics.get('alpha')}, Beta={metrics.get('beta')}, "
            f"Sharpe={metrics.get('sharpe')}, 交易={metrics.get('trade_count')}, "
            f"曲线来源={(result.get('debug') or {}).get('equity_curve_source')}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"回测真实性检查失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
