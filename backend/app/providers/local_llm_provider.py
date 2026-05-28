from __future__ import annotations

from app.providers.llm_provider import LLMProvider, LLMResponse


class LocalLLMProvider(LLMProvider):
    name = "local"

    def __init__(self) -> None:
        super().__init__(model="local-llm", enabled=False)

    def chat(self, messages, temperature=0.2, response_format=None, timeout=45) -> LLMResponse:
        raise RuntimeError("本地模型 Provider 尚未启用。")
