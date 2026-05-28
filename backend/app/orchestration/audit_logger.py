from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


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
        return event

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


audit_logger = AuditLogger()
