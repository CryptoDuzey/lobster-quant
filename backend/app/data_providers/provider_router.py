from __future__ import annotations

from app.data_providers.akshare_provider import AkshareProvider


provider = AkshareProvider()


def get_market_provider() -> AkshareProvider:
    return provider
