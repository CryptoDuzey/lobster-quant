from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


BASE_URL = "http://127.0.0.1:8000"


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
    suffix = f"{path}?{query}" if query else path
    return request_json("GET", suffix, timeout=timeout)


def post_json(path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    return request_json("POST", path, payload=payload, timeout=timeout)


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def curve_valid(curve: list[dict[str, Any]] | None) -> bool:
    if not isinstance(curve, list) or len(curve) < 2:
        return False
    values = [float(item.get("value")) for item in curve if finite(item.get("value"))]
    if len(values) < 2:
        return False
    return abs(max(values) - min(values)) > 1e-10


def metric_signature(result: dict[str, Any]) -> tuple[Any, ...]:
    metrics = result.get("metrics") or {}
    return (
        round(float(metrics.get("total_return", 0)), 8),
        round(float(metrics.get("annual_return", 0)), 8),
        round(float(metrics.get("max_drawdown", 0)), 8),
        round(float(metrics.get("sharpe", 0)), 8),
        round(float(metrics.get("alpha", 0)), 8) if metrics.get("alpha") is not None else None,
        round(float(metrics.get("beta", 0)), 8) if metrics.get("beta") is not None else None,
        int(metrics.get("trade_count") or 0),
    )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_services() -> None:
    started = time.perf_counter()
    openapi = get_json("/openapi.json", timeout=10)
    assert_true("/api/v1/backtest/run" in openapi.get("paths", {}), "后端接口清单缺少回测入口")
    record("后端在线", "PASS", f"接口文档可访问，用时 {int((time.perf_counter() - started) * 1000)}ms")


def check_market_data() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    search = get_json("/api/v1/market/search", {"keyword": "平安"}, timeout=30)
    items = search.get("items") or []
    assert_true(any(item.get("symbol") == "000001.XSHE" for item in items), "股票搜索没有返回平安银行")
    record("股票搜索", "PASS", f"返回 {len(items)} 条候选", source=search.get("source"))

    bars = get_json(
        "/api/v1/market/bars",
        {
            "symbol": "000001.XSHE",
            "period": "day",
            "start_date": "2025-01-01",
            "end_date": "2026-04-30",
            "adjust": "qfq",
        },
        timeout=90,
    )
    rows = bars.get("bars") or []
    assert_true(len(rows) > 100, f"K 线数量过少：{len(rows)}")
    assert_true(all(finite(row.get("close")) for row in rows[:20]), "K 线 close 字段存在非数字")
    assert_true(rows == sorted(rows, key=lambda item: item.get("time", "")), "K 线时间不是升序")
    record("K线真实数据", "PASS", f"{bars.get('name')} 日线 {len(rows)} 条，来源 {bars.get('source')}", latency_ms=bars.get("latency_ms"))

    quote = get_json("/api/v1/market/quote", {"symbol": "000001.XSHE"}, timeout=30)
    assert_true(finite(quote.get("price")), "实时行情价格不是有效数字")
    record("实时行情快照", "PASS", f"价格 {quote.get('price')}，来源 {quote.get('source')}", timestamp=quote.get("timestamp"))
    return search, bars, quote


def check_news() -> dict[str, Any]:
    try:
        news = get_json("/api/v1/news/stock", {"symbol": "000001.XSHE", "limit": 6}, timeout=45)
    except Exception as exc:
        record("消息面推送", "WARN", f"消息接口暂时不可用：{exc}")
        return {"items": []}
    items = news.get("items") or []
    if not items:
        record("消息面推送", "WARN", "接口可访问，但当前没有返回新闻")
        return news
    real_links = [item for item in items if str(item.get("url") or "").startswith(("http://", "https://"))]
    if real_links:
        record("消息面推送", "PASS", f"返回 {len(items)} 条，含 {len(real_links)} 条可溯源链接", source=news.get("source"))
    else:
        record("消息面推送", "WARN", f"返回 {len(items)} 条，但没有可点击来源链接", source=news.get("source"))
    return news


def check_agents(bars: dict[str, Any], quote: dict[str, Any], news: dict[str, Any]) -> None:
    hello = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "你好"}], "use_defaults": False},
        timeout=70,
    )
    assert_true(hello.get("conversation_only") is True, "策略对话没有进入普通聊天模式")
    assert_true(bool(hello.get("message")), "策略对话没有返回内容")
    record("策略对话基础能力", "PASS", f"来源 {hello.get('agent_source')}，DeepSeek配置={hello.get('provider_configured')}")

    factor = post_json(
        "/api/v1/agents/strategy-chat",
        {
            "messages": [
                {"role": "user", "content": "帮我生成一个XGBoost策略，并给我回测结果摘要"},
                {"role": "assistant", "content": "不能生成假的 XGBoost 回测结果"},
                {"role": "user", "content": "三因子选股"},
            ],
            "use_defaults": False,
        },
        timeout=30,
    )
    assert_true(factor.get("strategy_mode") == "factor_selection", "三因子选股被误判，没有进入多因子策略引导")
    assert_true("XGBoost" not in str(factor.get("message", "")).splitlines()[0], "三因子选股首句仍被 XGBoost 上下文污染")
    record("Agent意图识别", "PASS", "三因子选股不会被旧的 XGBoost 上下文带偏")

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
            "news": news.get("items") or [],
            "messages": [{"role": "user", "content": "@技术面 分析一下当前走势"}],
            "target_agents": ["technical"],
        },
        timeout=70,
    )
    assert_true(assistant.get("success") is True, assistant.get("message") or "AI 助手失败")
    basis = assistant.get("basis") or {}
    assert_true(int(basis.get("bars_count") or 0) > 0, "AI 助手没有带真实 K 线作为依据")
    record("AI助手/Agent分析", "PASS", f"模式 {assistant.get('agent_mode')}，依据K线 {basis.get('bars_count')} 条")


def strategy_chat_to_backtest(text: str) -> dict[str, Any]:
    chat = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": text}], "use_defaults": False},
        timeout=90,
    )
    assert_true(chat.get("complete") is True, f"自然语言策略没有生成完整策略：{chat.get('message')}")
    strategy = chat.get("strategy") or {}
    strategy_json = strategy.get("strategy_json") or {}
    slots = chat.get("slots") or {}
    assert_true(bool(strategy_json.get("rules")), "策略 JSON 缺少交易规则")
    assert_true(bool(strategy.get("generated_code")), "没有生成 rqalpha 策略代码")

    payload = {
        "symbol": strategy_json.get("symbol") or slots.get("symbol") or "000001.XSHE",
        "period": strategy_json.get("period") or slots.get("period") or "day",
        "start_date": slots.get("start_date") or "2025-01-01",
        "end_date": slots.get("end_date") or "2026-04-30",
        "strategy_name": strategy.get("strategy_name") or strategy_json.get("strategy_name") or text[:24],
        "rules": strategy_json.get("rules") or {},
        "params": {
            **(strategy_json.get("params") or {}),
            "initial_cash": (strategy_json.get("params") or {}).get("initial_cash") or 1_000_000,
            "commission": (strategy_json.get("params") or {}).get("commission") or 0.0003,
            "slippage": (strategy_json.get("params") or {}).get("slippage") or 0.0005,
            "stamp_tax": 0.001,
            "t_plus_one": True,
            "round_lot": 100,
        },
    }
    result = post_json("/api/v1/backtest/run", payload, timeout=360)
    assert_true(result.get("success") is True, f"真实回测失败：{result.get('message')}")
    assert_true((result.get("data_info") or {}).get("is_mock") is False, "回测结果包含 mock 数据")
    assert_true(bool(result.get("strategy_hash")), "回测缺少 strategy_hash")
    assert_true(bool(result.get("code_hash")), "回测缺少 code_hash")
    debug = result.get("debug") or {}
    assert_true(debug.get("executed_generated_code") is True, "后端没有确认执行生成代码")
    curves = result.get("curves") or {}
    assert_true(curve_valid(curves.get("strategy_curve")), "策略收益曲线无效")
    assert_true(curve_valid(curves.get("drawdown_curve")), "回撤曲线无效")
    benchmark = result.get("benchmark") or {}
    if benchmark.get("available"):
        assert_true(curve_valid(curves.get("benchmark_curve")), "基准可用但基准曲线无效")
        metrics = result.get("metrics") or {}
        assert_true(metrics.get("alpha") is not None and metrics.get("beta") is not None, "基准可用但 Alpha/Beta 缺失")
    for trade in result.get("trades") or []:
        assert_true(
            re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", str(trade.get("time") or "")) is not None,
            f"交易时间不精确：{trade.get('time')}",
        )
    return {"chat": chat, "backtest": result}


def check_natural_language_backtests() -> None:
    cases = [
        "用平安银行，2025.1.1到2026.4.30，日线，开盘9:31交易，5日均线上穿20日均线买入，下穿卖出，满仓",
        "用平安银行，2025.1.1到2026.4.30，日线，RSI低于35买入，高于55卖出，满仓",
        "用平安银行，2025.1.1到2026.4.30，日线，收盘价跌破布林带下轨买入，回到布林带中轨卖出，满仓",
    ]
    outputs = []
    for case in cases:
        item = strategy_chat_to_backtest(case)
        bt = item["backtest"]
        metrics = bt.get("metrics") or {}
        outputs.append(item)
        record(
            f"自然语言真实回测：{case[:18]}",
            "PASS",
            f"收益 {metrics.get('total_return')}，交易 {metrics.get('trade_count')} 次，数据 {bt.get('data_info', {}).get('data_source')}",
            strategy_hash=bt.get("strategy_hash"),
            code_hash=bt.get("code_hash"),
        )
    hashes = {item["backtest"].get("strategy_hash") for item in outputs}
    signatures = {metric_signature(item["backtest"]) for item in outputs}
    assert_true(len(hashes) == len(outputs), "不同自然语言策略产生了重复 strategy_hash")
    assert_true(len(signatures) == len(outputs), "不同自然语言策略核心指标完全相同，疑似没有真实执行不同策略")
    record("不同策略差异性", "PASS", "三类策略的 Hash 和核心指标均不同")


def check_unsupported_boundaries() -> None:
    ml = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "帮我生成一个XGBoost策略并给出回测收益"}], "use_defaults": True},
        timeout=30,
    )
    assert_true(ml.get("unsupported_strategy_type") == "machine_learning", "XGBoost 未被能力边界拦截")
    assert_true("年化收益" not in str(ml.get("message", ""))[:80], "XGBoost 回复前段疑似仍在给收益结果")
    record("机器学习边界", "PASS", "XGBoost 不会伪装成已回测能力")

    factor = post_json(
        "/api/v1/agents/strategy-chat",
        {"messages": [{"role": "user", "content": "三因子选股"}], "use_defaults": False},
        timeout=30,
    )
    assert_true(factor.get("strategy_mode") == "factor_selection", "多因子策略没有明确进入实验/规划路径")
    if factor.get("complete") is True:
        record("多因子边界", "PASS", "完整多因子描述可进入实验回测；信息不足时仍会先追问")
    else:
        record("多因子边界", "PASS", "信息不足的多因子请求会进入追问，不再误判为模板策略")


def main() -> int:
    try:
        check_services()
        _, bars, quote = check_market_data()
        news = check_news()
        check_agents(bars, quote, news)
        check_natural_language_backtests()
        check_unsupported_boundaries()
    except urllib.error.URLError as exc:
        record("测试中断", "FAIL", f"服务不可用或网络请求失败：{exc}")
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
