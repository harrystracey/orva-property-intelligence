"""
Dependency injection for ORVA API.
Cached data loading — mirrors app.py load_data() logic.
"""

import sys
import pandas as pd
from pathlib import Path
from functools import lru_cache

from .config import PROJECT_ROOT, PARQUET_PATH, PF_CSV_PATH

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
        except Exception:
            pass

    return df


class DataStore:
    """Singleton data store. Loaded once at startup, refreshable."""

    def __init__(self):
        self.leads_df: pd.DataFrame = pd.DataFrame()
        self.ref_df: pd.DataFrame = pd.DataFrame()
        self.ref_stats: dict = {}
        self._loaded = False

    def load(self):
        self.leads_df = _load_leads_df()
        self.ref_df, self.ref_stats = load_reference_data()
        self._loaded = True

    def reload(self):
        self.load()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def buildings(self) -> list[str]:
        if self.leads_df.empty:
            return []
        return sorted(
            self.leads_df["building_name"]
            .dropna()
            .str.strip()
            .loc[lambda s: s.ne("")]
            .unique()
            .tolist()
        )


# Global singleton
data_store = DataStore()


def get_data_store() -> DataStore:
    return data_store
