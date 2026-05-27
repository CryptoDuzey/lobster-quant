from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.database import get_connection
from app.orchestration.audit_logger import audit_logger
from app.orchestration.tool_registry import tool_registry


router = APIRouter(prefix="/api/v1/agent-gateway", tags=["agent-gateway"])

SCOPES = {
    "R": "读取行情、策略和回测结果",
    "W": "写入策略或修改配置",
    "B": "运行回测任务",
    "N": "发送通知",
    "C": "读取密钥配置，默认禁止",
    "T": "交易权限，MVP 默认禁用",
}


class TokenRequest(BaseModel):
    name: str = Field(default="本地 Agent Token", min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["R", "B"])


class GatewayRunRequest(BaseModel):
    task_type: str = Field(default="backtest", max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=lambda: ["R"])


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_scopes(scopes: list[str]) -> list[str]:
    cleaned = [scope for scope in scopes if scope in SCOPES and scope not in {"C", "T"}]
    return cleaned or ["R"]


@router.get("/tools")
def gateway_tools() -> dict[str, Any]:
    return {
        "scopes": [{"scope": key, "description": value, "enabled": key not in {"C", "T"}} for key, value in SCOPES.items()],
        "tools": tool_registry.list_tools(),
        "security": {
            "live_trade_enabled": False,
            "paper_only_default": True,
            "sse_job_stream": True,
            "idempotency_key": True,
            "kill_switch_reserved": True,
        },
    }


@router.post("/tokens")
def create_token(payload: TokenRequest) -> dict[str, Any]:
    token = f"lq_{secrets.token_urlsafe(24)}"
    token_id = f"agt_{uuid.uuid4().hex[:12]}"
    scopes = _safe_scopes(payload.scopes)
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_gateway_tokens (id, name, token_hash, scopes, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (token_id, payload.name, _hash_token(token), json.dumps(scopes, ensure_ascii=False), now),
        )
    audit_logger.log(
        agent="agent_gateway",
        action="create_token",
        input_summary={"name": payload.name, "scopes": scopes},
        output_summary={"token_id": token_id},
    )
    return {
        "id": token_id,
        "name": payload.name,
        "token": token,
        "scopes": scopes,
        "created_at": now,
        "note": "Token 只显示一次，请妥善保存。MVP 阶段实盘交易权限默认禁用。",
    }


@router.get("/tokens")
def list_tokens() -> dict[str, Any]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, scopes, is_active, created_at, last_used_at FROM agent_gateway_tokens ORDER BY created_at DESC"
        ).fetchall()
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "scopes": json.loads(row["scopes"] or "[]"),
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "token_preview": "lq_****",
            }
            for row in rows
        ]
    }


@router.post("/run")
def run_gateway_job(payload: GatewayRunRequest, idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
    now = _now()
    task_type = payload.task_type.strip() or "backtest"
    scopes = _safe_scopes(payload.scopes)
    if "T" in payload.scopes:
        result = {"success": False, "message": "MVP 阶段实盘交易权限默认禁用。"}
        status = "blocked"
    elif task_type in {"backtest", "run_backtest"} and "B" in scopes:
        result = {
            "success": True,
            "message": "回测任务已进入队列。当前接口已预留异步任务和 SSE 进度，正式执行仍走 /api/v1/backtest/run。",
            "next_step": "/api/v1/backtest/run",
        }
        status = "queued"
    else:
        result = {
            "success": True,
            "message": "Agent Gateway 已接收任务。当前版本只记录任务、权限和审计，不越权执行。",
        }
        status = "queued"
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with get_connection() as conn:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM agent_gateway_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return _job_from_row(existing)
        conn.execute(
            """
            INSERT INTO agent_gateway_jobs
            (id, task_type, status, payload_json, result_json, error_message, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, '', ?, ?, ?)
            """,
            (
                job_id,
                task_type,
                status,
                json.dumps({"payload": payload.payload, "scopes": scopes}, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                idempotency_key or "",
                now,
                now,
            ),
        )
    audit_logger.log(
        agent="agent_gateway",
        action="run",
        input_summary={"task_type": task_type, "scopes": scopes},
        output_summary={"job_id": job_id, "status": status},
    )
    return {"job_id": job_id, "status": status, "result": result}


def _job_from_row(row: Any) -> dict[str, Any]:
    return {
        "job_id": row["id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "result": json.loads(row["result_json"] or "{}"),
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM agent_gateway_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return {"success": False, "error_code": "JOB_NOT_FOUND", "message": "未找到任务"}
    return _job_from_row(row)


@router.get("/jobs/{job_id}/stream")
def stream_job(job_id: str) -> StreamingResponse:
    def events():
        yield "event: progress\ndata: {\"progress\":10,\"message\":\"任务已接收\"}\n\n"
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM agent_gateway_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            yield "event: error\ndata: {\"message\":\"未找到任务\"}\n\n"
            return
        yield "event: progress\ndata: {\"progress\":60,\"message\":\"正在读取任务快照\"}\n\n"
        yield "event: done\ndata: " + json.dumps(_job_from_row(row), ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/audit-logs")
def gateway_audit_logs(limit: int = 100) -> dict[str, Any]:
    return {"items": audit_logger.tail(max(1, min(limit, 200)))}
