from __future__ import annotations


def planned_agent_steps(task_type: str) -> list[str]:
    if task_type == "market_watch":
        return ["技术面分析", "消息面摘要", "风险检查", "多空观点汇总", "综合结论"]
    if task_type == "strategy_generate":
        return ["自然语言结构化", "安全校验", "rqalpha代码生成", "审计日志写入"]
    if task_type == "strategy_debug":
        return ["读取错误", "定位原因", "生成修复建议", "保留原始代码兜底"]
    return ["任务已接收", "等待执行"]
