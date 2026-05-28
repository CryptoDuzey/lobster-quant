from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


BASE_URL = os.getenv("LOBSTER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


results: list[CheckResult] = []


def record(name: str, status: str, detail: str, **evidence: Any) -> None:
    results.append(CheckResult(name, status, detail, evidence))
    print(f"[{status}] {name}: {detail}")


def request_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str, params: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    return request_json("GET", f"{path}?{query}" if query else path, timeout=timeout)


def post_json(path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    return request_json("POST", path, payload=payload, timeout=timeout)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def curve_valid(curve: list[dict[str, Any]] | None) -> bool:
    if not isinstance(curve, list) or len(curve) < 2:
        return False
    values = [float(item.get("value")) for item in curve if finite(item.get("value"))]
    return len(values) >= 2 and abs(max(values) - min(values)) > 1e-10


def metric_signature(result: dict[str, Any]) -> tuple[Any, ...]:
    metrics = result.get("metrics") or {}
    keys = ("total_return", "annual_return", "max_drawdown", "sharpe", "alpha", "beta", "trade_count")
    signature: list[Any] = []
    for key in keys:
        value = metrics.get(key)
        signature.append(None if value is None else round(float(value), 8))
    return tuple(signature)


def check_services() -> None:
    started = time.perf_counter()
    openapi = get_json("/openapi.json", timeout=10)
    assert_true("/api/v1/backtest/run" in openapi.get("paths", {}), "后端接口清单缺少回测入口")
    record("后端在线", "PASS", f"接口文档可访问，用时 {int((time.perf_counter() - started) * 1000)}ms")


def check_market_data() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    search = get_json("/api/v1/market/search", {"keyword": "平安"}, timeout=30)
    items = search.get("items") or []
    assert_true(any(item.get("symbol") == "000001.XSHE" for item in items), "股票搜索没有返回平安银行")
    record("股票搜索", "PASS", f"返回 {len(items)} 条候选，来源 {search.get('source')}")

    params = {
        "symbol": "000001.XSHE",
        "period": "day",
        "start_date": "2025-01-01",
        "end_date": "2026-04-30",
        "adjust": "qfq",
    }
    bars = get_json("/api/v1/market/bars", params, timeout=90)
    rows = bars.get("bars") or []
    assert_true(len(rows) > 100, f"K线数量过少：{len(rows)}")
    assert_true(all(finite(row.get("close")) for row in rows[:20]), "K线 close 字段存在无效数字")
    assert_true(rows == sorted(rows, key=lambda item: item.get("time", "")), "K线时间不是升序")
    record("K线真实数据", "PASS", f"{bars.get('name')} 日线 {len(rows)} 条，来源 {bars.get('source')}")

    cached = get_json("/api/v1/market/bars", params, timeout=30)
    assert_true(cached.get("cache_hit") is True, "日线行情第二次请求没有命中本地缓存")
    record("行情缓存", "PASS", f"缓存返回 {cached.get('bars_count')} 条，来源 {cached.get('source')}")

    quote = get_json("/api/v1/market/quote", {"symbol": "000001.XSHE"}, timeout=30)
    assert_true(finite(quote.get("price")), "实时行情价格不是有效数字")
    record("实时行情快照", "PASS", f"价格 {quote.get('price')}，来源 {quote.get('source')}")
    return search, bars, quote


def check_agents(bars: dict[str, Any], quote: dict[str, Any]) -> None:
    hello = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "你好"}], "use_defaults": False},
        timeout=70,
    )
    assert_true(hello.get("conversation_only") is True, "策略对话没有进入普通聊天模式")
    assert_true(bool(hello.get("message")), "策略对话没有返回内容")
    record("策略对话基础能力", "PASS", f"来源 {hello.get('agent_source')}，模型配置={hello.get('provider_configured')}")

    factor = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "三因子选股"}], "use_defaults": False},
        timeout=30,
    )
    assert_true(factor.get("strategy_mode") == "factor_selection", "三因子选股没有进入多因子策略路径")
    record("Agent 意图识别", "PASS", "三因子选股被识别为多因子策略，不再串到模板策略")

    assistant = post_json(
        "/api/v1/agents/assistant-chat",
        {
            "session_id": "qa_smoke",
            "symbol": "000001.XSHE",
            "name": "平安银行",
            "query": "@技术面 分析一下当前走势",
            "period": "day",
            "quote": quote,
            "bars": (bars.get("bars") or [])[-120:],
            "news": [],
            "messages": [{"role": "user", "content": "@技术面 分析一下当前走势"}],
            "target_agents": ["technical"],
        },
        timeout=90,
    )
    assert_true(assistant.get("success") is True, assistant.get("message") or "AI助手失败")
    basis = assistant.get("basis") or {}
    assert_true(int(basis.get("bars_count") or 0) > 0, "AI助手没有使用真实K线作为依据")
    record("AI助手/Agent分析", "PASS", f"依据K线 {basis.get('bars_count')} 条")


def build_backtest_payload(chat: dict[str, Any], fallback_text: str) -> dict[str, Any]:
    strategy = chat.get("strategy") or {}
    strategy_json = strategy.get("strategy_json") or {}
    slots = chat.get("slots") or {}
    params = strategy_json.get("params") or {}
    return {
        "symbol": strategy_json.get("symbol") or slots.get("symbol") or "000001.XSHE",
        "period": strategy_json.get("period") or slots.get("period") or "day",
        "start_date": slots.get("start_date") or "2025-01-01",
        "end_date": slots.get("end_date") or "2026-04-30",
        "strategy_name": strategy.get("strategy_name") or strategy_json.get("strategy_name") or fallback_text[:24],
        "rules": strategy_json.get("rules") or {},
        "params": {
            **params,
            "initial_cash": params.get("initial_cash") or 1_000_000,
            "commission": params.get("commission") or 0.0003,
            "slippage": params.get("slippage") or 0.0005,
            "stamp_tax": params.get("stamp_tax") or 0.001,
            "t_plus_one": True,
            "round_lot": 100,
        },
    }


def run_strategy(text: str) -> dict[str, Any]:
    chat = post_json("/api/v1/agents/strategy-chat", {"messages": [{"role": "user", "content": text}]}, timeout=90)
    assert_true(chat.get("complete") is True, f"自然语言策略没有生成完整策略：{chat.get('message')}")
    strategy = chat.get("strategy") or {}
    assert_true(bool((strategy.get("strategy_json") or {}).get("rules")), "策略JSON缺少交易规则")
    assert_true(bool(strategy.get("generated_code")), "没有生成 rqalpha 策略代码")
    result = post_json("/api/v1/backtest/run", build_backtest_payload(chat, text), timeout=360)
    assert_true(result.get("success") is True, f"真实回测失败：{result.get('message')}")
    assert_true((result.get("data_info") or {}).get("is_mock") is False, "回测结果包含 mock 数据")
    assert_true(bool(result.get("strategy_hash")), "回测缺少 strategy_hash")
    assert_true(bool(result.get("code_hash")), "回测缺少 code_hash")
    assert_true((result.get("debug") or {}).get("executed_generated_code") is True, "后端没有确认执行生成策略")
    curves = result.get("curves") or {}
    assert_true(curve_valid(curves.get("strategy_curve")), "策略收益曲线无效")
    assert_true(curve_valid(curves.get("drawdown_curve")), "回撤曲线无效")
    benchmark = result.get("benchmark") or {}
    if benchmark.get("available"):
        assert_true(curve_valid(curves.get("benchmark_curve")), "基准可用但基准曲线无效")
        assert_true((result.get("metrics") or {}).get("alpha") is not None, "基准可用但 Alpha 缺失")
        assert_true((result.get("metrics") or {}).get("beta") is not None, "基准可用但 Beta 缺失")
    for trade in result.get("trades") or []:
        assert_true(
            re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", str(trade.get("time") or "")) is not None,
            f"交易时间不精确：{trade.get('time')}",
        )
    return result


def check_natural_language_backtests() -> None:
    cases = [
        "用平安银行，2025.1.1到2026.4.30，日线，5日均线上穿20日均线买入，下穿卖出，满仓，基准沪深300",
        "用平安银行，2025.1.1到2026.4.30，日线，RSI低于35买入，高于65卖出，满仓，基准沪深300",
        "用平安银行，2025.1.1到2026.4.30，日线，收盘价跌破布林带下轨买入，回到中轨卖出，满仓，基准沪深300",
    ]
    outputs = []
    for case in cases:
        result = run_strategy(case)
        metrics = result.get("metrics") or {}
        outputs.append(result)
        record(
            f"自然语言真实回测：{case[:18]}",
            "PASS",
            f"收益 {metrics.get('total_return')}，交易 {metrics.get('trade_count')} 次，数据 {result.get('data_info', {}).get('data_source')}",
        )
    assert_true(len({item.get("strategy_hash") for item in outputs}) == len(outputs), "不同策略产生了重复 strategy_hash")
    assert_true(len({metric_signature(item) for item in outputs}) == len(outputs), "不同策略核心指标完全相同，疑似没有真实执行不同策略")
    record("不同策略差异性", "PASS", "三类策略的 Hash 和核心指标均不同")


def check_data_boundaries() -> None:
    response = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "帮我生成一个XGBoost策略并给出回测收益"}], "use_defaults": True},
        timeout=30,
    )
    assert_true(response.get("unsupported_strategy_type") == "machine_learning", "XGBoost 未被能力边界拦截")
    record("机器学习边界", "PASS", "机器学习策略不会伪造成已回测结果")

    minute_text = "用平安银行，2025.1.1到2026.4.30，1分钟，09:31交易，5日均线上穿20日均线买入，下穿卖出"
    chat = post_json("/api/v1/agents/strategy-chat", {"messages": [{"role": "user", "content": minute_text}]}, timeout=90)
    if chat.get("complete") is True:
        result = post_json("/api/v1/backtest/run", build_backtest_payload(chat, minute_text), timeout=360)
        if result.get("success") is True:
            actual_start = ((result.get("time_range") or {}).get("actual_start") or "")[:10]
            assert_true(actual_start <= "2025-02-01", "分钟回测成功但实际数据没有覆盖请求区间")
            record("分钟级边界", "PASS", "分钟数据覆盖请求区间，回测成功")
        else:
            assert_true("分钟" in str(result.get("message", "")) or result.get("error_code"), "分钟回测失败但没有清晰错误")
            record("分钟级边界", "PASS", f"分钟历史不足时明确失败：{result.get('message')}")
    else:
        assert_true("分钟" in str(chat.get("message", "")) or chat.get("missing_slots"), "分钟策略没有给出清晰追问或边界")
        record("分钟级边界", "PASS", "分钟数据不足时不会伪造长期回测")


def main() -> int:
    try:
        check_services()
        _, bars, quote = check_market_data()
        check_agents(bars, quote)
        check_natural_language_backtests()
        check_data_boundaries()
    except Exception as exc:
        record("测试中断", "FAIL", str(exc))

    print("\n=== 汇总 ===")
    for item in results:
        print(f"{item.status:4} | {item.name} | {item.detail}")
    failed = [item for item in results if item.status == "FAIL"]
    warned = [item for item in results if item.status == "WARN"]
    print(f"\n通过 {len([r for r in results if r.status == 'PASS'])} 项，警告 {len(warned)} 项，失败 {len(failed)} 项。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
