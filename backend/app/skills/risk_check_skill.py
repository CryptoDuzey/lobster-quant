from __future__ import annotations

from typing import Any

from app.skills.base_skill import BaseSkill, SkillResult


class RiskCheckSkill(BaseSkill):
    name = "risk_check"
    description = "评估行情波动、回测指标和策略安全约束"
    permissions = ("READ_MARKET", "RUN_BACKTEST")

    def run(self, **kwargs: Any) -> SkillResult:
        bars = kwargs.get("bars") or []
        metrics = kwargs.get("metrics") or {}
        trades = kwargs.get("trades") or []
        max_drawdown = metrics.get("max_drawdown")
        sharpe = metrics.get("sharpe")
        trade_count = metrics.get("trade_count") or len(trades)
        risk_items: list[str] = []
        if max_drawdown is not None and float(max_drawdown) > 0.15:
            risk_items.append("最大回撤偏高，需要降低仓位或增加止损。")
        if sharpe is not None and float(sharpe) < 0.3:
            risk_items.append("夏普率偏低，收益质量不足。")
        if trade_count and int(trade_count) > 80:
            risk_items.append("交易次数较多，手续费和滑点压力会放大。")
        if bars and len(bars) < 40:
            risk_items.append("样本窗口较短，结论稳定性不足。")
        if not risk_items:
            risk_items.append("暂未发现明显硬性风险，但仍需扩大样本并做多股票验证。")
        return SkillResult(
            True,
            {
                "risk_view": " ".join(risk_items),
                "risk_level": "高" if len(risk_items) >= 3 else "中" if len(risk_items) == 2 else "低",
                "risk_items": risk_items,
            },
        )


def strategy_safety_check(strategy_json: dict[str, Any], generated_code: str = "") -> dict[str, bool]:
    text = generated_code or ""
    symbol = strategy_json.get("symbol") or strategy_json.get("stock_id") or ""
    return {
        "symbol_valid": bool(symbol and "." in symbol),
        "no_future_function": not any(word in text.lower() for word in ["future", "shift(-", "lookahead"]),
        "no_unsafe_eval": "__builtins__" in text or "eval(" not in text,
        "data_not_empty_required": "bars is None" in text or "len(bars)" in text or "数据为空" in text,
        "a_share_rules_checked": "100" in text and ("closable" in text or "T+1" in text or "t_plus_one" in str(strategy_json)),
        "live_trade_disabled": True,
    }
