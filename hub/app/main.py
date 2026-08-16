"""Featly Hub — FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from loguru import logger

from app.config import settings
from app.db import engine
from app.models import Base
from app.routes.bots import router as bots_router
from app.routes.inventory import router as inventory_router
from app.routes.orders import OrderStatus, pending_router, router as orders_router
from app.routes.settings import router as hub_settings_router
from app.routes.stats import router as stats_router
from app.services.monitor import engine_offline_watcher
from app.ws.engine import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Featly Backend starting...")
    # Ensure tables exist on first run (Alembic migrations not yet present)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"WS_SECRET: {settings.ws_secret[:8]}...")
    logger.info(f"API_KEY: {settings.api_key[:8]}...")
    logger.info("Save these! They won't be shown again.")
    # Фоновый мониторинг движков (алерты в TG по настройкам hub)
    monitor_task = asyncio.create_task(engine_offline_watcher())
    try:
        yield
    finally:
        monitor_task.cancel()
        await engine.dispose()
        logger.info("Featly Backend shutting down")


app = FastAPI(
    title="Featly Hub",
    version="3.0.0",
    description="Auto-delivery system for Roblox MM2 items",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(orders_router)
app.include_router(pending_router)
app.include_router(inventory_router)
app.include_router(bots_router)
app.include_router(stats_router)
app.include_router(hub_settings_router)

# WebSocket
app.include_router(ws_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/detailed")
async def health_detailed() -> dict:
    """Detailed health check — verifies DB connection."""
    from sqlalchemy import text

    from app.db import async_session

    db_ok = False
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "version": "3.0.0",
    }
