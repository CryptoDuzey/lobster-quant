from __future__ import annotations

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.providers.provider_factory import get_llm_provider


FINANCIAL_AGENT_ROLES = {
    "orchestrator": "协调 Agent",
    "research": "投研 Agent",
    "strategy": "策略 Agent",
    "risk": "风控 Agent",
    "backtest": "回测 Agent",
    "data": "数据 Agent",
}


class FinancialAgent(BaseAgent):
    name = "financial_agent"
    description = "跨页面金融 Agent，负责自由金融对话、策略研究、回测解释和风险分析"
    permissions = ("READ_MARKET", "READ_NEWS", "RUN_BACKTEST", "GENERATE_STRATEGY")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or payload.get("question") or "").strip()
        messages = payload.get("messages") or []
        page = str(payload.get("page") or payload.get("context", {}).get("page") or "")
        context = payload.get("context") or {}
        provider = get_llm_provider("deepseek")
        roles = self._select_roles(query, page)
        basis = self._basis(context, page)

        if not query:
            return {
                "success": False,
                "message": "请先输入你想问的金融、策略或回测问题。",
                "agent_labels": [FINANCIAL_AGENT_ROLES[item] for item in roles],
                "basis": basis,
                "provider_configured": bool(provider.available),
            }

        if provider.available:
            try:
                response = provider.chat(
                    [
                        {"role": "system", "content": self._system_prompt(page, roles)},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "query": query,
                                    "page": page,
                                    "context": context,
                                    "recent_messages": self._clean_messages(messages),
                                    "selected_roles": [FINANCIAL_AGENT_ROLES[item] for item in roles],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    temperature=0.25,
                    timeout=110,
                )
                result = {
                    "success": True,
                    "answer": response.content,
                    "final_summary": response.content,
                    "agent_mode": "financial_agent",
                    "agent_labels": [FINANCIAL_AGENT_ROLES[item] for item in roles],
                    "roles": roles,
                    "basis": basis,
                    "provider_configured": True,
                    "source": "DeepSeek",
                    "architecture_reference": [
                        "TradingAgents 风格：按技术/研究/风控/回测等角色拆分任务",
                        "FinRobot 风格：金融分析任务先做数据与概念整理，再输出结论",
                        "FinGPT 风格：金融文本处理与情绪/摘要能力作为后续 Skill 扩展",
                    ],
                }
                self.log("financial_agent_chat", payload, {"roles": roles, "provider": "DeepSeek"})
                return result
            except Exception as exc:
                message = f"金融 Agent 调用模型失败：{exc}"
        else:
            message = "模型 API Key 尚未配置，金融 Agent 只能做基础规则说明，不能进行真实模型对话。你可以在能力中心配置 DeepSeek、OpenAI、Claude、Kimi 等模型。"

        result = {
            "success": False,
            "answer": message,
            "final_summary": message,
            "agent_mode": "financial_agent",
            "agent_labels": [FINANCIAL_AGENT_ROLES[item] for item in roles],
            "roles": roles,
            "basis": basis,
            "provider_configured": False,
            "source": "local_financial_agent",
        }
        self.log("financial_agent_chat_failed", payload, {"roles": roles, "message": message}, "warning")
        return result

    def _select_roles(self, query: str, page: str) -> list[str]:
        text = query.lower()
        roles = ["orchestrator"]
        broad_market_terms = ("大A", "A股", "大盘", "市场", "牛市", "熊市", "未来", "怎么看", "宏观", "政策", "流动性")
        if any(term in query for term in broad_market_terms):
            roles.append("research")
            roles.append("risk")
            roles.append("data")
        if page in {"workshop", "strategy", "strategy-workshop"} or any(term in query for term in ("策略", "代码", "买入", "卖出")):
            roles.append("strategy")
        if page in {"backtest", "backtest-lab"} or any(term in query for term in ("回测", "收益", "alpha", "beta", "夏普", "回撤")):
            roles.append("backtest")
        if any(term in query for term in ("风险", "止损", "回撤", "波动", "仓位")):
            roles.append("risk")
        if any(term in query for term in ("数据", "行情", "财务", "宏观", "因子", "消息")) or "factor" in text:
            roles.append("data")
        if len(roles) == 1:
            roles.append("research")
        return list(dict.fromkeys(roles))

    def _basis(self, context: dict[str, Any], page: str) -> dict[str, Any]:
        return {
            "page": page,
            "has_backtest_result": bool(context.get("backtest_result") or context.get("metrics")),
            "has_strategy": bool(context.get("strategy_json") or context.get("generated_code")),
            "has_market_context": bool(context.get("symbol") or context.get("bars_count") or context.get("quote")),
            "data_rule": "只基于当前页面传入的真实数据、策略和回测结果回答；数据不足必须说明。",
        }

    def _clean_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for item in messages[-8:]:
            role = "assistant" if item.get("role") == "assistant" else "user"
            content = str(item.get("content") or "")
            if content:
                cleaned.append({"role": role, "content": content[:1200]})
        return cleaned

    def _system_prompt(self, page: str, roles: list[str]) -> str:
        role_text = "、".join(FINANCIAL_AGENT_ROLES[item] for item in roles)
        return (
            "你是龙虾量化 Lobster Quant 的金融 Agent，是一个可以自由对话的 A 股金融研究助手。"
            f"当前页面是 {page or '未知页面'}，本轮参与角色：{role_text}。"
            "你的设计借鉴 TradingAgents 的多角色投研分工、FinRobot 的金融分析 Agent 思路、FinGPT 的金融文本处理思路，"
            "但必须服务于中国A股、rqalpha回测和龙虾量化现有数据。"
            "你可以回答宏观市场看法、金融概念、投资大师思想、策略设计、回测解释、风险检查、数据需求和下一步操作。"
            "用户问宽泛市场问题时，比如“怎么看未来的大A”，不要机械地要求他补策略条件；"
            "应该用情景分析方式回答：政策与流动性、盈利周期、估值位置、资金结构、风险点、可验证指标。"
            "如果上下文没有实时宏观或指数数据，请明确说“以下是框架性判断，不是基于最新实时数据的结论”。"
            "不要编造行情、收益、Alpha/Beta、胜率、交易次数或已经完成的回测。"
            "如果用户要求生成策略，先判断条件是否足够；不够就追问；够了就说明可以交给策略工坊生成代码。"
            "如果用户问回测结果，只能基于上下文已有结果分析；没有结果就说需要先运行真实回测。"
            "输出中文，直接、清楚、专业，可以表达概率和分歧，但不要给确定性投资建议。"
        )
