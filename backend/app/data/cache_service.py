from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.database import get_connection


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MarketCacheService:
    def get_market_bars(
        self,
        symbol: str,
        period: str,
        adjust: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT time, open, high, low, close, volume, amount, source
                FROM market_bar_cache
                WHERE symbol = ? AND period = ? AND adjust = ? AND time BETWEEN ? AND ?
                ORDER BY time ASC
                """,
                (symbol, period, adjust, start_date, end_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_market_bars(
        self,
        symbol: str,
        period: str,
        adjust: str,
        bars: list[dict[str, Any]],
        source: str,
    ) -> None:
        if not bars:
            return
        now = _now()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO market_bar_cache
                (symbol, period, adjust, time, open, high, low, close, volume, amount, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, period, adjust, time) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        symbol,
                        period,
                        adjust,
                        row["time"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row.get("volume"),
                        row.get("amount"),
                        source,
                        now,
                        now,
                    )
                    for row in bars
                ],
            )


class BenchmarkCacheService:
    def get_bars(self, benchmark_symbol: str, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], str]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT time, open, high, low, close, source
                FROM benchmark_bar_cache
                WHERE benchmark_symbol = ? AND time BETWEEN ? AND ?
                ORDER BY time ASC
                """,
                (benchmark_symbol, start_date, end_date),
            ).fetchall()
        items = [dict(row) for row in rows]
        source = items[0]["source"] if items else ""
        return items, source

    def upsert_bars(self, benchmark_symbol: str, bars: list[dict[str, Any]], source: str) -> None:
        if not bars:
            return
        now = _now()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO benchmark_bar_cache
                (benchmark_symbol, time, open, high, low, close, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(benchmark_symbol, time) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        benchmark_symbol,
                        row["time"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        source,
                        now,
                        now,
                    )
                    for row in bars
                ],
            )


class FinancialFactorCacheService:
    def get_factors(self, symbol: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT symbol, report_date, available_date, factor_name, factor_value, source, updated_at
                FROM financial_factor_cache
                WHERE symbol = ?
                ORDER BY available_date ASC, factor_name ASC
                """,
                (symbol,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_factor_asof(self, symbol: str, factor_name: str, as_of_date: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT symbol, report_date, available_date, factor_name, factor_value, source, updated_at
                FROM financial_factor_cache
                WHERE symbol = ? AND factor_name = ? AND available_date <= ?
                ORDER BY available_date DESC
                LIMIT 1
                """,
                (symbol, factor_name, as_of_date),
            ).fetchone()
        return dict(row) if row else None

    def upsert_factors(self, symbol: str, rows: list[dict[str, Any]], source: str) -> None:
        if not rows:
            return
        now = _now()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO financial_factor_cache
                (symbol, report_date, available_date, factor_name, factor_value, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, report_date, factor_name) DO UPDATE SET
                    available_date=excluded.available_date,
                    factor_value=excluded.factor_value,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        symbol,
                        row["report_date"],
                        row["available_date"],
                        row["factor_name"],
                        row.get("factor_value"),
                        source,
                        now,
                        now,
                    )
                    for row in rows
                ],
            )


class MacroFactorCacheService:
    def get_indicator(self, indicator: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT indicator, time, value, source, extra_json, updated_at
                FROM macro_factor_cache
                WHERE indicator = ?
                ORDER BY time ASC
                """,
                (indicator,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_asof(self, indicator: str, as_of_date: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT indicator, time, value, source, extra_json, updated_at
                FROM macro_factor_cache
                WHERE indicator = ? AND time <= ?
                ORDER BY time DESC
                LIMIT 1
                """,
                (indicator, as_of_date),
            ).fetchone()
        return dict(row) if row else None

    def upsert_indicator(self, indicator: str, rows: list[dict[str, Any]], source: str) -> None:
        if not rows:
            return
        now = _now()
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO macro_factor_cache
                (indicator, time, value, source, extra_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator, time) DO UPDATE SET
                    value=excluded.value,
                    source=excluded.source,
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        indicator,
                        row["time"],
                        row.get("value"),
                        source,
                        row.get("extra_json", "{}"),
                        now,
                        now,
                    )
                    for row in rows
                ],
            )
