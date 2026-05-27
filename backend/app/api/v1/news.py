from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.data_providers.akshare_provider import ak_code, normalize_symbol, no_proxy_env


router = APIRouter(prefix="/api/v1/news", tags=["news"])


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.strip()


def _normalize_stock_news(rows: Any, symbol: str) -> list[dict[str, Any]]:
    if rows is None or getattr(rows, "empty", True):
        return []
    items: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        title = _safe_text(row.get("新闻标题") or row.get("title") or row.get("summary"))
        if not title:
            continue
        url = _safe_text(row.get("新闻链接") or row.get("url"))
        items.append(
            {
                "title": title,
                "source": _safe_text(row.get("文章来源") or row.get("source") or "东方财富"),
                "time": _safe_text(row.get("发布时间") or row.get("time") or ""),
                "url": url if url.startswith(("http://", "https://")) else "",
                "summary": _safe_text(row.get("新闻内容") or row.get("summary") or title),
                "related_symbols": [symbol],
            }
        )
    return items


@router.get("/stock")
def stock_news(symbol: str = Query("000001.XSHE"), limit: int = Query(12, ge=1, le=30)) -> dict[str, Any]:
    started = time.perf_counter()
    normalized = normalize_symbol(symbol)
    try:
        import akshare as ak

        with no_proxy_env():
            rows = ak.stock_news_em(symbol=ak_code(normalized))
        items = _normalize_stock_news(rows, normalized)[:limit]
        return {
            "symbol": normalized,
            "items": items,
            "source": "东方财富",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"消息面接口暂时不可用：{exc}") from exc


@router.get("/market")
def market_news(keyword: str = Query(""), limit: int = Query(12, ge=1, le=30)) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import akshare as ak

        with no_proxy_env():
            rows = ak.stock_news_main_cx()
        items: list[dict[str, Any]] = []
        if rows is not None and not rows.empty:
            for _, row in rows.iterrows():
                title = _safe_text(row.get("summary") or row.get("新闻标题") or row.get("title"))
                if keyword and keyword not in title:
                    continue
                url = _safe_text(row.get("url") or row.get("新闻链接"))
                items.append(
                    {
                        "title": title,
                        "source": _safe_text(row.get("tag") or "财新"),
                        "time": "",
                        "url": url if url.startswith(("http://", "https://")) else "",
                        "summary": title,
                        "related_symbols": [],
                    }
                )
                if len(items) >= limit:
                    break
        return {
            "keyword": keyword,
            "items": items,
            "source": "财新",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"市场快讯接口暂时不可用：{exc}") from exc
