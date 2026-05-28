from __future__ import annotations

from typing import Any

from app.skills.base_skill import BaseSkill, SkillResult


class BacktestSkill(BaseSkill):
    name = "backtest"
    description = "运行 rqalpha 回测任务；当前只允许回测和纸面验证，不允许实盘交易"
    permissions = ("RUN_BACKTEST",)

    def run(self, **kwargs: Any) -> SkillResult:
        return SkillResult(False, message="请通过 /api/v1/backtest/run 调用主回测引擎。本 Skill 仅用于工具注册和权限声明。")
