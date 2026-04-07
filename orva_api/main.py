"""
ORVA API — FastAPI backend for Property Intelligence.
Imports existing Python modules directly (data_processor, building_intelligence, etc.)
"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from .deps import data_store
from .routers import auth, leads, clients, whatsapp, reidin, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup."""
    print("[ORVA API] Loading lead data...")
    data_store.load()
    print(f"[ORVA API] Loaded {len(data_store.leads_df):,} leads")
    yield
    print("[ORVA API] Shutting down")


app = FastAPI(
    title="ORVA API",
    description="Property Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

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
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(clients.router)
app.include_router(whatsapp.router)
app.include_router(reidin.router)
app.include_router(chat.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_loaded": data_store.is_loaded,
        "total_leads": len(data_store.leads_df) if data_store.is_loaded else 0,
        "total_buildings": len(data_store.buildings) if data_store.is_loaded else 0,
    }
