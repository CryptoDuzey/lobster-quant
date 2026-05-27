from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.backtest.backtest_validator import json_safe


def stable_hash(payload: Any, prefix: str = "sha256") -> str:
    normalized = json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def make_backtest_id(symbol: str, run_at: str | None = None) -> str:
    timestamp = run_at or datetime.now().strftime("%Y%m%d_%H%M%S")
    compact_symbol = symbol.split(".")[0]
    return f"bt_{timestamp}_{compact_symbol}"


def safe_json_response(payload: dict[str, Any]) -> dict[str, Any]:
    return json_safe(payload)
