"""
ORVA API — FastAPI backend for Property Intelligence.
Imports existing Python modules directly (data_processor, building_intelligence, etc.)
"""

import sys
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from .deps import data_store
from .routers import auth, leads, clients, whatsapp, rentals, contacts, matcher, bayut, client_match

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("orva_api")

# Also log to file
_log_dir = _root / "logs"
_log_dir.mkdir(exist_ok=True)
_fh = logging.FileHandler(_log_dir / "api.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s"))
logger.addHandler(_fh)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup."""
    logger.info("Loading lead data...")
    data_store.load()
    logger.info("Loaded %s leads, PF merge: %s", f"{len(data_store.leads_df):,}", data_store.pf_merge_status)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="ORVA API",
    description="Property Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Request logging middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


# CORS — allow Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://65.20.73.212",
        "http://65.20.73.212:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Mount routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(clients.router)
app.include_router(whatsapp.router)
app.include_router(rentals.router)
app.include_router(contacts.router)
app.include_router(matcher.router)
app.include_router(bayut.router)
app.include_router(client_match.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_loaded": data_store.is_loaded,
        "total_leads": len(data_store.leads_df) if data_store.is_loaded else 0,
        "total_buildings": len(data_store.buildings) if data_store.is_loaded else 0,
        "pf_merge_status": data_store.pf_merge_status,
        "client_id_index_size": len(data_store.client_id_index),
        "rentals_loaded": data_store.rentals_df is not None and not data_store.rentals_df.empty,
        "total_rentals": len(data_store.rentals_df) if data_store.rentals_df is not None else 0,
    }
