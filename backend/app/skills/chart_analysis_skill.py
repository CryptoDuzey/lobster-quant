from __future__ import annotations

from app.skills.base_skill import BaseSkill, SkillResult


class ChartAnalysisSkill(BaseSkill):
    name = "chart_analysis"
    description = "预留图表选区分析能力，后续可接入视觉或区间K线分析"
    permissions = ("READ_MARKET",)

    def run(self, **kwargs) -> SkillResult:
        selected_range = kwargs.get("selected_range") or {}
        return SkillResult(True, {"selected_range": selected_range, "message": "图表选区分析接口已预留。"})
