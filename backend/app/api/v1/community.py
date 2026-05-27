from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/v1/community", tags=["community"])

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "community_strategies.json"


SEED_STRATEGIES = [
    {
        "id": "community_ma20_volume",
        "name": "MA20 成交量突破策略",
        "author": "龙虾研究员",
        "category": "趋势策略",
        "period": "日线",
        "symbol": "000001.XSHE",
        "name_cn": "平安银行",
        "total_return": 0.016,
        "annual_return": 0.042,
        "max_drawdown": 0.1611,
        "sharpe": -0.06,
        "risk_level": "中",
        "created_at": "2026-05-23 14:08:48",
        "favorites": 18,
        "forks": 7,
        "description": "以 MA20 趋势突破和成交量确认作为入场条件，适合趋势行情验证。",
        "rules": {
            "buy_rules": [{"description": "收盘价站上 MA20", "expression": "close > ma20"}],
            "sell_rules": [{"description": "收盘价跌破 MA20", "expression": "close < ma20"}],
            "risk_rules": [{"description": "持仓回撤超过 8% 止损", "expression": "drawdown > 0.08"}],
        },
    },
    {
        "id": "community_rsi_reversal",
        "name": "RSI 超跌反转观察策略",
        "author": "海岸线量化",
        "category": "均值回归",
        "period": "日线",
        "symbol": "600036.XSHG",
        "name_cn": "招商银行",
        "total_return": -0.012,
        "annual_return": -0.018,
        "max_drawdown": 0.092,
        "sharpe": 0.18,
        "risk_level": "中高",
        "created_at": "2026-05-22 19:30:00",
        "favorites": 12,
        "forks": 4,
        "description": "用于观察金融股超跌后的反弹结构，强调风控与仓位约束。",
        "rules": {
            "buy_rules": [{"description": "价格回到 MA20 上方", "expression": "close > ma20"}],
            "sell_rules": [{"description": "趋势再次转弱", "expression": "close < ma20"}],
            "risk_rules": [{"description": "回撤超过 6% 止损", "expression": "drawdown > 0.06"}],
        },
    },
]


def _read() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return [item.copy() for item in SEED_STRATEGIES]
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [item.copy() for item in SEED_STRATEGIES]


def _write(items: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    return {"items": _read()}


@router.post("/strategies")
def publish_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    items = _read()
    strategy = {
        **payload,
        "id": payload.get("id") or f"community_{uuid.uuid4().hex[:10]}",
        "author": payload.get("author") or "本地用户",
        "category": payload.get("category") or "用户发布",
        "risk_level": payload.get("risk_level") or "待评估",
        "created_at": payload.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "favorites": int(payload.get("favorites") or 0),
        "forks": int(payload.get("forks") or 0),
    }
    items.insert(0, strategy)
    _write(items[:200])
    return strategy


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str) -> dict[str, Any]:
    for item in _read():
        if item.get("id") == strategy_id:
            return item
    raise HTTPException(status_code=404, detail="未找到策略")


@router.post("/strategies/{strategy_id}/fork")
def fork_strategy(strategy_id: str) -> dict[str, Any]:
    items = _read()
    for item in items:
        if item.get("id") == strategy_id:
            item["forks"] = int(item.get("forks") or 0) + 1
            _write(items)
            return {"success": True, "forks": item["forks"], "strategy": item}
    raise HTTPException(status_code=404, detail="未找到策略")


@router.post("/strategies/{strategy_id}/favorite")
def favorite_strategy(strategy_id: str) -> dict[str, Any]:
    items = _read()
    for item in items:
        if item.get("id") == strategy_id:
            item["favorites"] = int(item.get("favorites") or 0) + 1
            _write(items)
            return {"success": True, "favorites": item["favorites"], "strategy": item}
    raise HTTPException(status_code=404, detail="未找到策略")
