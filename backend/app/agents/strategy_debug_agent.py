from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent


class StrategyDebugAgent(BaseAgent):
    name = "strategy_debug_agent"
    description = "策略代码 Debug Agent"
    permissions = ("DEBUG_STRATEGY", "GENERATE_STRATEGY")

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        generated_code = payload.get("generated_code", "")
        error_message = payload.get("error_message", "")
        if self.provider.available:
            try:
                result = self.provider.chat_json(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是龙虾量化的rqalpha策略Debug Agent。只返回JSON，字段为diagnosis、fixed_code、fix_summary。"
                                "不得生成系统命令，不得越权交易，修复重点是空数据、指标缺失、NaN/Inf、股票代码格式和A股交易约束。"
                            ),
                        },
                        {"role": "user", "content": str(payload)},
                    ],
                    temperature=0.1,
                )
                output = {
                    "diagnosis": result.get("diagnosis", ""),
                    "fixed_code": result.get("fixed_code", generated_code),
                    "fix_summary": result.get("fix_summary", ""),
                    "source": self.provider.name,
                }
                self.log("strategy_debug", payload, {"source": output["source"]})
                return output
            except Exception as exc:
                output = {
                    "diagnosis": f"模型修复失败：{exc}",
                    "fixed_code": generated_code,
                    "fix_summary": "已保留原始代码，请检查模型配置或手动修复。",
                    "source": "本地兜底",
                }
                self.log("strategy_debug", payload, {"source": output["source"]}, status="warning")
                return output
        output = {
            "diagnosis": f"当前未启用模型。错误信息：{error_message or '未提供'}",
            "fixed_code": generated_code,
            "fix_summary": "已记录错误，未进行自动改写。请配置模型 Provider 后再启用自动 Debug。",
            "source": "本地兜底",
        }
        self.log("strategy_debug", payload, {"source": output["source"]}, status="warning")
        return output
