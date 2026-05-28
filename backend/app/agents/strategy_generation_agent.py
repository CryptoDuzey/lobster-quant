from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.skills.risk_check_skill import strategy_safety_check
from app.skills.strategy_codegen_skill import StrategyCodegenSkill


ALLOWED_RULE_VARIABLES = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ma20",
    "ma5",
    "ma10",
    "ma30",
    "ma60",
    "atr",
    "atr_ma20",
    "volume_ma20",
    "rsi",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "cci",
    "drawdown",
    "cash",
    "position_quantity",
    "closable",
    "cost_basis",
    "stop_loss_price",
    "macd",
    "macd_signal",
    "macd_hist",
}


def _rule(expression: str, description: str, rule_id: str) -> dict[str, str]:
    return {"id": rule_id, "description": description, "expression": expression}


def fallback_strategy_json(payload: dict[str, Any]) -> dict[str, Any]:
    framework = payload.get("framework") or {}
    text = " ".join(
        str(value or "")
        for value in [
            payload.get("user_input"),
            payload.get("idea"),
            payload.get("buy_idea"),
            payload.get("sell_idea"),
            framework.get("buy"),
            framework.get("sell"),
        ]
    ).lower()
    if ("rsi" in text and ("均线" in text or "ma" in text or "趋势" in text or "融合" in text)) or ("rsi" in text and "5" in text and "20" in text):
        name = "均线 + RSI 趋势确认策略"
        strategy_type = "复合趋势策略"
        buy_rules = [
            _rule("ma5 > ma20", "短期均线强于长期均线", "buy_ma_rsi_001"),
            _rule("rsi > 50", "RSI 位于强弱分界上方", "buy_ma_rsi_002"),
        ]
        sell_rules = [
            _rule("ma5 < ma20", "短期均线弱于长期均线", "sell_ma_rsi_001"),
            _rule("rsi < 45", "RSI 转弱", "sell_ma_rsi_002"),
        ]
    elif "rsi" in text or "超跌" in text:
        name = "RSI 超跌反转策略"
        strategy_type = "均值回归"
        buy_rules = [_rule("rsi < 30", "RSI 低于 30，进入超跌区间", "buy_rsi_001")]
        sell_rules = [_rule("rsi > 55", "RSI 回升至 55 上方", "sell_rsi_001")]
    elif "布林" in text or "boll" in text or "bb_" in text:
        name = "布林带均值回归策略"
        strategy_type = "均值回归"
        buy_rules = [_rule("close < bb_lower", "收盘价跌破布林下轨", "buy_boll_001")]
        sell_rules = [_rule("close > bb_mid", "收盘价回到布林中轨上方", "sell_boll_001")]
    elif "5" in text and "20" in text:
        name = "5日 / 20日均线交叉策略"
        strategy_type = "趋势策略"
        buy_rules = [_rule("ma5 > ma20", "5日均线强于20日均线", "buy_ma_001")]
        sell_rules = [_rule("ma5 < ma20", "5日均线弱于20日均线", "sell_ma_001")]
    else:
        name = "MA20 成交量突破策略"
        strategy_type = "单股趋势策略"
        buy_rules = [
            _rule("close > ma20", framework.get("buy") or "收盘价站上 MA20", "buy_001"),
            _rule("volume > volume_ma20 * 1.2", "成交量放大", "buy_002"),
        ]
        sell_rules = [_rule("close < ma20", framework.get("sell") or "收盘价跌破 MA20", "sell_001")]
    return {
        "strategy_name": name,
        "strategy_type": strategy_type,
        "symbol": payload.get("symbol", "000001.XSHE"),
        "period": payload.get("period", "day"),
        "rules": {
            "buy_rules": buy_rules,
            "sell_rules": sell_rules,
            "risk_rules": [_rule("drawdown > 0.08", framework.get("stop") or "最大回撤超过 8% 止损", "risk_001")],
        },
        "params": {
            "initial_cash": 1000000,
            "commission": 0.0003,
            "slippage": 0.0005,
            "t_plus_one": True,
            "round_lot": 100,
            "ma_window": 20,
            "atr_window": 14,
            **({"execution_time": framework.get("execution_time")} if framework.get("execution_time") else {}),
        },
        "explanation": "使用本地规则解析生成，不伪装为 AI 结果。正式环境可配置多模型 Provider 生成更贴近用户意图的策略。",
    }

def normalize_strategy_json(strategy_json: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    framework = payload.get("framework") or {}
    strategy_json = dict(strategy_json or {})
    strategy_json["symbol"] = framework.get("symbol") or strategy_json.get("symbol") or payload.get("symbol", "000001.XSHE")
    strategy_json["period"] = framework.get("period") or strategy_json.get("period") or payload.get("period", "day")

    rules = strategy_json.get("rules") or {}
    buy_rules = rules.get("buy_rules") if isinstance(rules.get("buy_rules"), list) else []
    sell_rules = rules.get("sell_rules") if isinstance(rules.get("sell_rules"), list) else []
    risk_rules = rules.get("risk_rules") if isinstance(rules.get("risk_rules"), list) else []

    buy_expression = framework.get("buy_condition") or payload.get("buy_idea") or rules.get("buy")
    sell_expression = framework.get("sell_condition") or payload.get("sell_idea") or rules.get("sell")
    risk_expression = framework.get("stop_loss") or payload.get("risk_idea") or rules.get("stop_loss")

    if buy_expression:
        buy_rules = [_rule(str(buy_expression), "用户指定买入条件", "buy_user_001")]
    if sell_expression:
        sell_rules = [_rule(str(sell_expression), "用户指定卖出条件", "sell_user_001")]
    if risk_expression:
        risk_rules = [_rule(str(risk_expression), "用户指定风控条件", "risk_user_001")]

    strategy_json["rules"] = {
        "buy_rules": buy_rules or [_rule("close > ma20", "默认买入条件", "buy_default_001")],
        "sell_rules": sell_rules or [_rule("close < ma20", "默认卖出条件", "sell_default_001")],
        "risk_rules": risk_rules,
    }
    return strategy_json


class StrategyGenerationAgent(BaseAgent):
    name = "strategy_generation_agent"
    description = "自然语言策略生成和 rqalpha 代码生成 Agent"
    permissions = ("GENERATE_STRATEGY", "RUN_BACKTEST")

    def _llm_strategy(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.provider.available:
            return None
        prompt = (
            "你是龙虾量化的A股策略生成Agent。只返回JSON，必须中文。"
            "先把自然语言转成结构化策略JSON，再由系统安全生成rqalpha代码。"
            "表达式只能使用 open, high, low, close, volume, atr, rsi, bb_mid, bb_upper, bb_lower, cci, macd, macd_signal, macd_hist, drawdown, cash, position_quantity, closable, cost_basis, stop_loss_price，"
            "也可以使用动态指标 maN、volume_maN、atr_maN、high_maxN、low_minN、return_N、rsiN，例如 ma7、ma55、high_max20、return_60。"
            "JSON字段：strategy_name、strategy_type、symbol、period、rules、params、explanation。"
        )
        return self.provider.chat_json(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": str(payload)},
            ],
            temperature=0.15,
        )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        llm_strategy = self._llm_strategy(payload)
        source = self.provider.name if llm_strategy else "本地规则解析"
        strategy_json = normalize_strategy_json(llm_strategy or fallback_strategy_json(payload), payload)
        framework = payload.get("framework") or {}
        params = dict(strategy_json.get("params") or {})
        for source_key, target_key in [
            ("initial_cash", "initial_cash"),
            ("commission", "commission"),
            ("slippage", "slippage"),
            ("benchmark", "benchmark"),
            ("execution_time", "execution_time"),
        ]:
            if framework.get(source_key) is not None and params.get(target_key) is None:
                params[target_key] = framework[source_key]
        strategy_json["params"] = params
        code_payload = {
            "symbol": strategy_json.get("symbol") or payload.get("symbol"),
            "period": strategy_json.get("period") or payload.get("period", "day"),
            "start_date": payload.get("start_date", "2025-01-01"),
            "end_date": payload.get("end_date", "2026-05-23"),
            "strategy_name": strategy_json.get("strategy_name", "龙虾量化策略"),
            "rules": strategy_json.get("rules") or {},
            "params": strategy_json.get("params") or {},
            "buy_idea": payload.get("buy_idea"),
            "sell_idea": payload.get("sell_idea"),
            "risk_idea": payload.get("risk_idea"),
        }
        code_result = StrategyCodegenSkill().run(payload=code_payload)
        generated_code = code_result.data.get("generated_code", "") if code_result.success else ""
        safety_check = strategy_safety_check(strategy_json, generated_code)
        result = {
            "strategy_name": strategy_json.get("strategy_name", "龙虾量化策略"),
            "strategy_json": strategy_json,
            "generated_code": generated_code,
            "safety_check": safety_check,
            "source": source,
            "provider_configured": bool(self.provider.available),
            "notice": "" if llm_strategy else "模型 API Key 未配置或本次调用失败，当前使用本地规则解析 Agent。",
        }
        self.log("strategy_generate", payload, {"strategy_name": result["strategy_name"], "safety_check": safety_check})
        return result
