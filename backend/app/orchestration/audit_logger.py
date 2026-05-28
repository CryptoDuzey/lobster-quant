from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.database import get_connection


AUDIT_FILE = Path(__file__).resolve().parents[1] / "data" / "agent_audit_logs.jsonl"


class AuditLogger:
    def __init__(self, path: Path = AUDIT_FILE) -> None:
        self.path = path

    def log(
        self,
        agent: str,
        action: str,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        status: str = "success",
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": uuid.uuid4().hex,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "agent": agent,
            "action": action,
            "status": status,
            "permissions": permissions or [],
            "input_summary": input_summary or {},
            "output_summary": output_summary or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_audit_logs (
                        id TEXT PRIMARY KEY,
                        time TEXT NOT NULL,
                        agent TEXT NOT NULL,
                        action TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'success',
                        permissions TEXT NOT NULL DEFAULT '[]',
                        input_summary TEXT NOT NULL DEFAULT '{}',
                        output_summary TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_audit_logs
                    (id, time, agent, action, status, permissions, input_summary, output_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["id"],
                        event["time"],
                        event["agent"],
                        event["action"],
                        event["status"],
                        json.dumps(event["permissions"], ensure_ascii=False),
                        json.dumps(event["input_summary"], ensure_ascii=False),
                        json.dumps(event["output_summary"], ensure_ascii=False),
                    ),
                )
        except Exception:
            pass
        return event

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM agent_audit_logs ORDER BY time DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            if rows:
                formatted = []
                for row in reversed(rows):
                    item = dict(row)
                    item["permissions"] = json.loads(item.get("permissions") or "[]")
                    item["input_summary"] = json.loads(item.get("input_summary") or "{}")
                    item["output_summary"] = json.loads(item.get("output_summary") or "{}")
                    formatted.append(item)
                return formatted
        except Exception:
            pass
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        fallback_rows = []
        for line in lines:
            try:
                fallback_rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return fallback_rows


audit_logger = AuditLogger()
