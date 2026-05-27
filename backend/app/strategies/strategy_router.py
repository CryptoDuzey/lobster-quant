from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.security import decode_access_token
from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


OFFICIAL_STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "official_ma_cross",
        "name": "5日/20日均线交叉策略",
        "author": "龙虾量化官方",
        "category": "趋势跟随",
        "period": "日线",
        "symbol": "000001.XSHE",
        "name_cn": "平安银行",
        "description": "用短均线上穿长均线作为趋势启动信号，适合先做单股趋势验证。",
        "risk_level": "中",
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "views": 126,
        "favorites": 18,
        "forks": 7,
        "rules": {
            "buy_rules": [{"description": "MA5 上穿 MA20", "expression": "ma5 > ma20"}],
            "sell_rules": [{"description": "MA5 下穿 MA20", "expression": "ma5 < ma20"}],
            "risk_rules": [{"description": "最大亏损超过 8% 止损", "expression": "loss_from_entry > 0.08"}],
        },
    },
    {
        "id": "official_turtle_atr",
        "name": "海龟 ATR 趋势突破策略",
        "author": "龙虾量化官方",
        "category": "波动突破",
        "period": "日线",
        "symbol": "601318.XSHG",
        "name_cn": "中国平安",
        "description": "用区间高点突破和 ATR 风险尺度管理入场与止损，强调趋势确认。",
        "risk_level": "中高",
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "views": 98,
        "favorites": 11,
        "forks": 5,
        "rules": {
            "buy_rules": [{"description": "收盘价突破 20 日高点", "expression": "close > high_20"}],
            "sell_rules": [{"description": "收盘价跌破 10 日低点", "expression": "close < low_10"}],
            "risk_rules": [{"description": "跌破 2 倍 ATR 风控线", "expression": "close < entry_price - 2 * atr"}],
        },
    },
    {
        "id": "official_boll_mean_revert",
        "name": "布林带均值回归策略",
        "author": "龙虾量化官方",
        "category": "均值回归",
        "period": "日线",
        "symbol": "600036.XSHG",
        "name_cn": "招商银行",
        "description": "观察价格触及布林下轨后的回归机会，适合震荡市场研究。",
        "risk_level": "中",
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "views": 87,
        "favorites": 9,
        "forks": 3,
        "rules": {
            "buy_rules": [{"description": "收盘价低于布林下轨后回升", "expression": "close > boll_lower and prev_close < boll_lower"}],
            "sell_rules": [{"description": "收盘价触及布林中轨", "expression": "close >= boll_mid"}],
            "risk_rules": [{"description": "亏损超过 6% 止损", "expression": "loss_from_entry > 0.06"}],
        },
    },
    {
        "id": "official_rsi_cci_vote",
        "name": "RSI + CCI + 均线三票制策略",
        "author": "龙虾量化官方",
        "category": "多因子",
        "period": "日线",
        "symbol": "000001.XSHE",
        "name_cn": "平安银行",
        "description": "用动量、超买超卖和趋势三类信号投票，适合做多条件组合实验。",
        "risk_level": "中高",
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": None,
        "views": 143,
        "favorites": 22,
        "forks": 8,
        "rules": {
            "buy_rules": [{"description": "至少两类信号转强", "expression": "signal_votes >= 2"}],
            "sell_rules": [{"description": "趋势票和动量票同时转弱", "expression": "trend_vote < 1 and momentum_vote < 1"}],
            "risk_rules": [{"description": "持仓回撤超过 8% 止损", "expression": "drawdown > 0.08"}],
        },
    },
]


class StrategyPayload(BaseModel):
    id: str | None = None
    name: str = Field(default="未命名策略", min_length=1, max_length=120)
    author: str | None = None
    category: str | None = None
    period: str | None = None
    symbol: str | None = None
    name_cn: str | None = None
    description: str | None = None
    risk_level: str | None = None
    total_return: float | None = None
    annual_return: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    rules: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class CommentPayload(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _optional_user(authorization: str | None) -> tuple[int, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return 0, "本地用户"
    payload = decode_access_token(authorization.split(" ", 1)[1].strip())
    if not payload:
        return 0, "本地用户"
    return int(payload.get("sub") or 0), str(payload.get("username") or "本地用户")


def _serialize_strategy(strategy: dict[str, Any]) -> str:
    return json.dumps(strategy, ensure_ascii=False, separators=(",", ":"))


def _row_to_strategy(row: Any) -> dict[str, Any]:
    payload = json.loads(row["payload_json"] or "{}")
    payload.update(
        {
            "id": row["id"],
            "name": row["name"],
            "author": row["author"],
            "category": row["category"],
            "period": row["period"],
            "symbol": row["symbol"],
            "total_return": row["total_return"],
            "annual_return": row["annual_return"],
            "max_drawdown": row["max_drawdown"],
            "sharpe": row["sharpe"],
            "risk_level": row["risk_level"],
            "views": row["views"],
            "favorites": row["favorites"],
            "forks": row["forks"],
            "comments_count": row["comments_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    return payload


def _seed_if_needed() -> None:
    now = _now()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM strategies").fetchone()["count"]
        if count:
            return
        for item in OFFICIAL_STRATEGIES:
            payload = dict(item)
            conn.execute(
                """
                INSERT OR IGNORE INTO strategies
                (id, user_id, name, author, category, period, symbol, payload_json,
                 total_return, annual_return, max_drawdown, sharpe, risk_level,
                 views, favorites, forks, comments_count, created_at, updated_at)
                VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    item["id"],
                    item["name"],
                    item["author"],
                    item["category"],
                    item["period"],
                    item["symbol"],
                    _serialize_strategy(payload),
                    item.get("total_return"),
                    item.get("annual_return"),
                    item.get("max_drawdown"),
                    item.get("sharpe"),
                    item.get("risk_level") or "待评估",
                    int(item.get("views") or 0),
                    int(item.get("favorites") or 0),
                    int(item.get("forks") or 0),
                    now,
                    now,
                ),
            )


@router.get("")
@router.get("/")
def list_strategies(
    keyword: str | None = Query(default=None),
    category: str | None = Query(default=None),
    sort: str = Query(default="latest"),
) -> dict[str, Any]:
    _seed_if_needed()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM strategies").fetchall()
    items = [_row_to_strategy(row) for row in rows]
    if keyword:
        key = keyword.strip().lower()
        items = [
            item
            for item in items
            if key in str(item.get("name", "")).lower()
            or key in str(item.get("description", "")).lower()
            or key in str(item.get("symbol", "")).lower()
            or key in str(item.get("category", "")).lower()
        ]
    if category and category not in {"全部", "全部策略"}:
        items = [item for item in items if category in str(item.get("category", ""))]

    sort_map = {
        "累计收益": ("total_return", True),
        "年化收益": ("annual_return", True),
        "最大回撤": ("max_drawdown", False),
        "夏普率": ("sharpe", True),
        "热度": ("favorites", True),
        "浏览量": ("views", True),
        "收藏数": ("favorites", True),
        "发布时间": ("created_at", True),
        "latest": ("created_at", True),
    }
    field, reverse = sort_map.get(sort, sort_map["latest"])
    items.sort(key=lambda item: (item.get(field) is not None, item.get(field)), reverse=reverse)
    return {"items": items, "total": len(items)}


@router.post("")
@router.post("/")
def publish_strategy(payload: StrategyPayload, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id, username = _optional_user(authorization)
    now = _now()
    data = payload.model_dump()
    strategy_id = data.get("id") or f"strategy_{uuid.uuid4().hex[:12]}"
    data.update(
        {
            "id": strategy_id,
            "author": data.get("author") or username,
            "category": data.get("category") or "用户发布",
            "period": data.get("period") or "日线",
            "symbol": data.get("symbol") or "",
            "risk_level": data.get("risk_level") or "待评估",
            "created_at": now,
            "updated_at": now,
            "views": 0,
            "favorites": 0,
            "forks": 0,
            "comments_count": 0,
        }
    )
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO strategies
            (id, user_id, name, author, category, period, symbol, payload_json,
             total_return, annual_return, max_drawdown, sharpe, risk_level,
             views, favorites, forks, comments_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?)
            """,
            (
                strategy_id,
                user_id,
                data["name"],
                data["author"],
                data["category"],
                data["period"],
                data["symbol"],
                _serialize_strategy(data),
                data.get("total_return"),
                data.get("annual_return"),
                data.get("max_drawdown"),
                data.get("sharpe"),
                data["risk_level"],
                now,
                now,
            ),
        )
    return data


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str) -> dict[str, Any]:
    _seed_if_needed()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="未找到策略")
        conn.execute("UPDATE strategies SET views = views + 1 WHERE id = ?", (strategy_id,))
    item = _row_to_strategy(row)
    item["views"] = int(item.get("views") or 0) + 1
    return item


@router.post("/{strategy_id}/favorite")
def favorite_strategy(strategy_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="未找到策略")
        conn.execute("UPDATE strategies SET favorites = favorites + 1, updated_at = ? WHERE id = ?", (_now(), strategy_id))
        updated = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return {"success": True, "strategy": _row_to_strategy(updated), "favorites": updated["favorites"]}


@router.post("/{strategy_id}/fork")
def fork_strategy(strategy_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="未找到策略")
        conn.execute("UPDATE strategies SET forks = forks + 1, updated_at = ? WHERE id = ?", (_now(), strategy_id))
        updated = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return {"success": True, "strategy": _row_to_strategy(updated), "forks": updated["forks"]}


@router.get("/{strategy_id}/comments")
def list_comments(strategy_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="未找到策略")
        rows = conn.execute(
            "SELECT * FROM strategy_comments WHERE strategy_id = ? ORDER BY created_at DESC",
            (strategy_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("/{strategy_id}/comments")
def add_comment(strategy_id: str, payload: CommentPayload, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id, username = _optional_user(authorization)
    now = _now()
    comment = {
        "id": f"comment_{uuid.uuid4().hex[:12]}",
        "strategy_id": strategy_id,
        "user_id": user_id,
        "username": username,
        "content": payload.content.strip(),
        "created_at": now,
    }
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="未找到策略")
        conn.execute(
            """
            INSERT INTO strategy_comments (id, strategy_id, user_id, username, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (comment["id"], strategy_id, user_id, username, comment["content"], now),
        )
        conn.execute(
            "UPDATE strategies SET comments_count = comments_count + 1, updated_at = ? WHERE id = ?",
            (now, strategy_id),
        )
    return {"success": True, "comment": comment}
