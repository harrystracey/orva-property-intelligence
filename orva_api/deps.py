"""
Dependency injection for ORVA API.
Cached data loading — mirrors app.py load_data() logic.
"""

import sys
import logging
import pandas as pd
from pathlib import Path
from functools import lru_cache

from .config import PROJECT_ROOT, PARQUET_PATH, PF_CSV_PATH

logger = logging.getLogger("orva_api")

# Add project root to sys.path so we can import existing modules
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_processor import load_reference_data  # noqa: E402

_PARQUET_TO_APP_COLS = {
    "Owner Name": "owner_name",
    "Phone": "phone",
    "Phone Display": "phone_display",
    "Phone Alt": "phone_alt",
    "Email": "email",
    "Email Alt": "email_alt",
    "Building Name": "building_name",
    "Unit Number": "unit_number",
    "Bedrooms": "bedrooms",
    "Size (sqft)": "size_sqft",
    "Floor": "floor",
    "Nationality": "nationality",
    "Date": "date",
    "Transaction Value": "transaction_value",
    "Project": "project",
    "Source File": "source_file",
    "Import Date": "import_date",
}

_DEFAULT_COLS = [
    ("size_sqm", pd.NA), ("size_method", ""), ("size_confidence", ""),
    ("bedroom_method", ""), ("bedroom_confidence", ""),
    ("listing_price", pd.NA), ("listing_type", ""), ("listing_url", ""),
    ("furnished", ""), ("pf_listing_count", 0), ("source", "crm"),
    ("completeness", 0), ("data_quality", ""),
]


def _load_leads_df() -> pd.DataFrame:
    """Load leads from parquet (fast path). Mirrors app.py load_data()."""
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(f"Parquet not found: {PARQUET_PATH}")

    df = pd.read_parquet(PARQUET_PATH)
    df.rename(columns=_PARQUET_TO_APP_COLS, inplace=True)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "bedrooms" in df.columns:
        df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce")
    if "size_sqft" in df.columns:
        df["size_sqft"] = pd.to_numeric(df["size_sqft"], errors="coerce")

    for col, default in _DEFAULT_COLS:
        if col not in df.columns:
            df[col] = default

    if (df["completeness"] == 0).all():
        has_phone = df["phone"].fillna("").astype(str).str.strip().ne("")
        has_name = df["owner_name"].fillna("").astype(str).str.strip().ne("")
        has_unit = df["unit_number"].fillna("").astype(str).str.strip().ne("")
        has_beds = df["bedrooms"].notna()
        has_size = df["size_sqft"].notna()
        df["completeness"] = (
            has_phone.astype(int) * 30
            + has_name.astype(int) * 25
            + has_unit.astype(int) * 20
            + has_beds.astype(int) * 15
            + has_size.astype(int) * 10
        )

    # Merge PF scraped data
    pf_status = "not_found"
    if PF_CSV_PATH.exists():
        try:
            pf = pd.read_csv(PF_CSV_PATH, encoding="utf-8", low_memory=False, on_bad_lines="skip")
            if not pf.empty and "owner_name" in pf.columns:
                pf["source"] = "propertyfinder"
                for c in df.columns:
                    if c not in pf.columns:
                        pf[c] = pd.NA
                pf = pf[[c for c in df.columns if c in pf.columns]]
                df = pd.concat([df, pf], ignore_index=True)
                pf_status = "ok"
            else:
                pf_status = "empty"
        except Exception:
            logger.exception("Failed to merge PropertyFinder CSV from %s", PF_CSV_PATH)
            pf_status = "failed"

    return df, pf_status


class DataStore:
    """Singleton data store. Loaded once at startup, refreshable."""

    def __init__(self):
        self.leads_df: pd.DataFrame = pd.DataFrame()
        self.ref_df: pd.DataFrame = pd.DataFrame()
        self.ref_stats: dict = {}
        self.rentals_df: pd.DataFrame | None = None
        self.client_id_index: dict[str, int] = {}
        self.pf_merge_status: str = "not_loaded"
        self._buildings_cache: list[str] = []
        self._loaded = False

    def _load_rentals(self):
        """Load rental data from CSV."""
        try:
            from rental_processor import load_rental_data  # noqa: E402
            from .config import RENTALS_CSV_PATH
            if RENTALS_CSV_PATH.exists():
                self.rentals_df = load_rental_data()
                logger.info("Loaded %d rental records", len(self.rentals_df))
            else:
                logger.warning("Rentals CSV not found: %s", RENTALS_CSV_PATH)
                self.rentals_df = pd.DataFrame()
        except Exception:
            logger.exception("Failed to load rental data")
            self.rentals_df = pd.DataFrame()

    def load(self):
        from client_data_manager import make_client_id  # noqa: E402

        self.leads_df, self.pf_merge_status = _load_leads_df()
        self.ref_df, self.ref_stats = load_reference_data()

        # Pre-compute client_id → row index for O(1) lookups
        self.client_id_index = {}
        for idx, row in self.leads_df.iterrows():
            cid = make_client_id(
                name=row.get("owner_name"),
                building=row.get("building_name"),
                unit=row.get("unit_number"),
            )
            if cid not in self.client_id_index:
                self.client_id_index[cid] = idx
        logger.info("Built client_id index: %d entries", len(self.client_id_index))

        # Cache buildings list
        if not self.leads_df.empty:
            self._buildings_cache = sorted(
                self.leads_df["building_name"]
                .dropna()
                .str.strip()
                .loc[lambda s: s.ne("")]
                .unique()
                .tolist()
            )
        else:
            self._buildings_cache = []

        self._load_rentals()
        self._loaded = True

    def reload(self):
        self.load()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def buildings(self) -> list[str]:
        return self._buildings_cache


# Global singleton
data_store = DataStore()


def get_data_store() -> DataStore:
    return data_store
