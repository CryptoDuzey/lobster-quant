from __future__ import annotations

from typing import Any

from app.api.v1.backtest import BacktestRequest, generate_strategy_code
from app.skills.base_skill import BaseSkill, SkillResult


class StrategyCodegenSkill(BaseSkill):
    name = "strategy_codegen"
    description = "将结构化策略 JSON 转成 rqalpha 策略代码"
    permissions = ("GENERATE_STRATEGY",)

    def run(self, **kwargs: Any) -> SkillResult:
        payload = kwargs.get("payload") or kwargs
        request = BacktestRequest.model_validate(payload)
        code = generate_strategy_code(request)
        return SkillResult(
            True,
            {
                "strategy_name": request.strategy_name,
                "symbol": request.stock_id,
                "period": request.period,
                "generated_code": code,
            },
        )
