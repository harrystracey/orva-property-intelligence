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
JWT_SECRET = os.getenv("JWT_SECRET", "orva-jwt-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 30  # 30 days

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
