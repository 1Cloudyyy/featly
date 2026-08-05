"""Featly Backend — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.routes.bots import router as bots_router
from app.routes.inventory import router as inventory_router
from app.routes.orders import OrderStatus, pending_router, router as orders_router
from app.ws.engine import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Featly Backend starting...")
    yield
    logger.info("Featly Backend shutting down")


app = FastAPI(
    title="Featly Backend",
    version="2.2.0",
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

# WebSocket
app.include_router(ws_router)


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
        "version": "2.2.0",
    }
