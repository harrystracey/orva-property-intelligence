"""
ORVA API — FastAPI backend for Property Intelligence.
Imports existing Python modules directly (data_processor, building_intelligence, etc.)
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importing _sys_paths puts PROJECT_ROOT and whatsapp_bot/ on sys.path so
# every downstream module can import data_processor, whatsapp_bot, etc.
from . import _sys_paths  # noqa: F401

# Configure root logger once. LOG_LEVEL env override lets ops raise to DEBUG
# in staging or drop to WARNING when stdout is noisy. format keeps a single
# line per record so Docker / journalctl stay tidy.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("orva_api")

from .config import CORS_ORIGINS
from .deps import data_store
from .routers import auth, leads, clients, whatsapp, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup."""
    logger.info("loading lead data")
    data_store.load()
    logger.info("loaded %d leads", len(data_store.leads_df))
    yield
    logger.info("shutting down")


app = FastAPI(
    title="ORVA API",
    description="Property Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS -- origins come from config.CORS_ORIGINS (env var CORS_ORIGINS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(clients.router)
app.include_router(whatsapp.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_loaded": data_store.is_loaded,
        "total_leads": len(data_store.leads_df) if data_store.is_loaded else 0,
        "total_buildings": len(data_store.buildings) if data_store.is_loaded else 0,
    }
