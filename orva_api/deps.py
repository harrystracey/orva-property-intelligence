"""
Dependency injection for ORVA API.
Cached data loading — mirrors app.py load_data() logic.
"""

import pandas as pd
from functools import lru_cache

from .config import PARQUET_PATH, PF_CSV_PATH
from . import _sys_paths  # noqa: F401 -- puts project root on sys.path

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
        # client_id -> pandas index label. Built once at load so
        # /api/clients/{id} is O(1) instead of an O(n) scan over 78K rows.
        self._client_index: dict[str, int] = {}
        self._loaded = False

    def load(self):
        self.leads_df = _load_leads_df()
        self.ref_df, self.ref_stats = load_reference_data()
        self._rebuild_client_index()
        self._loaded = True

    def reload(self):
        self.load()

    def _rebuild_client_index(self) -> None:
        """Rebuild the client_id -> row index lookup. First-write-wins on
        duplicate ids (which shouldn't happen but we don't want to silently
        drop them either)."""
        # Imported here to avoid import cycles at module load
        from client_data_manager import make_client_id  # noqa: E402

        idx: dict[str, int] = {}
        if self.leads_df.empty:
            self._client_index = idx
            return
        for row_idx, row in self.leads_df.iterrows():
            cid = make_client_id(
                name=row.get("owner_name"),
                building=row.get("building_name"),
                unit=row.get("unit_number"),
            )
            if cid and cid not in idx:
                idx[cid] = row_idx
        self._client_index = idx

    def find_client_row(self, client_id: str):
        """
        Return the lead row for a client_id or None.

        Uses the precomputed index built during load(). Previous callers
        iterated 78K rows on every /api/clients/{id} request.
        """
        row_idx = self._client_index.get(client_id)
        if row_idx is None:
            return None
        return self.leads_df.loc[row_idx]

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
