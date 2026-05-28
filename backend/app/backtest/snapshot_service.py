from __future__ import annotations

from typing import Any

from app.backtest.result_normalizer import stable_hash


class SnapshotService:
    """Build reproducible hashes for deterministic backtest reports."""

    def strategy_code_hash(self, code: str) -> str:
        return stable_hash(code)

    def config_snapshot_hash(self, config: dict[str, Any]) -> str:
        return stable_hash(config)

    def data_hash(self, bars: list[dict[str, Any]]) -> str:
        return stable_hash(bars)

    def build_snapshot(self, *, strategy_code: str, strategy_json: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, str]:
        strategy_hash = self.config_snapshot_hash(strategy_json)
        code_hash = self.strategy_code_hash(strategy_code)
        return {
            "strategy_hash": strategy_hash,
            "code_hash": code_hash,
            "config_hash": strategy_hash,
            "strategy_code_hash": code_hash,
            "config_snapshot_hash": strategy_hash,
            "data_hash": self.data_hash(bars),
        }
