from __future__ import annotations

from typing import Any

from app.api.v1.news import stock_news
from app.skills.base_skill import BaseSkill, SkillResult


class NewsFetchSkill(BaseSkill):
    name = "news_fetch"
    description = "读取当前股票消息面，保留可溯源链接"
    permissions = ("READ_NEWS",)

    def run(self, **kwargs: Any) -> SkillResult:
        payload = stock_news(symbol=kwargs.get("symbol", "000001.XSHE"), limit=int(kwargs.get("limit", 12)))
        return SkillResult(
            True,
            {"items": payload.get("items", []), "source": payload.get("source", "")},
            sources=payload.get("items", []),
        )
