from __future__ import annotations

from typing import Any

from app.skills.base_skill import BaseSkill, SkillResult


POSITIVE_WORDS = ("增长", "突破", "增持", "净流入", "中标", "回购", "盈利", "上调", "利好")
NEGATIVE_WORDS = ("下滑", "减持", "亏损", "处罚", "调查", "净流出", "下调", "风险", "利空")


class SentimentSkill(BaseSkill):
    name = "news_sentiment"
    description = "对消息标题和摘要做轻量情绪分类"
    permissions = ("READ_NEWS",)

    def run(self, **kwargs: Any) -> SkillResult:
        news = kwargs.get("news") or []
        if not news:
            return SkillResult(True, {"sentiment": "中性", "score": 0.0, "reason": "暂无可用消息。"})
        score = 0
        hits: list[str] = []
        for item in news[:12]:
            text = f"{item.get('title', '')} {item.get('summary', '')}"
            for word in POSITIVE_WORDS:
                if word in text:
                    score += 1
                    hits.append(word)
            for word in NEGATIVE_WORDS:
                if word in text:
                    score -= 1
                    hits.append(word)
        sentiment = "偏利好" if score > 0 else "偏利空" if score < 0 else "中性"
        return SkillResult(
            True,
            {
                "sentiment": sentiment,
                "score": max(-1.0, min(1.0, score / max(len(news[:12]), 1))),
                "reason": f"近期消息关键词显示为{sentiment}。" if hits else "未发现明显方向性关键词。",
            },
            sources=[{"title": item.get("title"), "url": item.get("url"), "source": item.get("source")} for item in news[:8]],
        )
