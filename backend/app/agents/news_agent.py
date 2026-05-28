from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.skills.sentiment_skill import SentimentSkill


class NewsAgent(BaseAgent):
    name = "news_agent"
    description = "消息面分析师 Agent"
    permissions = ("READ_NEWS",)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        news = payload.get("news") or []
        sentiment = SentimentSkill().run(news=news)
        data = sentiment.data
        count = len(news)
        news_view = f"近期共读取 {count} 条相关消息，消息面整体{data.get('sentiment', '中性')}。{data.get('reason', '')}"
        result = {
            "news_view": news_view,
            "news_sentiment": data.get("sentiment", "中性"),
            "news_score": data.get("score", 0),
            "sources": sentiment.sources,
        }
        self.log("news_view", payload, {"news_count": count, "sentiment": result["news_sentiment"]})
        return result
