from __future__ import annotations

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.news_agent import NewsAgent
from app.agents.risk_agent import RiskAgent
from app.agents.technical_agent import TechnicalAgent
from app.providers.provider_factory import get_llm_provider


AGENT_ALIASES = {
    "技术面": "technical",
    "技术": "technical",
    "K线": "technical",
    "k线": "technical",
    "走势": "technical",
    "消息面": "news",
    "消息": "news",
    "新闻": "news",
    "资讯": "news",
    "风控": "risk",
    "风险": "risk",
    "回撤": "risk",
    "量化": "quant",
    "回测": "quant",
    "交易": "quant",
    "策略": "strategy",
    "策略生成": "strategy",
    "委员会": "committee",
    "投研委员会": "committee",
}

AGENT_LABELS = {
    "technical": "技术面 Agent",
    "news": "消息面 Agent",
    "risk": "风控 Agent",
    "quant": "量化回测 Agent",
    "strategy": "策略 Agent",
    "committee": "投研委员会",
}


class MarketWatchAgent(BaseAgent):
    name = "market_watch_agent"
    description = "行情盯盘 Agent"
    permissions = ("READ_MARKET", "READ_NEWS", "GENERATE_ANALYSIS")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        bars = payload.get("bars") or []
        quote = payload.get("quote") or {}
        news_items = payload.get("news") or []
        question = str(payload.get("question") or payload.get("query") or "").strip()
        targets = self._resolve_target_agents(payload, question)

        if targets:
            result = self._targeted_chat(payload, targets)
            self.log("market_watch_targeted_chat", payload, {"targets": targets, "provider": result.get("source")})
            return result

        if self._is_general_question(question):
            result = self._general_chat(payload, question)
            self.log("market_watch_chat", payload, {"provider_configured": result.get("provider_configured")})
            return result

        if len(bars) < 2:
            result = {
                "success": False,
                "symbol": payload.get("symbol"),
                "name": payload.get("name", ""),
                "message": "缺少真实行情数据，暂无法生成个股分析。",
                "basis": {
                    "quote_time": quote.get("timestamp") or "",
                    "bars_count": len(bars),
                    "news_count": len(news_items),
                    "data_source": quote.get("source") or payload.get("data_source") or "",
                },
            }
            self.log("market_watch_committee", payload, result, "warning")
            return result

        result = self._committee_analysis(payload)
        self.log("market_watch_committee", payload, {"confidence": result.get("confidence")})
        return result

    def _resolve_target_agents(self, payload: dict[str, Any], question: str) -> list[str]:
        requested = payload.get("target_agents") or []
        targets: list[str] = []
        for item in requested:
            normalized = self._normalize_agent_name(str(item))
            if normalized and normalized not in targets:
                targets.append(normalized)

        for alias, value in AGENT_ALIASES.items():
            if f"@{alias}" in question or f"＠{alias}" in question:
                if value == "committee":
                    return ["technical", "news", "risk", "quant"]
                if value not in targets:
                    targets.append(value)
        return targets

    def _normalize_agent_name(self, name: str) -> str:
        clean = name.strip().replace("@", "").replace("＠", "")
        return AGENT_ALIASES.get(clean) or clean if clean in AGENT_LABELS else ""

    def _targeted_chat(self, payload: dict[str, Any], targets: list[str]) -> dict[str, Any]:
        bars = payload.get("bars") or []
        quote = payload.get("quote") or {}
        news_items = payload.get("news") or []
        outputs: dict[str, Any] = {}

        if "technical" in targets:
            outputs["technical"] = TechnicalAgent().run(payload)
        if "news" in targets:
            outputs["news"] = NewsAgent().run(payload)
        if "risk" in targets:
            outputs["risk"] = RiskAgent().run(payload)
        if "quant" in targets:
            outputs["quant"] = self._quant_view(payload)
        if "strategy" in targets:
            outputs["strategy"] = self._strategy_view(payload)

        basis = {
            "quote_time": quote.get("timestamp") or (bars[-1].get("time", "") if bars else ""),
            "bars_count": len(bars),
            "news_count": len(news_items),
            "data_source": quote.get("source") or payload.get("data_source") or "",
        }
        answer = self._compose_targeted_answer(payload, targets, outputs, basis)
        return {
            "success": True,
            "symbol": payload.get("symbol"),
            "name": payload.get("name", ""),
            "basis": basis,
            "target_agents": targets,
            "agent_labels": [AGENT_LABELS.get(item, item) for item in targets],
            "specialist_outputs": outputs,
            "answer": answer["text"],
            "final_summary": answer["text"],
            "confidence": answer["confidence"],
            "agent_mode": "targeted_agents",
            "provider_configured": answer["provider_configured"],
            "source": answer["source"],
            "skills_used": self._skills_for_targets(targets),
        }

    def _compose_targeted_answer(
        self,
        payload: dict[str, Any],
        targets: list[str],
        outputs: dict[str, Any],
        basis: dict[str, Any],
    ) -> dict[str, Any]:
        provider = get_llm_provider("deepseek")
        question = payload.get("question") or payload.get("query") or ""
        labels = [AGENT_LABELS.get(item, item) for item in targets]
        if provider.available:
            try:
                response = provider.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是龙虾量化的专职 Agent 调度器。用户通过 @ 点名了一个或多个专职 Agent。"
                                "你只能基于输入里的真实行情、消息、指标、交易和专职 Agent 输出回答，不允许编造数据。"
                                "请用中文，先标明本次响应由哪些 Agent 参与，再给出简洁、有依据、有风险提示的结论。"
                                "不要给确定性买卖建议。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "question": question,
                                    "symbol": payload.get("symbol"),
                                    "name": payload.get("name"),
                                    "basis": basis,
                                    "target_agents": labels,
                                    "specialist_outputs": outputs,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    temperature=0.25,
                    timeout=45,
                )
                return {
                    "text": response.content,
                    "confidence": 0.66,
                    "provider_configured": True,
                    "source": "DeepSeek",
                }
            except Exception as exc:
                return {
                    "text": f"已调用 {', '.join(labels)}，但 DeepSeek 汇总失败：{exc}",
                    "confidence": 0.2,
                    "provider_configured": True,
                    "source": "DeepSeek",
                }

        parts = [f"本次由 {', '.join(labels)} 响应。当前模型未配置，先展示各专职 Agent 基于真实输入得到的结果："]
        if outputs.get("technical"):
            parts.append(f"技术面：{outputs['technical'].get('technical_view') or outputs['technical'].get('message') or '暂无技术结论'}")
        if outputs.get("news"):
            parts.append(f"消息面：{outputs['news'].get('news_view') or '暂无消息结论'}")
        if outputs.get("risk"):
            parts.append(f"风控：{outputs['risk'].get('risk_view') or '暂无风控结论'}")
        if outputs.get("quant"):
            parts.append(f"量化回测：{outputs['quant'].get('quant_view')}")
        if outputs.get("strategy"):
            parts.append(f"策略：{outputs['strategy'].get('strategy_view')}")
        return {
            "text": "\n".join(parts),
            "confidence": 0.35,
            "provider_configured": False,
            "source": "local_agent_outputs",
        }

    def _committee_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        bars = payload.get("bars") or []
        quote = payload.get("quote") or {}
        news_items = payload.get("news") or []
        technical = TechnicalAgent().run(payload)
        news = NewsAgent().run(payload)
        risk = RiskAgent().run(payload)
        trend = technical.get("trend_state", "震荡")
        sentiment = news.get("news_sentiment", "中性")
        bull_case = f"若价格继续保持在关键均线上方，且成交量维持放大，{payload.get('name') or payload.get('symbol')}有延续反弹的条件。"
        bear_case = "如果价格跌破短线支撑或消息面转弱，当前结构可能重新回到震荡甚至走弱。"
        final_summary = (
            f"综合技术面、消息面和风控信号，当前更适合观察突破确认。"
            f"技术结构为{trend}，消息面{sentiment}，不宜仅凭单一上涨信号追入。"
        )
        confidence = 0.58
        if trend in {"震荡偏强", "短线快速上行"}:
            confidence += 0.08
        if sentiment == "偏利好":
            confidence += 0.06
        if risk.get("risk_level") == "高":
            confidence -= 0.1
        basis = {
            "quote_time": quote.get("timestamp") or bars[-1].get("time", ""),
            "bars_count": len(bars),
            "news_count": len(news_items),
            "data_source": quote.get("source") or payload.get("data_source") or "",
        }
        result = {
            "success": True,
            "symbol": payload.get("symbol"),
            "name": payload.get("name", ""),
            "basis": basis,
            "technical_view": technical.get("technical_view", ""),
            "news_view": news.get("news_view", ""),
            "risk_view": risk.get("risk_view", ""),
            "bull_case": bull_case,
            "bear_case": bear_case,
            "final_summary": final_summary,
            "confidence": round(max(0.05, min(0.95, confidence)), 2),
            "sources": news.get("sources", []),
            "answer": f"{final_summary}\n\n技术面：{technical.get('technical_view', '')}\n消息面：{news.get('news_view', '')}\n风险面：{risk.get('risk_view', '')}",
            "agent_mode": "local_rules",
            "provider_configured": False,
            "skills_used": ["technical_indicator", "news_fetch", "risk_check"],
        }
        if not self._complete_with_llm(payload, result):
            result["success"] = False
            result["message"] = result.get("provider_error") or "DeepSeek API Key 未配置，无法生成真实 AI 回答。"
            result["answer"] = ""
        return result

    def _quant_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("metrics") or {}
        trades = payload.get("trades") or []
        if not metrics and not trades:
            return {
                "quant_view": "当前没有可用的回测结果或交易记录。请先在工坊生成策略并运行回测，再让量化回测 Agent 分析。",
                "available": False,
            }
        total_return = metrics.get("total_return")
        alpha = metrics.get("alpha")
        beta = metrics.get("beta")
        max_drawdown = metrics.get("max_drawdown")
        trade_count = metrics.get("trade_count") or len(trades)
        return {
            "quant_view": (
                f"当前回测记录显示：累计收益 {self._pct(total_return)}，Alpha {self._num(alpha)}，"
                f"Beta {self._num(beta)}，最大回撤 {self._pct(max_drawdown)}，交易次数 {trade_count}。"
                "这些指标必须结合基准曲线、样本长度和交割单一起看。"
            ),
            "available": True,
            "metrics": metrics,
            "trade_count": trade_count,
        }

    def _strategy_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "strategy_view": (
                "策略 Agent 负责把自然语言想法整理成可回测规则。"
                "一个可执行策略至少需要标的、回测区间、周期、买入条件和卖出条件；止盈止损可以不强制，"
                "但若缺少风控，回测分析会单独提示风险。"
            )
        }

    def _skills_for_targets(self, targets: list[str]) -> list[str]:
        skills = []
        if "technical" in targets:
            skills.append("technical_indicator")
        if "news" in targets:
            skills.append("news_fetch")
        if "risk" in targets:
            skills.append("risk_check")
        if "quant" in targets:
            skills.append("backtest_metrics")
        if "strategy" in targets:
            skills.append("strategy_generation")
        return skills

    def _is_general_question(self, question: str) -> bool:
        if not question:
            return False
        if "@" in question or "＠" in question:
            return False
        lowered = question.lower()
        analysis_keywords = [
            "分析",
            "走势",
            "k线",
            "K线",
            "买",
            "卖",
            "风险",
            "消息",
            "新闻",
            "技术面",
            "基本面",
            "回测",
            "策略",
            "支撑",
            "压力",
            "涨",
            "跌",
            "量能",
            "成交",
        ]
        if any(keyword in question or keyword in lowered for keyword in analysis_keywords):
            return False
        return len(question) <= 80

    def _general_chat(self, payload: dict[str, Any], question: str) -> dict[str, Any]:
        provider = get_llm_provider("deepseek")
        basis = {
            "quote_time": (payload.get("quote") or {}).get("timestamp") or "",
            "bars_count": len(payload.get("bars") or []),
            "news_count": len(payload.get("news") or []),
            "data_source": (payload.get("quote") or {}).get("source") or payload.get("data_source") or "",
        }
        if provider.available:
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "你是龙虾量化 Lobster Quant 的 AI 投研助手。"
                            "你可以帮助用户理解行情、消息面、风险、策略和回测流程。"
                            "你运行在一个A股AI量化工作站里，内置约束包括：真实行情优先、禁止假数据、A股T+1、100股一手、rqalpha回测、策略生成前需要补全关键条件。"
                            "用户只是打招呼或询问产品能力时，像正常大模型一样自然回答。中文回答，简洁清楚。"
                        ),
                    },
                    *[
                        {"role": str(item.get("role", "user")), "content": str(item.get("content", "") or "")}
                        for item in (payload.get("messages") or [])[-8:]
                        if item.get("content")
                    ],
                ]
                if not any(item["role"] == "user" and item["content"] == question for item in messages):
                    messages.append({"role": "user", "content": question})
                response = provider.chat(messages, temperature=0.25, timeout=45)
                return {
                    "success": True,
                    "symbol": payload.get("symbol"),
                    "name": payload.get("name", ""),
                    "basis": basis,
                    "answer": response.content,
                    "final_summary": response.content,
                    "confidence": 0.5,
                    "agent_mode": "deepseek_general_chat",
                    "provider_configured": True,
                    "source": "DeepSeek",
                    "skills_used": [],
                }
            except Exception as exc:
                return {
                    "success": False,
                    "symbol": payload.get("symbol"),
                    "name": payload.get("name", ""),
                    "basis": basis,
                    "message": f"DeepSeek 调用失败：{exc}",
                    "answer": "",
                    "provider_configured": True,
                    "source": "DeepSeek",
                }
        answer = (
            "你好，我是龙虾量化的 AI 投研助手。"
            "我可以帮你看当前股票、解释 K 线和消息面、提醒风险，也可以引导你去工坊生成策略并送到回测实验室。"
            "你也可以输入 @技术面、@消息面、@风控、@量化 来点名专职 Agent。"
        )
        return {
            "success": True,
            "symbol": payload.get("symbol"),
            "name": payload.get("name", ""),
            "basis": basis,
            "answer": answer,
            "final_summary": answer,
            "confidence": 0.3,
            "agent_mode": "local_identity",
            "provider_configured": False,
            "source": "local",
            "skills_used": [],
        }

    def _complete_with_llm(self, payload: dict[str, Any], result: dict[str, Any]) -> bool:
        provider = get_llm_provider("deepseek")
        result["provider_configured"] = provider.available
        if not provider.available:
            result["provider_error"] = "DeepSeek API Key 未配置，无法生成真实 AI 回答。"
            return False
        question = payload.get("question") or "请分析当前股票。"
        messages = payload.get("messages") or []
        recent_dialogue = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages[-6:]
        )
        news_titles = [
            {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "time": item.get("time", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary", ""),
            }
            for item in (payload.get("news") or [])[:6]
        ]
        prompt = {
            "symbol": payload.get("symbol"),
            "name": payload.get("name"),
            "question": question,
            "basis": result.get("basis"),
            "technical_view": result.get("technical_view"),
            "news_view": result.get("news_view"),
            "risk_view": result.get("risk_view"),
            "bull_case": result.get("bull_case"),
            "bear_case": result.get("bear_case"),
            "recent_dialogue": recent_dialogue,
            "news": news_titles,
        }
        try:
            llm = provider.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是龙虾量化的A股AI投研委员会。你只能基于输入中的真实行情、K线、消息和技术/风控Skill结果回答。"
                            "不得给确定性买卖承诺，不得伪造新闻，不得假装有未提供的数据。"
                            "请输出JSON，字段包括 answer、technical_view、news_view、risk_view、bull_case、bear_case、final_summary、confidence。"
                            "answer要像对话回复，中文、专业、简洁，必须说明依据和风险。"
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                timeout=45,
            )
            for key in [
                "answer",
                "technical_view",
                "news_view",
                "risk_view",
                "bull_case",
                "bear_case",
                "final_summary",
            ]:
                if llm.get(key):
                    result[key] = str(llm[key])
            if isinstance(llm.get("confidence"), (int, float)):
                result["confidence"] = round(max(0.05, min(0.95, float(llm["confidence"]))), 2)
            result["agent_mode"] = "deepseek_agent_committee"
            result["source"] = "DeepSeek"
            return True
        except Exception as exc:
            result["provider_error"] = str(exc)
            result["answer"] = ""
            return False

    def _pct(self, value: Any) -> str:
        try:
            number = float(value)
        except Exception:
            return "--"
        return f"{number * 100:+.2f}%"

    def _num(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "--"
