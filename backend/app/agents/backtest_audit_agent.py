from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.skills.risk_check_skill import RiskCheckSkill


class BacktestAuditAgent(BaseAgent):
    name = "backtest_audit_agent"
    description = "回测结果审计 Agent"
    permissions = ("RUN_BACKTEST", "GENERATE_ANALYSIS")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("metrics") or {}
        trades = payload.get("trades") or []
        risk = RiskCheckSkill().run(metrics=metrics, trades=trades, bars=payload.get("bars") or [])
        if self.provider.available:
            try:
                result = self.provider.chat_json(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是A股量化回测审计Agent。只返回JSON，字段为summary、strengths、risks、suggestions、score。"
                                "必须中文、专业、基于总收益、年化收益、最大回撤、夏普率、Alpha、Beta、胜率和交易次数分析。"
                                "不要承诺盈利，不要写鸡汤。"
                            ),
                        },
                        {"role": "user", "content": str(payload)},
                    ],
                    temperature=0.15,
                )
                output = {
                    "summary": result.get("summary", ""),
                    "strengths": result.get("strengths", []),
                    "risks": result.get("risks", []),
                    "suggestions": result.get("suggestions", []),
                    "score": result.get("score", 60),
                }
                self.log("backtest_audit", payload, {"score": output["score"]})
                return output
            except Exception:
                pass
        total_return = metrics.get("total_return")
        sharpe = metrics.get("sharpe")
        max_drawdown = metrics.get("max_drawdown")
        trade_count = metrics.get("trade_count") or len(trades)
        summary = (
            f"策略总收益为 {float(total_return or 0) * 100:.2f}%，最大回撤约 {abs(float(max_drawdown or 0)) * 100:.2f}%，"
            f"夏普率为 {float(sharpe or 0):.2f}，交易次数 {trade_count} 次。"
            "当前结论只能说明样本区间内表现，不能证明未来稳定盈利。"
        )
        output = {
            "summary": summary,
            "strengths": ["策略规则结构清晰，已通过白名单表达式约束。"],
            "risks": risk.data.get("risk_items", ["样本不足，仍需扩大股票和时间区间验证。"]),
            "suggestions": ["加入成交量或波动率过滤。", "做多股票样本验证，观察参数是否过拟合。"],
            "score": 63 if total_return and float(total_return) > 0 else 52,
        }
        self.log("backtest_audit", payload, {"score": output["score"]}, status="local")
        return output
