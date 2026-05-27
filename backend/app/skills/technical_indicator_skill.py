from __future__ import annotations

from statistics import mean
from typing import Any

from app.skills.base_skill import BaseSkill, SkillResult


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if result != result:
            return default
        return result
    except Exception:
        return default


class TechnicalIndicatorSkill(BaseSkill):
    name = "technical_indicator"
    description = "计算基础技术指标和短线结构判断"
    permissions = ("READ_MARKET",)

    def run(self, **kwargs: Any) -> SkillResult:
        bars = kwargs.get("bars") or []
        if not bars:
            return SkillResult(False, message="暂无K线数据，无法进行技术分析。")

        closes = [_number(row.get("close")) for row in bars if row.get("close") is not None]
        volumes = [_number(row.get("volume")) for row in bars if row.get("volume") is not None]
        latest = bars[-1]
        close = _number(latest.get("close"))
        ma20 = _number(latest.get("ma20"), mean(closes[-20:]) if closes else 0)
        atr = _number(latest.get("atr"))
        previous = bars[-2] if len(bars) > 1 else latest
        change = close - _number(previous.get("close"), close)
        change_pct = change / _number(previous.get("close"), close or 1) if _number(previous.get("close"), close or 1) else 0
        volume_ma20 = mean(volumes[-20:]) if volumes else 0
        volume_state = "放大" if volumes and volumes[-1] > volume_ma20 * 1.2 else "未明显放大"
        trend = "震荡偏强" if close >= ma20 else "震荡偏弱"
        if abs(change_pct) > 0.03:
            trend = "短线快速上行" if change_pct > 0 else "短线快速下行"
        support = round(ma20 - atr, 3) if atr else round(ma20 * 0.98, 3)
        resistance = round(ma20 + atr, 3) if atr else round(ma20 * 1.02, 3)
        view = (
            f"当前价格位于MA20{'上方' if close >= ma20 else '下方'}，技术结构为{trend}。"
            f"成交量{volume_state}，短线支撑约 {support}，压力约 {resistance}。"
        )
        return SkillResult(
            True,
            {
                "technical_view": view,
                "trend_state": trend,
                "support": support,
                "resistance": resistance,
                "change_pct": round(change_pct, 4),
                "volume_state": volume_state,
            },
        )
