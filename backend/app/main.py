import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ]


def _frontend_dist_dir() -> Path:
    configured = os.getenv("LOBSTER_FRONTEND_DIST", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "front" / "dist"


def create_app() -> FastAPI:
    init_database()
    app = FastAPI(
        title="Lobster Quant API",
        version="0.1.0",
        description="龙虾量化 A 股 AI 投研与回测工作站后端。",
    )
    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "lobster-quant"}

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

    dist_dir = _frontend_dist_dir()
    assets_dir = dist_dir / "assets"
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_frontend(full_path: str) -> FileResponse:
            requested = dist_dir / full_path
            if requested.exists() and requested.is_file():
                return FileResponse(requested)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()
