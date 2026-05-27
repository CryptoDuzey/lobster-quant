from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.v1.backtest import BacktestRequest, generate_strategy_code


router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


@router.post("/generate-code")
def generate_code(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = BacktestRequest.model_validate(payload)
        code = generate_strategy_code(request)
        return {
            "success": True,
            "strategy_name": request.strategy_name,
            "symbol": request.stock_id,
            "period": request.period,
            "code": code,
            "constraints": [
                "单只股票策略只交易一个 symbol",
                "表达式已做白名单校验",
                "A 股 T+1 与 100 股整手交易约束由策略代码处理",
                "技术指标在策略逻辑层计算，不引用未生成字段",
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"策略代码生成失败：{exc}") from exc
