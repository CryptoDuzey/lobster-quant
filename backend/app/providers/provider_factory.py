from __future__ import annotations

import os

from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.kimi_provider import KimiProvider
from app.providers.local_llm_provider import LocalLLMProvider
from app.providers.llm_provider import LLMProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.qwen_provider import QwenProvider


def get_llm_provider(name: str | None = None) -> LLMProvider:
    provider_name = (name or os.getenv("LOBSTER_DEFAULT_LLM_PROVIDER", "deepseek")).strip().lower()
    providers = {
        "deepseek": DeepSeekProvider,
        "openai": OpenAIProvider,
        "qwen": QwenProvider,
        "kimi": KimiProvider,
        "local": LocalLLMProvider,
        "local_llm": LocalLLMProvider,
    }
    provider_cls = providers.get(provider_name, DeepSeekProvider)
    return provider_cls()


def list_llm_providers() -> list[dict[str, object]]:
    providers = [DeepSeekProvider(), OpenAIProvider(), QwenProvider(), KimiProvider(), LocalLLMProvider()]
    return [
        {
            "name": provider.name,
            "model": provider.model,
            "enabled": provider.available,
        }
        for provider in providers
    ]
