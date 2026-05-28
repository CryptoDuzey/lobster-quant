from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auth.security import decrypt_secret
from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

DEEPSEEK_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


class StrategyIdeas(BaseModel):
    buy_idea: str = ""
    sell_idea: str = ""
    risk_idea: str = ""


class AuditRequest(BaseModel):
    symbol: str
    name: str = ""
    strategy_name: str = ""
    strategy: StrategyIdeas | dict[str, Any] = Field(default_factory=dict)
    period: str = "day"
    metrics: dict[str, Any] = Field(default_factory=dict)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    market_context: dict[str, Any] = Field(default_factory=dict)


class StrategyRequest(BaseModel):
    symbol: str = "000001.XSHE"
    universe: str = "single_stock"
    period: str = "day"
    start_date: str = "2025-01-01"
    end_date: str = "2026-03-01"
    idea: str = ""
    user_input: str = ""
    framework: dict[str, Any] = Field(default_factory=dict)


class AiStockSearchRequest(BaseModel):
    query: str
    limit: int = 20


class StockAnalysisRequest(BaseModel):
    symbol: str
    name: str = ""
    question: str = ""
    period: str = "1m"
    selected_range: dict[str, Any] | None = None
    quote: dict[str, Any] = Field(default_factory=dict)
    bars: list[dict[str, Any]] = Field(default_factory=list)
    news: list[dict[str, Any]] = Field(default_factory=list)


class StrategyDebugRequest(BaseModel):
    strategy_json: dict[str, Any] = Field(default_factory=dict)
    generated_code: str = ""
    error_message: str = ""
    runtime_context: dict[str, Any] = Field(default_factory=dict)


STRATEGY_AGENT_PROMPT = """
你是龙虾量化系统中的 A 股量化策略生成 Agent。

当前系统使用 FastAPI + rqalpha + 自定义 LiveStockDataSource + akshare / 东方财富数据源，不使用 BigQuant，不使用 BigTrader。

你的任务不是泛泛解释策略，而是根据用户输入生成结构化策略 JSON，必要时生成安全、稳定、可运行的 rqalpha 策略代码。

最高优先级：
第一，代码能够稳定运行；
第二，数据范围正确；
第三，策略逻辑符合用户意图；
第四，结果展示完整。

必须遵守：
1. 先识别策略类型：单只股票、股票池、多因子选股。
2. 如果用户没有明确说股票池，默认按单只股票策略处理。
3. 单只股票策略只能使用一个 symbol，不允许自动扩展全市场。
4. 股票代码必须统一格式，不允许混用裸代码和带后缀代码。
5. 数据为空时禁止进入 rqalpha 回测。
6. 技术指标必须在代码中明确计算，不能引用未生成字段。
7. 所有窗口参数、资金参数、手续费、滑点、日期必须是有效值，不能是空字符串。
8. 必须处理 NaN、Inf、历史窗口不足、无交易、无持仓卖出、已有持仓重复买入等情况。
9. 必须遵守 A 股 T+1 和 100 股一手交易约束。
10. 不允许使用未来函数。
11. 不允许直接执行用户原始自然语言。
12. 不允许生成危险代码、文件删除代码、网络攻击代码或系统命令。
13. 不允许残留上一轮策略中的变量、字段、股票代码、指标。
14. 输出必须中文。
15. 如果生成代码，请只生成本次策略需要的代码，不要加入无关模块。
"""


THEME_STOCKS = {
    "中字头央企": [
        ("601398.XSHG", "工商银行", "大型国有银行，具备央企和高股息属性"),
        ("601857.XSHG", "中国石油", "中字头能源央企"),
        ("600028.XSHG", "中国石化", "中字头能源央企"),
        ("601888.XSHG", "中国中免", "消费央企龙头"),
        ("601988.XSHG", "中国银行", "大型国有银行"),
    ],
    "银行股": [
        ("000001.XSHE", "平安银行", "股份制银行代表，流动性较好"),
        ("600036.XSHG", "招商银行", "股份制银行龙头"),
        ("601398.XSHG", "工商银行", "国有大行代表"),
        ("601988.XSHG", "中国银行", "国有大行代表"),
    ],
    "半导体": [
        ("688981.XSHG", "中芯国际", "晶圆制造龙头"),
        ("603986.XSHG", "兆易创新", "存储与 MCU 芯片公司"),
        ("002371.XSHE", "北方华创", "半导体设备龙头"),
    ],
    "新能源": [
        ("300750.XSHE", "宁德时代", "动力电池龙头"),
        ("002594.XSHE", "比亚迪", "新能源车与电池龙头"),
        ("601012.XSHG", "隆基绿能", "光伏龙头"),
    ],
    "机器人": [
        ("300124.XSHE", "汇川技术", "工业自动化与伺服系统龙头"),
        ("002230.XSHE", "科大讯飞", "AI 与机器人交互相关"),
        ("002747.XSHE", "埃斯顿", "工业机器人公司"),
    ],
    "高股息": [
        ("601398.XSHG", "工商银行", "高股息低估值代表"),
        ("600900.XSHG", "长江电力", "水电高分红资产"),
        ("601088.XSHG", "中国神华", "煤炭高股息代表"),
    ],
}


def deepseek_key(required: bool = True) -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip() or _stored_api_key("deepseek")
    if required and not key:
        raise HTTPException(status_code=503, detail="missing DEEPSEEK_API_KEY")
    return key


def _stored_api_key(provider: str) -> str:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT encrypted_api_key FROM api_keys
                WHERE provider = ? AND is_active = 1
                ORDER BY user_id DESC, id DESC
                LIMIT 1
                """,
                (provider,),
            ).fetchone()
        if not row:
            return ""
        return decrypt_secret(row["encrypted_api_key"])
    except Exception:
        return ""


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def chat_json(system_prompt: str, user_payload: dict[str, Any], temperature: float = 0.2) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {deepseek_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return extract_json(content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek request failed: {exc}") from exc


def _local_stock_search(query: str, limit: int) -> dict[str, Any]:
    key = (query or "").strip()
    matched: list[tuple[str, str, str]] = []
    for theme, stocks in THEME_STOCKS.items():
        if key and (key in theme or theme in key):
            matched.extend(stocks)
    if not matched:
        if any(token in key for token in ["央企", "中特估", "中字", "低估值"]):
            matched.extend(THEME_STOCKS["中字头央企"])
        elif any(token in key for token in ["芯片", "半导体", "国产替代"]):
            matched.extend(THEME_STOCKS["半导体"])
        elif any(token in key for token in ["电池", "光伏", "新能源"]):
            matched.extend(THEME_STOCKS["新能源"])
        elif any(token in key for token in ["银行", "股息", "红利", "高息"]):
            matched.extend(THEME_STOCKS["银行股"] + THEME_STOCKS["高股息"])
        elif any(token in key for token in ["机器人", "自动化"]):
            matched.extend(THEME_STOCKS["机器人"])
    if not matched:
        matched = THEME_STOCKS["中字头央企"] + THEME_STOCKS["银行股"]
    dedup: dict[str, dict[str, Any]] = {}
    for symbol, name, reason in matched:
        code, exchange = symbol.split(".", 1)
        dedup[symbol] = {
            "symbol": symbol,
            "code": code,
            "name": name,
            "exchange": "上交所" if exchange == "XSHG" else "深交所",
            "reason": reason,
        }
    return {
        "query": query,
        "items": list(dedup.values())[:limit],
        "source": "本地语义候选",
        "notice": "模型 API Key 未配置时使用本地主题候选，不代表投资建议。",
    }


def _local_stock_analysis(request: StockAnalysisRequest) -> dict[str, Any]:
    quote = request.quote or {}
    bars = request.bars or []
    if len(bars) < 2:
        return {
            "success": False,
            "message": "缺少真实行情数据，暂无法生成个股分析",
            "basis": {
                "quote_time": quote.get("timestamp") or "",
                "bars_count": len(bars),
                "news_count": len(request.news or []),
                "data_source": quote.get("source") or "",
            },
        }
    latest = bars[-1] if bars else {}
    previous = bars[-2] if len(bars) > 1 else latest
    change_pct = quote.get("change_pct")
    if change_pct is None and latest and previous and previous.get("close"):
        change_pct = (float(latest.get("close", 0)) - float(previous.get("close", 0))) / float(previous.get("close", 1)) * 100
    trend = "偏强" if (change_pct or 0) >= 0 else "偏弱"
    summary = (
        f"{request.name or request.symbol} 当前短线表现{trend}，最新涨跌幅约为 {float(change_pct or 0):.2f}%。"
        f"系统已结合最近 {len(bars)} 根K线和 {len(request.news or [])} 条消息做快速判断。"
        "这不是确定性买卖建议，仍需要观察成交量、关键价位和市场整体风险。"
    )
    return {
        "success": True,
        "symbol": request.symbol,
        "name": request.name,
        "basis_meta": {
            "quote_time": quote.get("timestamp") or latest.get("time", ""),
            "bars_count": len(bars),
            "news_count": len(request.news or []),
            "data_source": quote.get("source") or "",
        },
        "summary": summary,
        "basis": [
            "依据当前行情快照、最近K线和消息数量做本地快速分析。",
            "配置可用模型 Key 后，将生成更完整的中文投研分析。",
        ],
        "risks": ["样本窗口较短，分钟级波动容易受盘口噪声影响。", "消息面可能存在滞后或缺失。"],
        "suggestions": ["关注是否有效突破前高。", "避免仅凭单一消息或单根K线追涨。"],
        "source": "本地分析",
    }


def _fallback_strategy(request: StrategyRequest) -> dict[str, Any]:
    framework = request.framework or {}
    buy_description = framework.get("buy") or "价格强于 MA20 且波动率放大"
    sell_description = framework.get("sell") or "价格跌破 MA20"
    risk_description = framework.get("stop") or "持仓回撤超过 8% 时止损"
    return {
        "strategy_name": "MA20 成交量突破策略",
        "strategy_type": "单股趋势策略",
        "symbol": request.symbol,
        "period": request.period,
        "rules": {
            "buy_rules": [
                {"id": "buy_001", "description": buy_description, "expression": "close > ma20"},
                {"id": "buy_002", "description": "成交量相对20日均量放大", "expression": "volume > volume_ma20 * 1.2"},
            ],
            "sell_rules": [
                {"id": "sell_001", "description": sell_description, "expression": "close < ma20"},
            ],
            "risk_rules": [
                {"id": "risk_001", "description": risk_description, "expression": "drawdown > 0.08"},
            ],
        },
        "params": {
            "initial_cash": 1000000,
            "commission": 0.0003,
            "slippage": 0.0005,
            "t_plus_one": True,
            "round_lot": 100,
            "ma_window": 20,
            "atr_window": 14,
            "max_drawdown_limit": 0.08,
        },
        "explanation": "模型 API Key 未配置时，系统使用本地安全模板完成结构化。该策略仅用于跑通流程，正式投研请配置可用模型 Key。",
        "source": "本地结构化兜底",
    }


@router.post("/audit")
def audit_strategy(request: AuditRequest) -> dict[str, Any]:
    return audit_backtest(request)


@router.post("/backtest/audit")
def audit_backtest(request: AuditRequest) -> dict[str, Any]:
    result = chat_json(
        (
            "你是A股量化投研风控负责人。只返回JSON。必须使用中文，必须基于收益率、最大回撤、夏普率、"
            "Alpha、Beta、胜率、交易次数等指标分析，不要承诺盈利，不要写鸡汤。"
            "JSON字段：summary字符串、strengths字符串数组、risks字符串数组、suggestions字符串数组、score数字。"
        ),
        {
            "symbol": request.symbol,
            "name": request.name,
            "strategy_name": request.strategy_name,
            "period": request.period,
            "strategy": request.strategy,
            "metrics": request.metrics,
            "trades": request.trades[:30],
            "market_context": request.market_context,
        },
    )
    return {
        "summary": result.get("summary", ""),
        "strengths": result.get("strengths", []),
        "risks": result.get("risks", []),
        "suggestions": result.get("suggestions", []),
        "score": result.get("score", 60),
    }


@router.post("/strategy")
def generate_strategy(request: StrategyRequest) -> dict[str, Any]:
    result = parse_strategy(request)
    rules = result.get("rules") or {}
    return {
        "name": result.get("strategy_name"),
        "buy_rules": [rule.get("expression") for rule in rules.get("buy_rules", [])],
        "sell_rules": [rule.get("expression") for rule in rules.get("sell_rules", [])],
        "risk_rules": [rule.get("expression") for rule in rules.get("risk_rules", [])],
        "buy_idea": " and ".join(rule.get("expression", "") for rule in rules.get("buy_rules", [])),
        "sell_idea": " and ".join(rule.get("expression", "") for rule in rules.get("sell_rules", [])),
        "risk_idea": " and ".join(rule.get("expression", "") for rule in rules.get("risk_rules", [])),
        "notes": [result.get("explanation", "")],
    }


@router.post("/strategy/parse")
def parse_strategy(request: StrategyRequest) -> dict[str, Any]:
    if not deepseek_key(required=False):
        return _fallback_strategy(request)
    result = chat_json(
        STRATEGY_AGENT_PROMPT
        + "\n请把用户输入转成结构化策略JSON。表达式只允许使用 close, open, high, low, volume, ma20, atr, atr_ma20, volume_ma20, drawdown, cash, position_quantity, closable, cost_basis, stop_loss_price。"
        + "\nJSON字段：strategy_name、strategy_type、symbol、period、rules、params、explanation。rules.buy_rules/sell_rules/risk_rules 都是对象数组，每个对象含 id、description、expression。",
        {
            "symbol": request.symbol,
            "period": request.period,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "user_input": request.user_input or request.idea,
            "framework": request.framework,
        },
    )
    rules = result.get("rules") or {}
    return {
        "strategy_name": result.get("strategy_name") or result.get("name") or "MA20 ATR 趋势突破策略",
        "strategy_type": result.get("strategy_type") or "单股趋势策略",
        "symbol": result.get("symbol") or request.symbol,
        "period": result.get("period") or request.period,
        "rules": {
            "buy_rules": rules.get("buy_rules")
            or [
                {
                    "id": "buy_001",
                    "description": "收盘价突破 MA20 且 ATR 放大",
                    "expression": "close > ma20 and atr > atr_ma20",
                }
            ],
            "sell_rules": rules.get("sell_rules")
            or [
                {
                    "id": "sell_001",
                    "description": "收盘价跌破 MA20",
                    "expression": "close < ma20",
                }
            ],
            "risk_rules": rules.get("risk_rules")
            or [
                {
                    "id": "risk_001",
                    "description": "持仓回撤超过 8% 时止损",
                    "expression": "drawdown > 0.08",
                }
            ],
        },
        "params": result.get("params")
        or {
            "initial_cash": 1000000,
            "commission": 0.0003,
            "slippage": 0.0005,
            "t_plus_one": True,
            "round_lot": 100,
            "ma_window": 20,
            "atr_window": 14,
        },
        "explanation": result.get("explanation")
        or "该策略属于趋势突破类策略，适合趋势行情，但在震荡行情中可能出现假突破。",
    }


@router.post("/stock-search")
def ai_stock_search(request: AiStockSearchRequest) -> dict[str, Any]:
    if not deepseek_key(required=False):
        return _local_stock_search(request.query, request.limit)
    result = chat_json(
        (
            "你是A股主题股票搜索助手。只返回JSON，必须中文。根据用户的概念、行业、风格或策略意图，"
            "给出候选A股，不要编造不存在的股票，不要承诺收益。JSON字段：query、items。"
            "items每项含 symbol、code、name、exchange、reason。symbol使用000001.XSHE或601318.XSHG格式。"
        ),
        {"query": request.query, "limit": request.limit},
        temperature=0.25,
    )
    items = result.get("items") or []
    return {
        "query": result.get("query") or request.query,
        "items": items[: request.limit],
        "source": "DeepSeek",
    }


@router.post("/stock-analysis")
def stock_analysis(request: StockAnalysisRequest) -> dict[str, Any]:
    if len(request.bars or []) < 2:
        return _local_stock_analysis(request)
    if not deepseek_key(required=False):
        return _local_stock_analysis(request)
    result = chat_json(
        (
            "你是A股AI盯盘助手。只返回JSON，必须中文、专业、基于行情、K线、消息面和技术指标。"
            "不能给确定性买卖建议，必须提示风险。JSON字段：summary、basis、risks、suggestions、source。"
        ),
        request.model_dump(),
        temperature=0.25,
    )
    return {
        "success": True,
        "symbol": request.symbol,
        "name": request.name,
        "basis_meta": {
            "quote_time": (request.quote or {}).get("timestamp") or ((request.bars or [{}])[-1].get("time") if request.bars else ""),
            "bars_count": len(request.bars or []),
            "news_count": len(request.news or []),
            "data_source": (request.quote or {}).get("source") or "",
        },
        "summary": result.get("summary", ""),
        "basis": result.get("basis", []),
        "risks": result.get("risks", []),
        "suggestions": result.get("suggestions", []),
        "source": "DeepSeek",
    }


@router.post("/strategy/debug")
def debug_strategy(request: StrategyDebugRequest) -> dict[str, Any]:
    if not deepseek_key(required=False):
        return {
            "diagnosis": "模型 API Key 未配置，系统只能记录错误，无法自动修复代码。",
            "fixed_code": request.generated_code,
            "fix_summary": "请检查后端 .env 中的 DEEPSEEK_API_KEY，或先使用结构化规则回测。",
            "source": "本地提示",
        }
    result = chat_json(
        STRATEGY_AGENT_PROMPT
        + "\n你现在负责修复 rqalpha 策略代码。只返回JSON：diagnosis、fixed_code、fix_summary。不要生成系统命令。",
        {
            "strategy_json": request.strategy_json,
            "generated_code": request.generated_code,
            "error_message": request.error_message,
            "runtime_context": request.runtime_context,
        },
        temperature=0.1,
    )
    return {
        "diagnosis": result.get("diagnosis", ""),
        "fixed_code": result.get("fixed_code", request.generated_code),
        "fix_summary": result.get("fix_summary", ""),
        "source": "DeepSeek",
    }
