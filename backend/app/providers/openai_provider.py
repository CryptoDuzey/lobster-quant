from __future__ import annotations

from app.providers.llm_provider import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        super().__init__(model="", enabled=False)

    def chat(self, messages, temperature=0.2, response_format=None, timeout=45) -> LLMResponse:
        raise RuntimeError("OpenAI Provider 尚未启用，请先配置密钥和模型。")
