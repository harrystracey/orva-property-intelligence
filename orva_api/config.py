"""
ORVA API Configuration
Loads settings from environment variables and defines paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root is one level up from orva-api/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# --- Auth ---
# JWT_SECRET must be explicitly set. The previous hardcoded default
# ("orva-jwt-secret-change-in-production") would silently ship to production
# as a forgeable secret if the env var was missing.
_BANNED_SECRETS = {
    "",
    "orva-jwt-secret-change-in-production",
    "change-in-production",
    "secret",
    "changeme",
}
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if JWT_SECRET in _BANNED_SECRETS or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET env var is missing, too short (<32 chars), or set to a "
        "known placeholder. Generate one with `python -c \"import secrets; "
        "print(secrets.token_urlsafe(48))\"` and set it in .env before "
        "starting the API."
    )
JWT_ALGORITHM = "HS256"
# Default 7 days; override with JWT_EXPIRY_HOURS if a longer-lived token is
# needed (e.g. internal tooling). 30 days was the old default and is a
# compromise on security if a tab/device is ever compromised.
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "168"))

# --- CORS ---
# Comma-separated list of allowed origins. Falls back to localhost for dev.
_default_cors = "http://localhost:3000,http://127.0.0.1:3000"
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", _default_cors).split(",")
    if o.strip()
]

# --- Users ---
# Users may be provided as a JSON file path via USERS_FILE. The fallback
# path is orva_api/users.json. If the file is missing we fall back to the
# legacy hardcoded USERS dict in auth.py for backwards compat with existing
# deployments, but that path is deprecated.
USERS_FILE = Path(os.getenv("USERS_FILE", PROJECT_ROOT / "orva_api" / "users.json"))

# --- API Keys ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- WhatsApp ---
WA_HOST_1 = os.getenv("WA_HOST_1", "localhost")
WA_HOST_2 = os.getenv("WA_HOST_2", "localhost")

# --- Data Paths ---
LEAD_DATABASE_DIR = PROJECT_ROOT / "lead_database"
DATA_DIR = PROJECT_ROOT / "data"
SCRAPED_DATA_DIR = PROJECT_ROOT / "scraped_data"
CLIENT_DATA_DIR = PROJECT_ROOT / "client_data"
CHAT_HISTORY_DIR = PROJECT_ROOT / "chat_history"
REFERENCE_DIR = PROJECT_ROOT / "Master reference datasets"

PARQUET_PATH = LEAD_DATABASE_DIR / "leads_master.parquet"
PF_CSV_PATH = SCRAPED_DATA_DIR / "propertyfinder_scraped_leads.csv"
BAYUT_CSV_PATH = DATA_DIR / "bayut_palm_listings.csv"
UNIT_REGISTRY_PATH = DATA_DIR / "unit_registry.csv"
RENTALS_CSV_PATH = SCRAPED_DATA_DIR / "palm_jumeirah_rentals.csv"

# --- Pagination ---
DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 1000
