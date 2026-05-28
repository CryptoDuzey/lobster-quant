from __future__ import annotations

import json
import importlib.util
import re
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.security import encrypt_secret
from app.db.database import get_connection
from app.agents.backtest_audit_agent import BacktestAuditAgent
from app.agents.financial_agent import FinancialAgent
from app.agents.market_watch_agent import MarketWatchAgent
from app.agents.strategy_debug_agent import StrategyDebugAgent
from app.agents.strategy_generation_agent import StrategyGenerationAgent
from app.orchestration.audit_logger import audit_logger
from app.orchestration.task_planner import planned_agent_steps
from app.orchestration.tool_registry import tool_registry
from app.providers.provider_factory import get_llm_provider
from app.providers.provider_factory import list_llm_providers


router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

MODEL_PURPOSES = ["strategy_generation", "strategy_debug", "backtest_audit", "stock_analysis", "news_summary"]
API_KEY_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{20,})")
ML_STRATEGY_KEYWORDS = (
    "xgboost",
    "xgb",
    "机器学习",
    "机器学习",
    "深度学习",
    "神经网络",
    "lstm",
    "transformer",
    "random forest",
    "随机森林",
    "lightgbm",
    "catboost",
    "强化学习",
)
FACTOR_STRATEGY_KEYWORDS = (
    "因子",
    "多因子",
    "三因子",
    "选股",
    "股票池",
    "打分",
    "排序",
)
VALUE_STRATEGY_KEYWORDS = (
    "巴菲特",
    "价值投资",
    "价值策略",
    "护城河",
    "roe",
    "ROE",
    "pe",
    "PE",
    "pb",
    "PB",
    "股息",
    "分红",
    "低估值",
    "优质公司",
)
STYLE_STRATEGY_PROFILES: dict[str, dict[str, Any]] = {
    "soros_reflexivity": {
        "aliases": ("索罗斯", "反身性", "宏观反身性", "宏观趋势"),
        "title": "索罗斯反身性 / 宏观趋势代理策略",
        "family": "macro_reflexivity_proxy",
        "factors": ["momentum_60", "ma_trend", "amount_20", "pmi", "lpr1y"],
        "factor_labels": ("60日动量", "均线趋势", "成交额流动性", "制造业PMI", "1年期LPR"),
        "boundary": "当前已接入PMI、CPI、GDP、LPR等国内宏观数据，但尚未接入汇率、海外利率和跨市场资产；因此这是A股宏观趋势代理版，不冒充完整索罗斯宏观交易。",
    },
    "peter_lynch_garp": {
        "aliases": ("彼得林奇", "彼得·林奇", "皮得林奇", "皮的林奇", "彼的林奇", "皮特林奇", "林奇策略", "成长价值", "GARP", "garp"),
        "title": "彼得林奇 GARP 成长价值代理策略",
        "family": "garp_proxy",
        "factors": ["revenue_growth", "net_profit_growth", "roe", "ma_trend"],
        "factor_labels": ("营收增长", "净利润增长", "ROE", "趋势稳定"),
        "boundary": "当前已接入真实财务摘要中的增长和ROE数据，但尚未接入历史PEG和行业成长性；因此这是GARP财务代理版，不冒充完整彼得林奇策略。",
    },
}
UNVERIFIED_BACKTEST_TERMS = (
    "回测结果",
    "回测摘要",
    "年化收益",
    "累计收益",
    "最大回撤",
    "夏普",
    "Sharpe",
    "Alpha",
    "Beta",
    "胜率",
    "交易次数",
)
UNSUPPORTED_IDEA_TERMS = (
    "市盈率",
    "市净率",
    "PE",
    "PB",
    "基金持仓",
    "机构持仓",
    "季报",
    "中报",
    "年报",
    "财报",
    "研报",
)


class MarketWatchRequest(BaseModel):
    session_id: str = ""
    symbol: str
    name: str = ""
    question: str = ""
    query: str = ""
    period: str = "1m"
    context: dict[str, Any] = Field(default_factory=dict)
    quote: dict[str, Any] = Field(default_factory=dict)
    bars: list[dict[str, Any]] = Field(default_factory=list)
    news: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    data_source: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    target_agents: list[str] = Field(default_factory=list)


class AgentStrategyGenerateRequest(BaseModel):
    symbol: str = "000001.XSHE"
    period: str = "day"
    start_date: str = "2025-01-01"
    end_date: str = "2026-05-23"
    user_input: str = ""
    framework: dict[str, Any] = Field(default_factory=dict)
    buy_idea: str = ""
    sell_idea: str = ""
    risk_idea: str = ""


class AgentDebugRequest(BaseModel):
    strategy_json: dict[str, Any] = Field(default_factory=dict)
    generated_code: str = ""
    error_message: str = ""
    runtime_context: dict[str, Any] = Field(default_factory=dict)


class AgentBacktestAuditRequest(BaseModel):
    symbol: str
    name: str = ""
    strategy_name: str = ""
    period: str = "day"
    strategy_json: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    bars: list[dict[str, Any]] = Field(default_factory=list)


class FinancialAgentRequest(BaseModel):
    session_id: str = ""
    query: str = ""
    question: str = ""
    page: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class StrategyChatRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    slots: dict[str, Any] = Field(default_factory=dict)
    use_defaults: bool = False


@router.post("/market-watch")
def market_watch(request: MarketWatchRequest) -> dict[str, Any]:
    payload = request.model_dump()
    query = payload.get("query") or payload.get("question") or ""
    payload["question"] = query if isinstance(query, str) else str(query)
    inline_key = _handle_inline_deepseek_key(payload["question"])
    if inline_key:
        return inline_key
    return MarketWatchAgent().run(payload)


@router.post("/assistant-chat")
def assistant_chat(request: MarketWatchRequest) -> dict[str, Any]:
    payload = request.model_dump()
    query = payload.get("query") or payload.get("question") or ""
    payload["question"] = query if isinstance(query, str) else str(query)
    inline_key = _handle_inline_deepseek_key(payload["question"])
    if inline_key:
        return inline_key
    return MarketWatchAgent().run(payload)


@router.post("/financial-agent-chat")
def financial_agent_chat(request: FinancialAgentRequest) -> dict[str, Any]:
    payload = request.model_dump()
    query = payload.get("query") or payload.get("question") or ""
    payload["query"] = query if isinstance(query, str) else str(query)
    inline_key = _handle_inline_deepseek_key(payload["query"])
    if inline_key:
        return {
            "success": True,
            "answer": inline_key["answer"],
            "final_summary": inline_key["answer"],
            "agent_mode": "financial_agent",
            "agent_labels": ["模型配置 Agent"],
            "provider_configured": inline_key["provider_configured"],
            "source": inline_key["source"],
        }
    return FinancialAgent().run(payload)


@router.post("/strategy-generate")
def strategy_generate(request: AgentStrategyGenerateRequest) -> dict[str, Any]:
    return StrategyGenerationAgent().run(request.model_dump())


@router.post("/strategy-chat")
def strategy_chat(request: StrategyChatRequest) -> dict[str, Any]:
    inline_key = _handle_inline_deepseek_key(_latest_user_message(request.messages))
    if inline_key:
        return {
            "complete": False,
            "conversation_only": True,
            "slots": request.slots or {},
            "message": inline_key["answer"],
            "provider_configured": inline_key["provider_configured"],
            "agent_source": inline_key["source"],
        }
    if _is_execution_timing_question(request):
        return _execution_timing_chat(request)
    if _is_investment_knowledge_question(request):
        return _investment_knowledge_chat(request)
    if _looks_like_ml_strategy_request(request):
        return _ml_strategy_boundary_response(request)
    if _looks_like_value_strategy_request(request):
        return _value_strategy_response(request)
    named_style = _detect_named_strategy_style(request)
    if named_style:
        return _named_strategy_style_response(request, named_style)
    if _looks_like_factor_strategy_request(request):
        return _factor_strategy_guidance_response(request)
    if not request.use_defaults and _is_strategy_ideation_chat(request):
        return _strategy_ideation_chat(request)
    if not request.use_defaults and _is_general_chat(request):
        return _general_strategy_chat(request)
    slots = _extract_strategy_slots(request)
    missing = _missing_strategy_slots(slots)
    if missing and not request.use_defaults:
        questions = _slot_questions(missing)
        audit_logger.log(
            agent="策略对话智能体",
            action="补全策略信息",
            input_summary={"missing": missing, "questions": questions},
            output_summary={"complete": False},
        )
        return {
            "complete": False,
            "slots": slots,
            "missing_slots": missing,
            "questions": questions,
            "message": "策略信息还不完整，请先补充关键条件，或选择使用默认配置。",
        }

    completed = _apply_default_slots(slots)
    user_input = _latest_user_message(request.messages) or "请根据已补全槽位生成结构化策略。"
    generated = StrategyGenerationAgent().run(
        {
            "symbol": completed["symbol"],
            "period": completed["period"],
            "start_date": completed["start_date"],
            "end_date": completed["end_date"],
            "user_input": user_input,
            "framework": completed,
            "buy_idea": completed.get("buy_condition", ""),
            "sell_idea": completed.get("sell_condition", ""),
            "risk_idea": completed.get("stop_loss", ""),
            "execution_time": completed.get("execution_time"),
        }
    )
    audit_logger.log(
        agent="策略对话智能体",
        action="策略槽位补全并生成策略",
        input_summary={"slots": completed},
        output_summary={"complete": True, "strategy_name": generated.get("strategy_name")},
    )
    return {
        "complete": True,
        "slots": completed,
        "strategy": generated,
        "agent_source": generated.get("source"),
        "provider_configured": generated.get("provider_configured"),
        "message": "策略信息已补全，已生成结构化策略和 rqalpha 代码。",
    }


@router.post("/strategy-debug")
def strategy_debug(request: AgentDebugRequest) -> dict[str, Any]:
    return StrategyDebugAgent().run(request.model_dump())


@router.post("/backtest-audit")
def backtest_audit(request: AgentBacktestAuditRequest) -> dict[str, Any]:
    return BacktestAuditAgent().run(request.model_dump())


def _latest_user_message(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content", "") or "")
    return ""


def _all_user_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(item.get("content", "") or "") for item in messages if item.get("role") == "user")


def _looks_like_ml_strategy_request(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages).lower()
    return any(keyword.lower() in text for keyword in ML_STRATEGY_KEYWORDS)


def _looks_like_factor_strategy_request(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages)
    lowered = text.lower()
    core_terms = ("因子", "多因子", "三因子", "选股", "股票池", "打分", "排序")
    if any(term.lower() in lowered or term in text for term in core_terms):
        return True
    return ("调仓" in text or "rebalance" in lowered) and any(
        term.lower() in lowered or term in text
        for term in ("股票池", "选前", "排名", "top", "组合", "持仓数量")
    )


def _is_execution_timing_question(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages).strip()
    if not text:
        return False
    lowered = text.lower()
    if any(term in text for term in ("买入", "卖出", "上穿", "下穿", "止损")) and any(
        term in text for term in ("用", "回测", "策略")
    ):
        return False
    timing_terms = (
        "调仓",
        "调仓时间",
        "交易时间",
        "执行时间",
        "成交时间",
        "什么时候",
        "几点",
        "十点",
        "10点",
        "10:00",
        "开盘",
        "收盘",
        "日线",
        "分钟线",
        "分钟级",
        "分钟级别",
        "分钟回测",
        "分钟级回测",
        "分钟数据",
    )
    question_terms = ("吗", "嘛", "呢", "？", "?", "可以", "能不能", "不能", "是否", "怎么", "为什么")
    return any(term in text or term in lowered for term in timing_terms) and any(term in text for term in question_terms)


def _is_investment_knowledge_question(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages).strip()
    if not text:
        return False
    lowered = text.lower()
    names = ("巴菲特", "索罗斯", "彼得林奇", "彼得·林奇", "皮的林奇", "皮得林奇", "林奇", "芒格", "达利欧", "格雷厄姆")
    question_terms = ("知道", "是谁", "什么", "吗", "嘛", "？", "?", "怎么理解", "讲讲", "介绍")
    action_terms = ("生成", "回测", "跑", "执行", "买入", "卖出", "选股", "持仓", "调仓", "代码", "收益", "策略啊")
    if not any(name.lower() in lowered or name in text for name in names):
        return False
    if any(term in text for term in action_terms):
        return False
    return len(text) <= 80 and any(term in text for term in question_terms)


def _investment_knowledge_chat(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    system_prompt = (
        "你是龙虾量化 Lobster Quant 的 A 股量化投研助手。"
        "用户现在是在普通对话或投资知识咨询，不是让你立刻生成策略。"
        "请直接回答用户问的人物、投资方法或概念，像正常大模型一样自然交流。"
        "回答后可以顺带说明：如果要把该思想量化，需要哪些真实数据、哪些规则、哪些边界。"
        "不要编造任何回测收益、胜率、Alpha/Beta 或已经跑过的结果。"
        "不要把所有问题都套成多因子模板；只有用户明确要求回测、选股、买卖条件或生成代码时，才进入策略生成。"
        "中文、简洁、专业。"
    )
    if provider.available:
        try:
            response = provider.chat(
                [{"role": "system", "content": system_prompt}, *_clean_llm_messages(request.messages)],
                temperature=0.28,
                timeout=45,
            )
            return {
                "complete": False,
                "conversation_only": True,
                "knowledge_chat": True,
                "slots": request.slots or {},
                "message": response.content,
                "provider_configured": True,
                "agent_source": "DeepSeek_knowledge_agent",
            }
        except Exception as exc:
            message = f"模型调用失败：{exc}"
    else:
        message = "我可以先回答投资人物和策略思想，但当前 DeepSeek 未配置，回答会比较基础。你配置 Key 后，我会用模型结合上下文继续分析。"
    return {
        "complete": False,
        "conversation_only": True,
        "knowledge_chat": True,
        "slots": request.slots or {},
        "message": message,
        "provider_configured": bool(provider.available),
        "agent_source": "local_knowledge_agent",
    }


def _execution_timing_chat(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    system_prompt = (
        "你是龙虾量化 Lobster Quant 的 A 股回测执行时点 Agent。"
        "用户正在问日线、分钟线、调仓时间、成交时间相关问题。"
        "必须直接回答问题，不要切换到多因子模板，不要要求用户补股票池。"
        "当前产品能力：可以做分钟级回测，支持 1分钟、5分钟、15分钟、30分钟、60分钟；"
        "但分钟历史长度取决于真实数据源，日线和60分钟通常可覆盖一年以上，30分钟接近一年，"
        "15分钟、5分钟、1分钟可用历史更短，必须以接口返回的 actual_start/actual_end 为准。"
        "不要说 rqalpha 默认只有日线，也不要说必须由用户额外导入数据；本系统会先尝试真实数据源。"
        "核心规则：日线只能用日K级别信号，无法真实还原10:00或9:31这类分钟级成交；"
        "如果要每天10:00或9:31真实调仓，需要1分钟或足够细的分钟级行情和分钟级回测；"
        "日线策略更可信的口径是收盘后生成信号，下一交易日开盘附近执行，或明确标注日线估算成交。"
        "如果用户问能不能做，回答可以做，但必须说明需要分钟线，不能用日线假装精确到分钟。"
        "如果数据源覆盖不到用户给的时间段，必须说明会失败，不会补假数据。"
        "中文、简洁、像正常大模型对话。"
    )
    if provider.available:
        try:
            response = provider.chat(
                [{"role": "system", "content": system_prompt}, *_clean_llm_messages(request.messages)],
                temperature=0.18,
                timeout=45,
            )
            return {
                "complete": False,
                "conversation_only": True,
                "execution_timing": True,
                "slots": request.slots or {},
                "message": _strip_unverified_backtest_claims(response.content),
                "provider_configured": True,
                "agent_source": "DeepSeek_execution_timing_agent",
            }
        except Exception as exc:
            message = f"模型调用失败：{exc}\n\n{_local_execution_timing_answer()}"
            return {
                "complete": False,
                "conversation_only": True,
                "execution_timing": True,
                "slots": request.slots or {},
                "message": message,
                "provider_configured": True,
                "agent_source": "local_execution_timing_agent",
            }
    return {
        "complete": False,
        "conversation_only": True,
        "execution_timing": True,
        "slots": request.slots or {},
        "message": _local_execution_timing_answer(),
        "provider_configured": False,
        "agent_source": "local_execution_timing_agent",
    }


def _local_execution_timing_answer() -> str:
    return (
        "能做分钟级回测，但要说清楚边界：\n\n"
        "1. 龙虾量化支持 1分钟、5分钟、15分钟、30分钟、60分钟回测，会优先请求真实分钟K线。\n"
        "2. 如果你要 9:31、10:00 这种精确成交时间，必须用分钟级数据，不能拿日K假装成分钟成交。\n"
        "3. 分钟历史长度取决于真实数据源：日线和60分钟通常能覆盖一年以上，30分钟接近一年，"
        "15分钟、5分钟、1分钟可用历史更短，要以接口实际返回区间为准。\n"
        "4. 如果数据源拿不到你给的分钟区间，系统会直接报错，不会补假数据。\n\n"
        "所以结论是：可以做。你可以直接说：用平安银行，5分钟，最近两个月，10:00 调仓，某某条件买入卖出。"
    )


def _looks_like_value_strategy_request(request: StrategyChatRequest) -> bool:
    latest = _latest_user_message(request.messages).strip()
    if not latest:
        return False
    lowered = latest.lower()
    all_text = _all_user_text(request.messages)
    all_lowered = all_text.lower()
    if any(phrase in latest for phrase in ("知道嘛", "知道吗", "是谁", "是什么")) and not any(
        term in latest for term in ("策略", "回测", "试试", "选股", "持仓")
    ):
        return False
    latest_mentions_value = any(keyword.lower() in lowered or keyword in latest for keyword in VALUE_STRATEGY_KEYWORDS)
    previous_mentions_value = any(keyword.lower() in all_lowered or keyword in all_text for keyword in VALUE_STRATEGY_KEYWORDS)
    followup_terms = ("试试", "可以", "回测", "选股", "持仓", "日频", "日线", "初始", "资金", "策略")
    return latest_mentions_value or (previous_mentions_value and any(term in latest for term in followup_terms))


def _detect_named_strategy_style(request: StrategyChatRequest) -> str:
    latest = _latest_user_message(request.messages).strip()
    if not latest:
        return ""
    all_text = _all_user_text(request.messages)
    latest_lowered = latest.lower()
    all_lowered = all_text.lower()
    for key, profile in STYLE_STRATEGY_PROFILES.items():
        aliases = tuple(profile.get("aliases") or ())
        latest_mentions = any(alias.lower() in latest_lowered or alias in latest for alias in aliases)
        previous_mentions = any(alias.lower() in all_lowered or alias in all_text for alias in aliases)
        if latest_mentions:
            return key
        if previous_mentions and any(term in latest for term in ("试试", "可以", "回测", "选股", "持仓", "日频", "日线", "初始", "资金", "策略")):
            return key
    return ""


def _named_strategy_style_response(request: StrategyChatRequest, style_key: str) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    profile = STYLE_STRATEGY_PROFILES[style_key]
    all_text = _all_user_text(request.messages)
    latest = _latest_user_message(request.messages)
    spec = _parse_factor_spec(all_text)
    spec["initial_cash"] = _parse_cash(all_text)
    if not spec.get("start_date") or not spec.get("end_date"):
        message = (
            f"我识别到你说的是「{profile['title']}」。\n\n"
            f"{profile['boundary']}\n\n"
            "如果你想先做可验证版本，请补充：股票池或标的、回测起止时间、初始资金、持仓数量和调仓频率。"
            "例如：沪深300选股，2025.1.1 到 2026.5.22，日频，初始100万，持仓10只。"
        )
        return {
            "complete": False,
            "conversation_only": True,
            "strategy_mode": profile["family"],
            "slots": request.slots or {},
            "message": message,
            "provider_configured": bool(provider.available),
            "agent_source": "style_strategy_router",
        }

    factors = list(profile["factors"])
    factor_labels = list(profile["factor_labels"])
    strategy_json = {
        "strategy_name": profile["title"],
        "strategy_type": "股票池风格代理策略",
        "mode": "factor_selection",
        "symbol": "000001.XSHE",
        "period": "day",
        "stock_pool": spec["stock_pool"],
        "factors": factors,
        "rules": {
            "buy_rules": [
                {
                    "id": "style_proxy_rank_buy",
                    "description": f"按 {', '.join(factor_labels)} 打分，调仓时买入排名前 {spec['top_n']} 只",
                    "expression": "factor_score_rank <= top_n",
                }
            ],
            "sell_rules": [
                {
                    "id": "style_proxy_rebalance_sell",
                    "description": "调仓日卖出不在新一期名单内的持仓",
                    "expression": "not_in_selected_pool",
                }
            ],
            "risk_rules": [
                {
                    "id": "style_proxy_boundary",
                    "description": profile["boundary"],
                    "expression": "style_data_boundary",
                }
            ],
        },
        "params": {
            "strategy_mode": "factor_selection",
            "strategy_family": profile["family"],
            "stock_pool": spec["stock_pool"],
            "factors": factors,
            "rebalance": spec["rebalance"],
            "top_n": spec["top_n"],
            "initial_cash": spec["initial_cash"],
            "commission": 0.0003,
            "slippage": 0.0005,
            "stamp_tax": 0.001,
            "benchmark": spec["benchmark"],
            "universe_limit": 80,
        },
        "explanation": f"这是「{profile['title']}」的可验证代理版。{profile['boundary']}",
        "warnings": [profile["boundary"]],
    }
    generated_code = (
        f"# {profile['title']}\n"
        f"# 重要说明：{profile['boundary']}\n"
        f"# 股票池: {spec['stock_pool']}\n"
        f"# 代理因子: {', '.join(factor_labels)}\n"
        f"# 持仓数量: {spec['top_n']}，调仓: {spec['rebalance']}\n"
        "# 回测由后端真实行情数据与组合调仓模块完成；不执行外部不安全代码。\n"
    )
    completed_slots = {
        "mode": "factor_selection",
        "symbol": "000001.XSHE",
        "stock_name": spec["stock_pool"],
        "period": "day",
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "buy_condition": "factor_score_rank <= top_n",
        "sell_condition": "not_in_selected_pool",
        "initial_cash": spec["initial_cash"],
        "benchmark": spec["benchmark"],
    }
    audit_logger.log(
        agent="策略对话智能体",
        action="生成投资流派代理策略",
        input_summary={"query": latest, "style": style_key, "spec": spec},
        output_summary={"complete": True, "strategy_mode": profile["family"]},
    )
    return {
        "complete": True,
        "conversation_only": False,
        "strategy_mode": profile["family"],
        "slots": completed_slots,
        "message": (
            f"我识别到这是「{profile['title']}」，不会硬套成普通模板。\n"
            f"{profile['boundary']}\n"
            f"已生成可验证代理版：{spec['stock_pool']} 股票池，持仓 {spec['top_n']} 只，"
            f"区间 {spec['start_date']} 至 {spec['end_date']}，使用真实行情做 {', '.join(factor_labels)} 回测。"
        ),
        "strategy": {
            "strategy_name": strategy_json["strategy_name"],
            "strategy_json": strategy_json,
            "generated_code": generated_code,
            "source": "style_strategy_router",
            "provider_configured": bool(provider.available),
        },
        "agent_source": "style_strategy_router",
        "provider_configured": bool(provider.available),
    }


def _parse_factor_spec(text: str) -> dict[str, Any]:
    lowered = text.lower()
    factors: list[str] = []
    factor_aliases = [
        ("momentum_60", ("动量", "强势", "momentum")),
        ("low_volatility_60", ("低波动", "波动率低", "低波", "稳健")),
        ("amount_20", ("成交额", "流动性", "成交量", "放量")),
        ("rsi_14", ("rsi", "相对强弱")),
        ("ma_trend", ("均线", "趋势")),
        ("roe", ("roe", "净资产收益率", "盈利能力", "高ROE", "质量")),
        ("revenue_growth", ("营收增长", "收入增长", "营业收入增长")),
        ("net_profit_growth", ("利润增长", "净利润增长", "归母净利润增长", "成长")),
        ("debt_ratio", ("资产负债率", "低负债", "负债率")),
        ("cashflow_quality", ("现金流", "经营现金流", "现金流质量")),
        ("net_margin", ("净利率", "销售净利率")),
        ("pmi", ("pmi", "PMI", "制造业景气")),
        ("cpi_yoy", ("cpi", "CPI", "通胀")),
        ("gdp_yoy", ("gdp", "GDP", "经济增长")),
        ("lpr1y", ("lpr", "LPR", "利率")),
    ]
    for name, aliases in factor_aliases:
        if any(alias in lowered or alias in text for alias in aliases):
            factors.append(name)
    if "三因子" in text and len(factors) < 3:
        for fallback in ["momentum_60", "low_volatility_60", "amount_20"]:
            if fallback not in factors:
                factors.append(fallback)
            if len(factors) >= 3:
                break
    if ("价值" in text or "巴菲特" in text) and not any(factor in factors for factor in ["roe", "net_profit_growth", "debt_ratio"]):
        factors.extend(["roe", "net_profit_growth", "debt_ratio", "cashflow_quality"])
    if ("宏观" in text or "索罗斯" in text) and not any(factor in factors for factor in ["pmi", "lpr1y"]):
        factors.extend(["momentum_60", "ma_trend", "pmi", "lpr1y"])
    factors = list(dict.fromkeys(factors))

    pool = "CSI300"
    if "中证500" in text or "000905" in text:
        pool = "CSI500"
    elif "全a" in lowered or "全 A" in text or "全A" in text:
        pool = "A_SHARE_SAMPLE"
    elif "沪深300" in text or "000300" in text:
        pool = "CSI300"

    top_n = 10
    top_match = re.search(r"(?:前|top|持仓|选前)\s*(\d{1,3})", lowered)
    if top_match:
        top_n = max(1, min(50, int(top_match.group(1))))
    rebalance = "monthly"
    if "每周" in text or "周调仓" in text:
        rebalance = "weekly"
    elif "每日" in text or "每天" in text:
        rebalance = "daily"

    dates = re.findall(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", text)
    years = re.findall(r"(20\d{2})", text)
    start_date = _normalize_date(dates[0]) if len(dates) >= 1 else None
    end_date = _normalize_date(dates[1]) if len(dates) >= 2 else None
    if not start_date and len(years) >= 1:
        start_date = f"{int(years[0]):04d}-01-01"
    if not end_date and len(years) >= 2:
        end_date = f"{int(years[-1]):04d}-12-31"
    return {
        "mode": "factor_selection",
        "stock_pool": pool,
        "factors": factors,
        "rebalance": rebalance,
        "top_n": top_n,
        "start_date": start_date,
        "end_date": end_date,
        "period": "day",
        "initial_cash": 1000000,
        "benchmark": "000300.XSHG" if pool != "CSI500" else "000905.XSHG",
    }


def _parse_cash(text: str, default: float = 1000000) -> float:
    match = re.search(r"(?:初始资金|资金|本金|初始)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(万|w|W|元)?", text)
    if not match:
        return default
    value = float(match.group(1))
    unit = match.group(2) or ""
    if unit in {"万", "w", "W"}:
        value *= 10000
    return max(10000, value)


def _value_strategy_response(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    all_text = _all_user_text(request.messages)
    latest = _latest_user_message(request.messages)
    spec = _parse_factor_spec(all_text)
    spec["initial_cash"] = _parse_cash(all_text)
    if not spec.get("start_date") or not spec.get("end_date"):
        message = (
            "我识别到你说的是巴菲特 / 价值投资策略。这里不能简单套成普通三因子。\n\n"
            "先说清楚边界：当前系统已接入可追溯的ROE、利润增长、负债率和现金流质量，但历史PE/PB/股息率仍未接入，所以不能冒充完整巴菲特基本面策略。\n\n"
            "如果你要先做可验证版本，请补充：股票池、回测起止时间、初始资金、持仓数量。"
            "例如：沪深300选股，2025.1.1 到 2026.5.22，日频，初始100万，持仓10只。"
        )
        return {
            "complete": False,
            "conversation_only": True,
            "strategy_mode": "value_investing",
            "slots": request.slots or {},
            "message": message,
            "provider_configured": bool(provider.available),
            "agent_source": "value_strategy_router",
        }

    factor_names = ["ROE", "净利润增长", "低负债", "现金流质量"]
    strategy_json = {
        "strategy_name": "巴菲特风格价值投资代理策略",
        "strategy_type": "股票池价值投资代理策略",
        "mode": "factor_selection",
        "symbol": "000001.XSHE",
        "period": "day",
        "stock_pool": spec["stock_pool"],
        "factors": ["roe", "net_profit_growth", "debt_ratio", "cashflow_quality"],
        "rules": {
            "buy_rules": [
                {
                    "id": "value_proxy_rank_buy",
                    "description": f"在股票池内按ROE、净利润增长、低负债和现金流质量打分，买入排名前 {spec['top_n']} 只",
                    "expression": "factor_score_rank <= top_n",
                }
            ],
            "sell_rules": [
                {
                    "id": "value_proxy_rebalance_sell",
                    "description": "调仓日卖出不在新一期名单内的持仓",
                    "expression": "not_in_selected_pool",
                }
            ],
            "risk_rules": [
                {
                    "id": "value_proxy_boundary",
                    "description": "当前已接入ROE、利润增长、负债率和现金流质量；历史PE/PB/股息率仍未接入",
                    "expression": "valuation_data_unavailable",
                }
            ],
        },
        "params": {
            "strategy_mode": "factor_selection",
            "strategy_family": "value_investing_proxy",
            "stock_pool": spec["stock_pool"],
            "factors": ["roe", "net_profit_growth", "debt_ratio", "cashflow_quality"],
            "rebalance": "monthly",
            "top_n": spec["top_n"],
            "initial_cash": spec["initial_cash"],
            "commission": 0.0003,
            "slippage": 0.0005,
            "stamp_tax": 0.001,
            "benchmark": spec["benchmark"],
            "universe_limit": 80,
        },
        "explanation": (
            "这是巴菲特风格的行情代理版：使用真实行情里的低波动、趋势稳定和流动性过滤做组合调仓。"
            "它不是完整巴菲特基本面策略，因为当前还没有历史PE、ROE、股息率数据链路。"
        ),
        "warnings": [
            "已使用真实财务摘要中的ROE、利润增长、负债率和现金流质量；历史PE/PB/股息率仍未接入。",
            "该版本是价值投资财务代理策略，结果需要单独标注口径，不能等同于巴菲特原始选股体系。",
        ],
    }
    generated_code = (
        "# 巴菲特风格价值投资代理策略\n"
        "# 重要说明：当前版本已接入ROE、利润增长、负债率和现金流质量；历史PE/PB/股息率尚未接入。\n"
        f"# 股票池: {spec['stock_pool']}\n"
        f"# 代理因子: {', '.join(factor_names)}\n"
        f"# 持仓数量: {spec['top_n']}，调仓: monthly\n"
        "# 回测由后端真实行情数据与组合调仓模块完成；不执行外部不安全代码。\n"
    )
    completed_slots = {
        "mode": "factor_selection",
        "symbol": "000001.XSHE",
        "stock_name": spec["stock_pool"],
        "period": "day",
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "buy_condition": "value_proxy_rank <= top_n",
        "sell_condition": "not_in_selected_pool",
        "initial_cash": spec["initial_cash"],
        "benchmark": spec["benchmark"],
    }
    audit_logger.log(
        agent="策略对话智能体",
        action="生成巴菲特价值投资代理策略",
        input_summary={"query": latest, "spec": spec},
        output_summary={"complete": True, "strategy_mode": "value_investing_proxy"},
    )
    return {
        "complete": True,
        "conversation_only": False,
        "strategy_mode": "value_investing_proxy",
        "slots": completed_slots,
        "message": (
            "我识别到这是巴菲特 / 价值投资策略，不再按普通三因子处理。\n"
            "已生成“巴菲特风格财务代理版”："
            f"{spec['stock_pool']} 股票池，持仓 {spec['top_n']} 只，区间 {spec['start_date']} 至 {spec['end_date']}，"
            "使用真实财务摘要中的ROE、利润增长、负债率和现金流质量进入回测。历史PE/PB/股息率还未接入，会在报告中标注。"
        ),
        "strategy": {
            "strategy_name": strategy_json["strategy_name"],
            "strategy_json": strategy_json,
            "generated_code": generated_code,
            "source": "value_strategy_router",
            "provider_configured": bool(provider.available),
        },
        "agent_source": "value_strategy_router",
        "provider_configured": bool(provider.available),
    }


def _factor_strategy_guidance_response(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    query = _latest_user_message(request.messages)
    spec = _parse_factor_spec(_all_user_text(request.messages))
    if spec["factors"] and spec.get("start_date") and spec.get("end_date"):
        factor_labels = {
            "momentum_60": "60日动量",
            "low_volatility_60": "60日低波动",
            "amount_20": "20日成交额",
            "rsi_14": "RSI强弱",
            "ma_trend": "均线趋势",
            "roe": "ROE",
            "roa": "ROA",
            "revenue_growth": "营收增长率",
            "net_profit_growth": "净利润增长率",
            "debt_ratio": "资产负债率",
            "cashflow_quality": "现金流质量",
            "net_margin": "销售净利率",
            "pmi": "制造业PMI",
            "cpi_yoy": "CPI同比",
            "gdp_yoy": "GDP同比",
            "lpr1y": "1年期LPR",
        }
        factor_names = [factor_labels.get(item, item) for item in spec["factors"]]
        strategy_json = {
            "strategy_name": f"{' + '.join(factor_names[:3])} 多因子选股策略",
            "strategy_type": "股票池多因子策略",
            "mode": "factor_selection",
            "symbol": "000001.XSHE",
            "period": "day",
            "stock_pool": spec["stock_pool"],
            "factors": spec["factors"],
            "rules": {
                "buy_rules": [
                    {
                        "id": "factor_rank_buy",
                        "description": f"按 {', '.join(factor_names)} 等权打分，调仓时买入排名前 {spec['top_n']} 只",
                        "expression": "factor_score_rank <= top_n",
                    }
                ],
                "sell_rules": [
                    {
                        "id": "factor_rebalance_sell",
                        "description": "调仓日卖出不在新一期名单内的持仓",
                        "expression": "not_in_selected_pool",
                    }
                ],
                "risk_rules": [],
            },
            "params": {
                "strategy_mode": "factor_selection",
                "stock_pool": spec["stock_pool"],
                "factors": spec["factors"],
                "rebalance": spec["rebalance"],
                "top_n": spec["top_n"],
                "initial_cash": spec["initial_cash"],
                "commission": 0.0003,
                "slippage": 0.0005,
                "stamp_tax": 0.001,
                "benchmark": spec["benchmark"],
                "universe_limit": 30,
            },
            "explanation": "这是基于真实行情数据的多因子实验策略规格。系统会按股票池样本计算因子分数并做组合调仓回测，不会生成虚假的收益。"
        }
        generated_code = (
            "# 多因子选股策略由龙虾量化安全规则引擎执行\n"
            f"# 股票池: {spec['stock_pool']}\n"
            f"# 因子: {', '.join(factor_names)}\n"
            f"# 调仓: {spec['rebalance']}，持仓数量: {spec['top_n']}\n"
            "# 回测由后端真实行情数据与组合调仓模块完成；不执行外部不安全代码。\n"
        )
        completed_slots = {
            "mode": "factor_selection",
            "symbol": "000001.XSHE",
            "stock_name": spec["stock_pool"],
            "period": "day",
            "start_date": spec["start_date"],
            "end_date": spec["end_date"],
            "buy_condition": "factor_score_rank <= top_n",
            "sell_condition": "not_in_selected_pool",
            "initial_cash": spec["initial_cash"],
            "benchmark": spec["benchmark"],
        }
        audit_logger.log(
            agent="策略对话智能体",
            action="生成多因子选股实验策略",
            input_summary={"query": query, "spec": spec},
            output_summary={"complete": True, "strategy_mode": "factor_selection"},
        )
        return {
            "complete": True,
            "conversation_only": False,
            "strategy_mode": "factor_selection",
            "slots": completed_slots,
            "message": "多因子策略规格已生成。它将使用真实行情做组合调仓实验回测；如果数据源取不到某些成分股，会在回测报告里明确警告。",
            "strategy": {
                "strategy_name": strategy_json["strategy_name"],
                "strategy_json": strategy_json,
                "generated_code": generated_code,
                "source": "factor_strategy_router",
                "provider_configured": bool(provider.available),
            },
            "agent_source": "factor_strategy_router",
            "provider_configured": bool(provider.available),
        }
    message = (
        "可以，三因子选股属于股票池 / 多因子策略。\n\n"
        "要把它做成可以验证的策略，我需要先确认这些条件：\n"
        "1. 股票池：全 A、沪深300、中证500，还是你自己的自选池？\n"
        "2. 三个因子：例如动量、估值、质量、波动率、成交额、股息率，你想用哪三个？\n"
        "3. 打分方式：等权打分，还是某个因子权重更高？\n"
        "4. 调仓周期：每日、每周、每月，还是固定 N 个交易日？\n"
        "5. 持仓数量：选前 5、前 10、前 20，还是按资金等权买入？\n"
        "6. 回测区间、初始资金、手续费、滑点和基准指数。\n\n"
        "当前正式可信回测主线已经稳定支持单股规则策略。多因子选股我会先帮你整理成清晰策略规格；"
        "等股票池数据、因子计算和组合调仓模块接入后，再进入真实回测。你可以直接补一句："
        "“用沪深300股票池，动量+低波动+成交额三个因子，每月调仓，选前10只，2022到2026回测”。"
    )
    audit_logger.log(
        agent="策略对话智能体",
        action="识别多因子选股意图",
        input_summary={"query": query},
        output_summary={"complete": False, "strategy_mode": "factor_selection"},
    )
    return {
        "complete": False,
        "conversation_only": True,
        "strategy_mode": "factor_selection",
        "slots": request.slots or {},
        "message": message,
        "provider_configured": bool(provider.available),
        "agent_source": "factor_strategy_router",
    }


def _ml_strategy_capability() -> dict[str, Any]:
    return {
        "xgboost_installed": importlib.util.find_spec("xgboost") is not None,
        "sklearn_installed": importlib.util.find_spec("sklearn") is not None,
        "ml_runner_ready": True,
        "supported_now": True,
        "supported_scope": "单只股票、日线、基础滚动线性模型；不冒充 XGBoost / 深度学习结果",
    }


def _ml_strategy_boundary_response(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    capability = _ml_strategy_capability()
    text = _all_user_text(request.messages)
    if _looks_like_factor_strategy_request(request) or any(term in text for term in ("股票池", "沪深300选股", "全A", "全 A", "组合调仓", "多因子")):
        message = (
            "可以讨论机器学习选股，但当前正式可信回测只先开放“单只股票基础机器学习择时”。\n\n"
            "原因很简单：股票池机器学习需要稳定的成分股历史、财务因子、横截面训练、组合调仓和样本外验证。"
            "这些模块不能用模板假装，否则结果不可信。\n\n"
            "你现在可以先这样落地：用某一只股票，给出回测区间和周期，我会生成基础机器学习择时实验；"
            "如果要做沪深300股票池机器学习，我会先整理成研究方案，等股票池因子和组合调仓链路完整后再跑真实回测。"
        )
        return {
            "complete": False,
            "conversation_only": True,
            "unsupported_strategy_type": "ml_stock_pool_not_ready",
            "capability": capability,
            "slots": request.slots or {},
            "message": message,
            "provider_configured": bool(provider.available),
            "agent_source": "ml_capability_router",
        }

    slots = _extract_strategy_slots(request)
    minimal_missing = [key for key in ("symbol", "period", "start_date", "end_date") if not slots.get(key)]
    if minimal_missing and not request.use_defaults:
        questions = {
            "symbol": "你想用哪只股票做机器学习择时？例如平安银行 000001.XSHE。",
            "period": "当前基础机器学习实验先支持日线，你是否接受日线？",
            "start_date": "回测从哪一天开始？",
            "end_date": "回测到哪一天结束？",
        }
        message = (
            "机器学习策略可以先做一个真实数据的基础实验，但我需要先确认几个关键条件。\n"
            "当前不会直接编造 XGBoost 或深度学习结果；先跑的是基础滚动线性模型，用真实行情生成信号。\n\n"
            + "\n".join(questions[key] for key in minimal_missing[:4])
        )
        return {
            "complete": False,
            "conversation_only": True,
            "slots": slots,
            "missing_slots": minimal_missing,
            "questions": [questions[key] for key in minimal_missing[:4]],
            "message": message,
            "provider_configured": bool(provider.available),
            "agent_source": "ml_slot_router",
        }

    completed = _apply_default_slots(slots)
    completed["period"] = "day"
    completed["mode"] = "ml_basic"
    strategy_name = "基础机器学习择时实验"
    strategy_json = {
        "strategy_name": strategy_name,
        "strategy_type": "机器学习实验策略",
        "mode": "ml_basic",
        "symbol": completed["symbol"],
        "period": "day",
        "start_date": completed["start_date"],
        "end_date": completed["end_date"],
        "rules": {
            "buy_rules": [
                {
                    "description": "滚动模型预测下一交易日收益大于阈值时买入",
                    "expression": "ml_prediction > prediction_threshold",
                }
            ],
            "sell_rules": [
                {
                    "description": "滚动模型预测下一交易日收益小于等于阈值时卖出",
                    "expression": "ml_prediction <= prediction_threshold",
                }
            ],
            "risk_rules": [
                {
                    "description": "A股 T+1、100股整手、真实手续费滑点；不使用未来数据",
                    "expression": "safe_walk_forward_validation",
                }
            ],
        },
        "params": {
            "strategy_mode": "ml_basic",
            "model_type": "rolling_ridge_linear",
            "train_window": 120,
            "prediction_threshold": 0,
            "initial_cash": completed.get("initial_cash", 1000000),
            "commission": 0.0003,
            "slippage": 0.0005,
            "stamp_tax": 0.001,
            "round_lot": 100,
            "t_plus_one": True,
            "benchmark": completed.get("benchmark", "000300.XSHG"),
        },
        "warnings": [
            "这是基础机器学习实验，不是 XGBoost、LSTM 或深度学习结果。",
            "模型只使用历史OHLCV特征滚动训练，不允许未来函数。",
            "结果必须以真实回测接口返回的曲线、交割单和指标为准。",
        ],
    }
    generated_code = (
        "# 基础机器学习择时实验\n"
        "# 后端将使用真实日线行情构造历史特征，并滚动训练基础线性模型。\n"
        "# 当前不生成伪造的 XGBoost / 深度学习代码；回测结果只来自后端真实运行。\n"
        "strategy_mode = 'ml_basic'\n"
        "model_type = 'rolling_ridge_linear'\n"
        "features = ['ret_1', 'ret_3', 'ret_5', 'ret_10', 'ret_20', 'ma5_gap', 'ma20_gap', 'volatility_20', 'volume_ratio_20']\n"
        "train_window = 120\n"
        "prediction_threshold = 0.0\n"
    )
    audit_logger.log(
        agent="策略对话智能体",
        action="生成基础机器学习实验策略",
        input_summary={"query": _latest_user_message(request.messages), "slots": completed, "capability": capability},
        output_summary={"complete": True, "strategy_name": strategy_name},
    )
    return {
        "complete": True,
        "conversation_only": False,
        "strategy_mode": "ml_basic",
        "capability": capability,
        "slots": completed,
        "strategy": {
            "strategy_name": strategy_name,
            "strategy_json": strategy_json,
            "generated_code": generated_code,
            "safety_check": {
                "symbol_valid": True,
                "no_future_function": True,
                "no_unsafe_eval": True,
                "data_not_empty_required": True,
                "a_share_rules_checked": True,
                "ml_result_not_faked": True,
            },
            "source": "local_ml_basic_agent",
            "provider_configured": bool(provider.available),
        },
        "message": (
            "我已生成一个可真实回测的基础机器学习择时实验。"
            "它会用真实日线行情滚动训练基础模型，不会冒充 XGBoost 或深度学习结果。"
            "点击执行回测后，收益曲线、交割单、Alpha/Beta 等都以后端真实计算为准。"
        ),
        "provider_configured": bool(provider.available),
        "agent_source": "ml_basic_agent",
    }


def _contains_unverified_backtest_claim(text: str) -> bool:
    if not text:
        return False
    if not any(term in text for term in UNVERIFIED_BACKTEST_TERMS):
        return False
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:%|次)", text))


def _strip_unverified_backtest_claims(text: str) -> str:
    if not _contains_unverified_backtest_claim(text):
        return text
    return (
        "我不能在没有真实回测任务返回结果的情况下给出收益率、最大回撤、夏普、Alpha/Beta、胜率或交易次数。\n\n"
        "如果你只是描述策略想法，我会先确认标的、时间、周期、资金、买入、卖出、仓位和基准，然后生成策略代码；"
        "只有后端真实跑完回测并返回曲线、交割单和指标后，我才会展示这些数字。"
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _extract_api_key(text: str) -> str:
    match = API_KEY_RE.search(text or "")
    return match.group(1) if match else ""


def _save_deepseek_key(api_key: str, model: str = "deepseek-chat") -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO api_keys
            (user_id, provider, encrypted_api_key, is_active, created_at, updated_at)
            VALUES (0, 'deepseek', ?, 1, ?, ?)
            ON CONFLICT(user_id, provider) DO UPDATE SET
                encrypted_api_key=excluded.encrypted_api_key,
                is_active=1,
                updated_at=excluded.updated_at
            """,
            (encrypt_secret(api_key), now, now),
        )
        for purpose in MODEL_PURPOSES:
            conn.execute(
                """
                INSERT INTO model_providers
                (user_id, provider, model, purpose, is_active, created_at, updated_at)
                VALUES (0, 'deepseek', ?, ?, 1, ?, ?)
                ON CONFLICT(user_id, provider, purpose) DO UPDATE SET
                    model=excluded.model,
                    is_active=1,
                    updated_at=excluded.updated_at
                """,
                (model, purpose, now, now),
            )


def _handle_inline_deepseek_key(text: str) -> dict[str, Any] | None:
    api_key = _extract_api_key(text)
    if not api_key:
        return None
    _save_deepseek_key(api_key)
    provider = get_llm_provider("deepseek")
    try:
        response = provider.chat(
            [
                {
                    "role": "system",
                    "content": "你是龙虾量化的模型连接测试助手。请只回复一句中文：DeepSeek 已接入龙虾量化。",
                },
                {"role": "user", "content": "测试连接"},
            ],
            temperature=0,
            timeout=30,
        )
        answer = (
            "DeepSeek API Key 已加密保存，并且模型连接测试通过。"
            "现在可以继续正常对话，也可以描述策略想法，我会先按龙虾量化内置规则补全要素，再生成代码和回测。"
        )
        if response.content:
            answer += f"\n模型返回：{response.content}"
        return {
            "success": True,
            "symbol": "",
            "name": "",
            "basis": {"data_source": "DeepSeek"},
            "answer": answer,
            "final_summary": answer,
            "confidence": 1,
            "agent_mode": "deepseek_key_saved",
            "provider_configured": True,
            "source": "DeepSeek",
            "skills_used": [],
        }
    except Exception as exc:
        answer = (
            "已收到并加密保存 DeepSeek API Key，但连接测试失败。"
            f"请检查 Key 是否正确、额度是否可用，或稍后重试。错误：{exc}"
        )
        return {
            "success": False,
            "symbol": "",
            "name": "",
            "basis": {"data_source": "DeepSeek"},
            "message": answer,
            "answer": answer,
            "final_summary": answer,
            "confidence": 0,
            "agent_mode": "deepseek_key_test_failed",
            "provider_configured": True,
            "source": "DeepSeek",
            "skills_used": [],
        }


def _clean_llm_messages(messages: list[dict[str, Any]], limit: int = 8) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in messages[-limit:]:
        role = str(item.get("role") or "user").strip().lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        content = item.get("content", "")
        if content is None:
            continue
        if not isinstance(content, str):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                content = str(content)
        content = content.strip()
        if content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _is_executable_strategy_request(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    execution_terms = (
        "生成代码",
        "写代码",
        "rqalpha",
        "执行回测",
        "跑回测",
        "真实回测",
        "回测一下",
        "送去回测",
        "用默认配置",
        "直接回测",
        "开始回测",
    )
    if any(term.lower() in lowered or term in text for term in execution_terms):
        return True
    has_rule = any(term in text or term in lowered for term in ("买入", "卖出", "上穿", "下穿", "突破", "跌破", "止损", "止盈"))
    has_range = bool(re.search(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", text)) or bool(re.search(r"20\d{2}\s*(?:到|至|-)\s*20\d{2}", text))
    has_target = bool(re.search(r"\b[036]\d{5}(?:\.(?:XSHE|XSHG|SZ|SH))?\b", text, re.IGNORECASE)) or any(
        name in text for name in ("平安银行", "中国平安", "贵州茅台", "沪深300", "中证500")
    )
    return has_rule and (has_range or has_target)


def _is_strategy_ideation_chat(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages).strip()
    if not text or _is_executable_strategy_request(text):
        return False
    lowered = text.lower()
    idea_terms = (
        "说一个",
        "说个",
        "给我一个",
        "推荐",
        "有什么",
        "有哪些",
        "策略思路",
        "策略想法",
        "牛逼",
        "厉害",
        "稳健",
        "普通的策略",
        "简单策略",
        "策略",
    )
    return len(text) <= 160 and any(term in lowered or term in text for term in idea_terms)


def _strategy_ideation_chat(request: StrategyChatRequest) -> dict[str, Any]:
    provider = get_llm_provider("deepseek")
    system_prompt = (
        "你是龙虾量化 Lobster Quant 的 AI 策略工坊助手。"
        "用户现在是在做策略头脑风暴，不是正式回测。请像正常大模型一样对话，先给可验证的A股策略思路。"
        "当前正式可落地回测的数据只包含真实A股行情OHLCV和技术指标：MA、ATR、RSI、布林带、CCI、MACD、成交量均线。"
        "不要推荐依赖市盈率、财报、基金持仓、研报、情绪数据、Level2 或任何尚未接入的数据的策略，除非明确标注暂不能回测。"
        "优先给单股规则策略或已接入的多因子实验策略；每次最多给3个方向，每个方向说明买入、卖出和风控思路。"
        "不要编造任何收益、回撤、胜率、Alpha/Beta 或已经回测过的结果。"
        "如果策略还不能直接回测，只说明需要补齐哪些条件；不要马上强迫用户填表。"
        "输出要中文、自然、简洁，最后给用户一个下一步选择，例如让用户选一个策略，或说“用默认配置跑第一个”。"
    )
    if provider.available:
        try:
            response = provider.chat(
                [{"role": "system", "content": system_prompt}, *_clean_llm_messages(request.messages)],
                temperature=0.35,
                timeout=45,
            )
            safe_content = _strip_unverified_backtest_claims(response.content)
            if safe_content != response.content or _contains_unsupported_idea_terms(safe_content):
                safe_content = _supported_strategy_ideas_message()
            return {
                "complete": False,
                "conversation_only": True,
                "strategy_ideation": True,
                "slots": request.slots or {},
                "message": safe_content,
                "provider_configured": True,
                "agent_source": "DeepSeek",
                "guarded": safe_content != response.content,
            }
        except Exception as exc:
            return {
                "complete": False,
                "conversation_only": True,
                "strategy_ideation": True,
                "slots": request.slots or {},
                "message": f"模型调用失败：{exc}",
                "provider_configured": True,
                "agent_source": "DeepSeek",
            }
    return {
        "complete": False,
        "conversation_only": True,
        "strategy_ideation": True,
        "slots": request.slots or {},
        "message": _supported_strategy_ideas_message(),
        "provider_configured": False,
        "agent_source": "local_strategy_ideas",
    }


def _contains_unsupported_idea_terms(text: str) -> bool:
    if not text:
        return False
    return any(term in text for term in UNSUPPORTED_IDEA_TERMS)


def _supported_strategy_ideas_message() -> str:
    return (
        "可以。我先给你三个当前能用真实行情落地验证的 A 股策略方向，不编造收益：\n\n"
        "1. MA20 放量趋势突破：收盘价站上 MA20，且成交量高于 20日均量时买入；跌回 MA20 或触发回撤止损时卖出。\n"
        "2. RSI + 布林带均值回归：价格接近布林带下轨且 RSI 偏低时买入；回到中轨、RSI 修复或风控触发时卖出。\n"
        "3. ATR 波动突破：收盘价突破近 N 日高点，并且 ATR 放大时买入；跌破移动止损线或趋势转弱时卖出。\n\n"
        "如果你想进入真实回测，可以直接说：用平安银行，2025.1.1到2026.4.30，日线，跑第一个策略。"
        "我会再生成规则和代码，不会在回测前给假结果。"
    )


def _is_general_chat(request: StrategyChatRequest) -> bool:
    text = _latest_user_message(request.messages).strip()
    if not text:
        return False
    lowered = text.lower()
    strategy_keywords = [
        "策略",
        "回测",
        "买入",
        "卖出",
        "止损",
        "止盈",
        "均线",
        "股票",
        "代码",
        "日线",
        "分钟",
        "开盘",
        "收盘",
        "交易",
        "平安银行",
        "中国平安",
        "贵州茅台",
        "策略",
        "回测",
        "买入",
        "卖出",
        "止损",
        "均线",
        "rsi",
        "atr",
        "布林",
        "股票",
        "平安",
        "代码",
        "收益",
        "仓",
        "日线",
        "分钟",
    ]
    if any(keyword in lowered or keyword in text for keyword in strategy_keywords):
        return False
    return len(text) <= 80


def _general_strategy_chat(request: StrategyChatRequest) -> dict[str, Any]:
    text = _latest_user_message(request.messages).strip()
    provider = get_llm_provider("deepseek")
    if provider.available:
        try:
            response = provider.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是龙虾量化 Lobster Quant 的 AI 策略工坊助手。"
                            "你的职责是帮助用户把自然语言交易想法补全为A股量化策略，并生成安全的 rqalpha 回测代码。"
                            "你必须遵守龙虾量化内置规则：真实数据优先，不编造回测结果；A股T+1和100股一手；默认单只股票；代码不得执行危险操作；策略生成前必须确认标的、时间、周期、资金、买入、卖出、止损、仓位、基准。"
                            "你要先像正常大模型一样对话；当用户开始描述策略时，主动确认标的、时间、周期、资金、买入、卖出、止损、仓位、基准。"
                            "中文回答，简洁清楚，不给确定性投资承诺。"
                        ),
                    },
                    *_clean_llm_messages(request.messages),
                ],
                temperature=0.25,
                timeout=45,
            )
            safe_content = _strip_unverified_backtest_claims(response.content)
            return {
                "complete": False,
                "conversation_only": True,
                "slots": request.slots or {},
                "message": safe_content,
                "provider_configured": True,
                "agent_source": "DeepSeek",
                "guarded": safe_content != response.content,
            }
        except Exception as exc:
            return {
                "complete": False,
                "conversation_only": True,
                "slots": request.slots or {},
                "message": f"模型调用失败：{exc}",
                "provider_configured": True,
                "agent_source": "DeepSeek",
            }
    return {
        "complete": False,
        "conversation_only": True,
        "slots": request.slots or {},
        "message": (
            "你好，我是龙虾量化的 AI 策略工坊助手。"
            "我可以帮你把 A 股交易想法整理成完整策略、生成 rqalpha 回测代码，并把结果送到回测实验室。"
            "当前 DeepSeek API Key 未配置，所以只能做基础引导；配置模型后可以进行完整对话和策略生成。"
        ),
        "provider_configured": False,
        "agent_source": "local_identity",
    }


def _normalize_stock_code(code: str) -> str:
    code = code.strip()
    if "." in code:
        return code.upper()
    if code.startswith("6"):
        return f"{code}.XSHG"
    return f"{code}.XSHE"


def _normalize_date(match: str) -> str:
    parts = re.split(r"[./-]", match)
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize_clock(hour: str, minute: str, second: str | None = None) -> str:
    return f"{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"


def _extract_percent_after(text: str, keywords: tuple[str, ...], default: float | None = None) -> float | None:
    for keyword in keywords:
        index = text.find(keyword)
        if index < 0:
            continue
        fragment = text[index:index + 36]
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", fragment)
        if match:
            return float(match.group(1)) / 100
    return default


def _extract_two_ma_windows(text: str) -> tuple[int, int] | None:
    patterns = [
        r"(\d{1,3})\s*(?:日|天)?\s*均线.{0,12}?(?:上穿|突破|站上|大于|强于).{0,12}?(\d{1,3})\s*(?:日|天)?\s*均线",
        r"(\d{1,3})\s*/\s*(\d{1,3})\s*(?:日|天)?\s*均线",
        r"(\d{1,3})\s*(?:日|天)?\s*(?:和|与|及)\s*(\d{1,3})\s*(?:日|天)?\s*均线",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def _find_indicator_action_thresholds(
    text: str,
    indicator: str,
    operators: tuple[str, ...],
    actions: tuple[str, ...],
    window: int = 28,
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    op_pattern = "|".join(re.escape(item) for item in operators)
    indicator_pattern = re.escape(indicator)
    all_action_words = ("买入", "买", "加仓", "开仓", "卖出", "卖", "清仓", "减仓", "止损", "止盈")
    separators = "，,；;\n。"

    for match in re.finditer(rf"{indicator_pattern}\s*(?:{op_pattern})\s*(-?\d{{1,4}})", text, re.IGNORECASE):
        clause_start = max((text.rfind(sep, 0, match.start()) for sep in separators), default=-1) + 1
        clause_end_candidates = [text.find(sep, match.end()) for sep in separators]
        clause_end_candidates = [index for index in clause_end_candidates if index >= 0]
        clause_end = min(clause_end_candidates) if clause_end_candidates else len(text)
        clause = text[clause_start:clause_end]
        threshold_pos = match.start() - clause_start

        nearest_action = ""
        nearest_distance = window + 1
        for action in all_action_words:
            search_from = 0
            while True:
                action_pos = clause.find(action, search_from)
                if action_pos < 0:
                    break
                distance = abs(action_pos - threshold_pos)
                if distance < nearest_distance:
                    nearest_action = action
                    nearest_distance = distance
                search_from = action_pos + len(action)

        if nearest_action in actions and nearest_distance <= window:
            results.append((match.group(0), int(match.group(1))))
    return results


def _threshold_expression(indicator: str, fragment: str, value: int) -> str:
    if re.search(r"(?:低于|小于|<|跌破|下穿)", fragment, re.IGNORECASE):
        return f"{indicator} < {value}"
    return f"{indicator} > {value}"


def _infer_rule_conditions(text: str) -> dict[str, str]:
    lowered = text.lower()
    buy_parts: list[str] = []
    sell_parts: list[str] = []

    ma_pair = _extract_two_ma_windows(text)
    if ma_pair:
        fast, slow = ma_pair
        buy_parts.append(f"ma{fast} > ma{slow}")
        sell_parts.append(f"ma{fast} < ma{slow}")

    for match in re.finditer(r"(?:收盘价|价格|股价|close).{0,10}?(?:站上|突破|上穿|大于|高于)\s*(\d{1,3})\s*(?:日|天)?\s*均线", text, re.IGNORECASE):
        buy_parts.append(f"close > ma{int(match.group(1))}")
    for match in re.finditer(r"(?:收盘价|价格|股价|close).{0,10}?(?:跌破|下穿|小于|低于)\s*(\d{1,3})\s*(?:日|天)?\s*均线", text, re.IGNORECASE):
        sell_parts.append(f"close < ma{int(match.group(1))}")

    breakout = re.search(r"(?:突破|创出|站上).{0,8}?(\d{1,3})\s*(?:日|天)?\s*(?:新高|高点|最高)", text)
    if breakout:
        buy_parts.append(f"close > high_max{int(breakout.group(1))}")
    breakdown = re.search(r"(?:跌破|创出|下破).{0,8}?(\d{1,3})\s*(?:日|天)?\s*(?:新低|低点|最低)", text)
    if breakdown:
        sell_parts.append(f"close < low_min{int(breakdown.group(1))}")

    if "放量" in text or "成交量放大" in text or "量能放大" in text:
        buy_parts.append("volume > volume_ma20 * 1.2")
    if "缩量" in text:
        sell_parts.append("volume < volume_ma20 * 0.8")

    rsi_buy_matches = _find_indicator_action_thresholds(
        text,
        "rsi",
        ("高于", "大于", ">", "升破", "低于", "小于", "<", "跌破", "下穿"),
        ("买入", "买"),
    )
    rsi_sell_matches = _find_indicator_action_thresholds(
        text,
        "rsi",
        ("高于", "大于", ">", "升破", "低于", "小于", "<", "跌破", "下穿"),
        ("卖出", "卖", "清仓", "减仓"),
    )
    for fragment, value in rsi_buy_matches:
        buy_parts.append(_threshold_expression("rsi", fragment, value))
    for fragment, value in rsi_sell_matches:
        sell_parts.append(_threshold_expression("rsi", fragment, value))
    has_contextual_rsi = bool(rsi_buy_matches or rsi_sell_matches)
    rsi_low = re.search(r"rsi\s*(?:低于|小于|<|跌破)\s*(\d{1,3})", lowered)
    if rsi_low and not has_contextual_rsi:
        buy_parts.append(f"rsi < {int(rsi_low.group(1))}")
    rsi_high = re.search(r"rsi\s*(?:高于|大于|>|升破)\s*(\d{1,3})", lowered)
    if rsi_high and not has_contextual_rsi:
        sell_parts.append(f"rsi > {int(rsi_high.group(1))}")
    if "rsi" in lowered and not rsi_low and not rsi_high and ("均线" in text or "ma" in lowered or "趋势" in text or "融合" in text or "确认" in text):
        buy_parts.append("rsi > 50")
        sell_parts.append("rsi < 45")
    if "超跌" in text and not rsi_low:
        buy_parts.append("rsi < 30")
    if "超买" in text and not rsi_high:
        sell_parts.append("rsi > 70")

    if "布林" in text or "boll" in lowered:
        if "下轨" in text:
            buy_parts.append("close < bb_lower")
        if "上轨" in text:
            sell_parts.append("close > bb_upper")
        if "中轨" in text:
            sell_parts.append("close > bb_mid")

    if "macd" in lowered or "金叉" in text:
        buy_parts.append("macd > macd_signal")
    if "死叉" in text:
        sell_parts.append("macd < macd_signal")

    cci_low = re.search(r"cci\s*(?:低于|小于|<|跌破)\s*(-?\d{1,4})", lowered)
    if cci_low:
        buy_parts.append(f"cci < {int(cci_low.group(1))}")
    cci_high = re.search(r"cci\s*(?:高于|大于|>|升破)\s*(-?\d{1,4})", lowered)
    if cci_high:
        sell_parts.append(f"cci > {int(cci_high.group(1))}")

    if "动量" in text or "强势" in text:
        window_match = re.search(r"(\d{1,3})\s*(?:日|天)?\s*动量", text)
        window = int(window_match.group(1)) if window_match else 20
        buy_parts.append(f"return_{window} > 0")

    if "atr" in lowered and ("放大" in text or "上升" in text):
        buy_parts.append("atr > atr_ma20")

    risk = _extract_percent_after(text, ("止损", "亏损", "回撤"), None)
    result: dict[str, str] = {}
    if buy_parts:
        result["buy_condition"] = " and ".join(dict.fromkeys(buy_parts))
    if sell_parts:
        result["sell_condition"] = " or ".join(dict.fromkeys(sell_parts))
    if risk is not None:
        result["stop_loss"] = f"drawdown > {risk:.4g}"
    return result


def _extract_execution_time(text: str) -> str | None:
    match = re.search(r"([01]?\d|2[0-3])\s*[:：点时]\s*([0-5]?\d)(?:\s*[:：分]\s*([0-5]?\d))?", text)
    if match:
        return _normalize_clock(match.group(1), match.group(2), match.group(3))
    if "开盘后一分钟" in text or "开盘一分钟" in text or "开盘 1 分钟" in text or "开盘1分钟" in text:
        return "09:31:00"
    explicit_open = (
        "开盘调仓",
        "开盘交易",
        "开盘执行",
        "开盘买入",
        "开盘卖出",
        "开盘后",
        "次日开盘",
        "第二天开盘",
    )
    explicit_close = (
        "收盘调仓",
        "收盘交易",
        "收盘执行",
        "收盘买入",
        "收盘卖出",
        "收盘前",
        "尾盘",
    )
    if any(term in text for term in explicit_open):
        return "09:31:00"
    if any(term in text for term in explicit_close):
        return "15:00:00"
    return None


def _extract_strategy_slots(request: StrategyChatRequest) -> dict[str, Any]:
    text = _all_user_text(request.messages)
    latest_text = _latest_user_message(request.messages)
    lowered = text.lower()
    slots = dict(request.slots or {})
    if latest_text:
        slots["raw_idea"] = latest_text
    execution_time = _extract_execution_time(text)
    if execution_time:
        slots["execution_time"] = execution_time

    code_match = re.search(r"\b([036]\d{5})(?:\.(?:XSHE|XSHG|SZ|SH))?\b", text, re.IGNORECASE)
    if code_match:
        slots["symbol"] = _normalize_stock_code(code_match.group(1))
    if "平安银行" in text or "000001" in text:
        slots["symbol"] = "000001.XSHE"
        slots["stock_name"] = "平安银行"
    elif "中国平安" in text or "601318" in text:
        slots["symbol"] = "601318.XSHG"
        slots["stock_name"] = "中国平安"
    elif "贵州茅台" in text or "600519" in text:
        slots["symbol"] = "600519.XSHG"
        slots["stock_name"] = "贵州茅台"

    if "平安银行" in text or "000001" in text:
        slots["symbol"] = "000001.XSHE"
        slots["stock_name"] = "平安银行"
    elif "中国平安" in text or "601318" in text:
        slots["symbol"] = "601318.XSHG"
        slots["stock_name"] = "中国平安"
    elif "贵州茅台" in text or "600519" in text:
        slots["symbol"] = "600519.XSHG"
        slots["stock_name"] = "贵州茅台"

    dates = re.findall(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", text)
    if len(dates) >= 2:
        slots["start_date"] = _normalize_date(dates[0])
        slots["end_date"] = _normalize_date(dates[1])
    elif len(dates) == 1 and ("开始" in text or "从" in text):
        slots["start_date"] = _normalize_date(dates[0])
    elif len(dates) == 1 and ("结束" in text or "到" in text):
        slots["end_date"] = _normalize_date(dates[0])
    if "最近两年" in text or "近两年" in text:
        slots.setdefault("start_date", "2024-01-01")
        slots.setdefault("end_date", "2026-05-23")

    if "日线" in text or "day" in lowered:
        slots["period"] = "day"
    if "60m" in lowered or ("60" in text and "分钟" in text):
        slots["period"] = "60m"
    elif "30m" in lowered or ("30" in text and "分钟" in text):
        slots["period"] = "30m"
    elif "15m" in lowered or ("15" in text and "分钟" in text):
        slots["period"] = "15m"
    elif "5m" in lowered or ("5" in text and ("分钟" in text or "min" in lowered)):
        slots["period"] = "5m"

    if "超跌" in text or re.search(r"rsi\s*(?:低于|小于|<|跌破)\s*\d{1,3}", lowered):
        slots["buy_condition"] = "rsi < 30"
        slots["sell_condition"] = "rsi > 55"
    elif "布林" in text or "boll" in lowered:
        slots["buy_condition"] = "close < bb_lower"
        slots["sell_condition"] = "close > bb_mid"
    elif ("5" in text and "20" in text and "均线" in text) or re.search(r"(?<!\d)5\D{0,12}20(?!\d)", text) or ("ma5" in lowered and "ma20" in lowered):
        slots["buy_condition"] = "ma5 > ma20"
        slots["sell_condition"] = "ma5 < ma20"
    elif "均线" in text or "ma" in lowered:
        slots.setdefault("buy_condition", "close > ma20")
        slots.setdefault("sell_condition", "close < ma20")

    if "成交量" in text and slots.get("buy_condition") == "close > ma20":
        slots["buy_condition"] = "close > ma20 and volume > volume_ma20 * 1.2"

    if "日线" in text:
        slots["period"] = "day"
    if "60分钟" in text or "60m" in lowered:
        slots["period"] = "60m"
    elif "30分钟" in text or "30m" in lowered:
        slots["period"] = "30m"
    elif "15分钟" in text or "15m" in lowered:
        slots["period"] = "15m"
    elif "5分钟" in text or "5m" in lowered:
        slots["period"] = "5m"

    if "超跌" in text or re.search(r"rsi\s*(?:低于|小于|<|跌破)\s*\d{1,3}", lowered):
        slots["buy_condition"] = "rsi < 30"
        slots["sell_condition"] = "rsi > 55"
    elif "布林" in text or "boll" in lowered:
        slots["buy_condition"] = "close < bb_lower"
        slots["sell_condition"] = "close > bb_mid"
    elif ("5" in text and "20" in text and "均线" in text) or ("ma5" in lowered and "ma20" in lowered):
        slots["buy_condition"] = "ma5 > ma20"
        slots["sell_condition"] = "ma5 < ma20"
    elif "均线" in text or "ma" in lowered:
        slots.setdefault("buy_condition", "close > ma20")
        slots.setdefault("sell_condition", "close < ma20")

    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if "止损" in text or "亏损" in text or "回撤" in text:
        value = 0.08
        if percent_match:
            value = float(percent_match.group(1)) / 100
        slots["stop_loss"] = f"drawdown > {value:.4g}"
    if "满仓" in text:
        slots["position_rule"] = "满仓"
    elif "半仓" in text:
        slots["position_rule"] = "半仓"
    elif "固定" in text and "仓" in text:
        slots["position_rule"] = "固定比例"
    cash_match = re.search(r"(\d+(?:\.\d+)?)\s*(万|w|W)", text)
    if cash_match:
        slots["initial_cash"] = int(float(cash_match.group(1)) * 10000)
    else:
        numeric_cash = re.search(r"(?:初始资金|本金|资金|目标金额).*?(\d{5,})", text)
        if numeric_cash:
            slots["initial_cash"] = int(numeric_cash.group(1))
    if "沪深300" in text or "000300" in text:
        slots["benchmark"] = "000300.XSHG"
    elif "上证指数" in text or "000001" in text and "指数" in text:
        slots["benchmark"] = "000001.XSHG"
    elif "中证500" in text or "000905" in text:
        slots["benchmark"] = "000905.XSHG"

    inferred_conditions = _infer_rule_conditions(text)
    for key, value in inferred_conditions.items():
        if value:
            slots[key] = value
    return slots


def _missing_strategy_slots(slots: dict[str, Any]) -> list[str]:
    required = {
        "symbol": "股票代码或股票池",
        "period": "交易周期",
        "start_date": "回测开始时间",
        "end_date": "回测结束时间",
        "buy_condition": "买入条件",
        "sell_condition": "卖出条件",
    }
    return [key for key in required if not slots.get(key)]


def _slot_questions(missing: list[str]) -> list[str]:
    labels = {
        "symbol": "你希望回测哪只股票或哪个股票池？",
        "period": "交易周期用日线、60分钟、30分钟、15分钟、5分钟还是1分钟？",
        "start_date": "回测从哪一天开始？",
        "end_date": "回测到哪一天结束？",
        "buy_condition": "什么时候买入？请尽量说成可判断的条件。",
        "sell_condition": "什么时候卖出？",
    }
    return [labels[key] for key in missing[:3]]


def _apply_default_slots(slots: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "mode": "single_stock",
        "symbol": "000001.XSHE",
        "stock_name": "平安银行",
        "period": "day",
        "start_date": "2024-01-01",
        "end_date": "2026-05-23",
        "buy_condition": "close > ma20",
        "sell_condition": "close < ma20",
        "stop_loss": "drawdown > 0.08",
        "position_rule": "满仓",
        "initial_cash": 1000000,
        "commission": 0.0003,
        "slippage": 0.0005,
        "benchmark": "000300.XSHG",
        "adjust": "qfq",
    }
    return {**defaults, **slots}


@router.get("/audit-logs")
def audit_logs(limit: int = 100) -> dict[str, Any]:
    return {"items": audit_logger.tail(limit)}


@router.get("/tools")
def tools() -> dict[str, Any]:
    return {
        "tools": tool_registry.list_tools(),
        "providers": list_llm_providers(),
        "security": {
            "live_trade_enabled": False,
            "default_scopes": ["READ_MARKET", "READ_NEWS", "RUN_BACKTEST", "GENERATE_STRATEGY", "DEBUG_STRATEGY"],
            "disabled_scopes": ["LIVE_TRADE_DISABLED"],
        },
    }


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str, task_type: str = "market_watch") -> StreamingResponse:
    def event_stream():
        for index, step in enumerate(planned_agent_steps(task_type), start=1):
            payload = {"task_id": task_id, "step": index, "message": step, "done": False}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            time.sleep(0.25)
        yield f"data: {json.dumps({'task_id': task_id, 'message': '任务完成', 'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
