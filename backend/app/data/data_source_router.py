from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/data-sources", tags=["data-sources"])

DEFAULT_SOURCES = [
    {"source_name": "eastmoney", "display_name": "东方财富", "priority": 10, "status": "可用"},
    {"source_name": "akshare", "display_name": "akshare", "priority": 20, "status": "可用"},
    {"source_name": "cache", "display_name": "本地 SQLite 缓存", "priority": 1, "status": "可用"},
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _seed() -> None:
    now = _now()
    with get_connection() as conn:
        for item in DEFAULT_SOURCES:
            conn.execute(
                """
                INSERT OR IGNORE INTO data_source_configs
                (source_name, display_name, is_enabled, priority, status, updated_at)
                VALUES (?, ?, 1, ?, ?, ?)
                """,
                (item["source_name"], item["display_name"], item["priority"], item["status"], now),
            )


@router.get("")
@router.get("/")
def list_data_sources() -> dict[str, Any]:
    _seed()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM data_source_configs ORDER BY priority ASC, source_name ASC"
        ).fetchall()
        market_count = conn.execute("SELECT COUNT(*) AS count FROM market_bar_cache").fetchone()["count"]
        benchmark_count = conn.execute("SELECT COUNT(*) AS count FROM benchmark_bar_cache").fetchone()["count"]
        financial_count = conn.execute("SELECT COUNT(*) AS count FROM financial_factor_cache").fetchone()["count"]
        macro_count = conn.execute("SELECT COUNT(*) AS count FROM macro_factor_cache").fetchone()["count"]
    return {
        "items": [
            {
                "source_name": row["source_name"],
                "display_name": row["display_name"],
                "is_enabled": bool(row["is_enabled"]),
                "priority": row["priority"],
                "status": row["status"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
        "cache": {
            "market_bar_count": market_count,
            "benchmark_bar_count": benchmark_count,
            "financial_factor_count": financial_count,
            "macro_factor_count": macro_count,
            "storage": "SQLite",
        },
    }


@router.get("/factors/financial/{symbol}")
def financial_factors(symbol: str, as_of: str | None = None) -> dict[str, Any]:
    from app.data.fundamental_macro_service import FINANCIAL_FACTOR_LABELS, FinancialFactorService
    from app.data_providers.akshare_provider import normalize_symbol

    normalized = normalize_symbol(symbol)
    service = FinancialFactorService()
    warnings = service.ensure_symbol(normalized)
    as_of_date = as_of or datetime.now().strftime("%Y-%m-%d")
    factors = {}
    for factor_name, label in FINANCIAL_FACTOR_LABELS.items():
        item = service.get_asof(normalized, factor_name, as_of_date)
        factors[factor_name] = {
            "label": label,
            "value": item.value,
            "source": item.source,
            "report_date": item.report_date,
            "available_date": item.available_date,
            "warning": item.warning,
        }
    return {"symbol": normalized, "as_of": as_of_date, "factors": factors, "warnings": warnings}


@router.get("/factors/macro")
def macro_factors(as_of: str | None = None) -> dict[str, Any]:
    from app.data.fundamental_macro_service import MacroFactorService

    as_of_date = as_of or datetime.now().strftime("%Y-%m-%d")
    context = MacroFactorService().get_context(as_of_date)
    return {
        "as_of": as_of_date,
        "factors": {
            key: {
                "value": item.value,
                "source": item.source,
                "time": item.report_date,
                "warning": item.warning,
            }
            for key, item in context.items()
        },
    }
