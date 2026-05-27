from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

from app.auth.auth_router import router as auth_router
from app.api.v1.agents import router as agents_router
from app.api.v1.ai import router as ai_router
from app.api.v1.ai_center import router as ai_center_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.community import router as community_router
from app.api.v1.market import router as market_router
from app.api.v1.news import router as news_router
from app.api.v1.strategy import router as strategy_router
from app.agent_gateway.agent_gateway_router import router as agent_gateway_router
from app.data.data_source_router import router as data_source_router
from app.db.database import init_database
from app.settings.settings_router import router as settings_router
from app.strategies.strategy_router import router as strategies_router


def create_app() -> FastAPI:
    init_database()
    app = FastAPI(
        title="AI A-Share Quant Workstation Backend",
        version="0.1.0",
        description="RiceQuant/rqalpha backtest API for A-share strategies.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(market_router)
    app.include_router(news_router)
    app.include_router(data_source_router)
    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(backtest_router)
    app.include_router(ai_router)
    app.include_router(ai_center_router)
    app.include_router(agent_gateway_router)
    app.include_router(agents_router)
    app.include_router(strategy_router)
    app.include_router(strategies_router)
    app.include_router(community_router)
    return app


app = create_app()
