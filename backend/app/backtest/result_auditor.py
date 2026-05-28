from __future__ import annotations

import math
from typing import Any


class BacktestResultAuditor:
    def audit(self, response: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        blocking_errors: list[str] = []

        data_info = response.get("data_info") or {}
        time_range = response.get("time_range") or {}
        metrics = response.get("metrics") or {}
        trades = response.get("trades") or []
        curves = response.get("curves") or {}
        benchmark = response.get("benchmark") or {}

        if data_info.get("is_mock"):
            blocking_errors.append("本次结果包含演示数据，不能作为正式回测结果。")
        if not response.get("strategy_hash"):
            blocking_errors.append("缺少策略 Hash，无法确认策略是否真实执行。")
        if not response.get("code_hash"):
            blocking_errors.append("缺少代码 Hash，无法确认执行代码快照。")
        if response.get("success") is False:
            blocking_errors.append(response.get("message") or "本次回测未成功完成。")
        if not time_range.get("bars_count"):
            blocking_errors.append("行情数据为空，回测结果不可信。")
        elif int(time_range.get("bars_count") or 0) < 30:
            warnings.append("行情样本少于 30 条，统计意义有限。")
        if (data_info.get("missing_ratio") or 0) > 0.02:
            warnings.append("行情缺失比例偏高，请谨慎解读回测结果。")

        strategy_curve_ok, strategy_reason = _valid_curve(curves.get("strategy_curve") or [])
        if not strategy_curve_ok:
            blocking_errors.append(f"策略曲线无效：{strategy_reason}")

        benchmark_curve = curves.get("benchmark_curve") or []
        benchmark_curve_ok, benchmark_reason = _valid_curve(benchmark_curve)
        if benchmark.get("available") and not benchmark_curve_ok:
            blocking_errors.append(f"基准曲线无效：{benchmark_reason}，禁止展示为真实基准。")
        if not benchmark.get("available") or not benchmark_curve_ok:
            if metrics.get("alpha") is not None or metrics.get("beta") is not None:
                blocking_errors.append("Alpha/Beta 在基准曲线无效时不应返回数值。")
            else:
                warnings.append("缺少有效基准收益序列，Alpha/Beta 暂不可用。")

        if not trades:
            warnings.append("本次回测没有交易，策略触发条件可能过严。")
        elif len(trades) < 3:
            warnings.append("交易次数较少，统计意义有限。")

        required = ["total_return", "annual_return", "max_drawdown", "sharpe", "volatility", "trade_count"]
        missing_metrics = [key for key in required if metrics.get(key) is None]
        if missing_metrics:
            warnings.append(f"部分指标无法计算：{', '.join(missing_metrics)}。")

        for key, value in metrics.items():
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                blocking_errors.append(f"指标 {key} 存在 NaN 或 Inf。")

        max_drawdown = metrics.get("max_drawdown")
        if isinstance(max_drawdown, (int, float)) and max_drawdown < -0.8:
            warnings.append("最大回撤超过 80%，策略风险极高。")

        trust_level = "high"
        if blocking_errors:
            trust_level = "low"
        elif len(warnings) >= 3:
            trust_level = "low"
        elif warnings:
            trust_level = "medium"

        return {
            "trust_level": trust_level,
            "warnings": warnings,
            "blocking_errors": blocking_errors,
        }


def _valid_curve(curve: list[dict[str, Any]]) -> tuple[bool, str]:
    if not isinstance(curve, list) or len(curve) < 2:
        return False, "曲线少于 2 个有效点"
    values: list[float] = []
    for item in curve:
        try:
            value = float(item.get("value"))
        except Exception:
            continue
        if math.isfinite(value):
            values.append(value)
    if len(values) < 2:
        return False, "曲线有效数值少于 2 个"
    if abs(max(values) - min(values)) < 1e-8:
        return False, "检测到收益序列为常数"
    return True, ""
