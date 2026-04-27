"""Admin router -- ops endpoints (health, backup, table counts, PF leads).

Only accessible to authenticated users for now. In a true multi-tenant
deployment these would be gated by an `admin` role; that's Phase 7+ work.
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from .. import _sys_paths  # noqa: F401

from ..auth import get_current_user


router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# /api/admin/health -- system diagnostics dashboard
# ---------------------------------------------------------------------------

def _file_info(rel_path: str) -> dict:
    """Return {present, size_mb, mtime} for a file path; safe on missing files."""
    p = Path(rel_path)
    if not p.exists():
        return {"present": False, "size_mb": None, "modified": None}
    stat = p.stat()
    return {
        "present": True,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _csv_row_count(path: str) -> Optional[int]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except Exception:
        return None


@router.get("/health")
def health_check(user: dict = Depends(get_current_user)) -> dict:
    """
    Comprehensive system diagnostics. Used by the /tools/health UI.
    Read-only -- no side effects.
    """
    from database import get_table_counts, database_exists, get_db_path  # noqa: E402

    checks: dict[str, Any] = {}

    # ---- Lead database ----
    leads_xlsx = _file_info("lead_database/leads_master.xlsx")
    leads_csv = _file_info("lead_database/leads_master.csv")
    checks["lead_database"] = {
        "xlsx": leads_xlsx,
        "csv": leads_csv,
        "csv_rows": _csv_row_count("lead_database/leads_master.csv"),
    }

    # ---- Reference / DLD sales ----
    checks["reference_data"] = {
        "reference_master": _file_info("Master reference datasets/reference_master.csv"),
        "reference_master_with_units": _file_info(
            "Master reference datasets/reference_master_with_units.csv"
        ),
        "reference_master_rows": _csv_row_count(
            "Master reference datasets/reference_master.csv"
        ),
    }

    # ---- Reidin historical ----
    checks["reidin"] = {
        "parquet": _file_info("data/reidin_master.parquet"),
        "csv": _file_info("data/reidin_master.csv"),
    }

    # ---- Public scraper outputs ----
    checks["public_scrapers"] = {
        "bayut_listings": _file_info("data/bayut_palm_listings.csv"),
        "bayut_rows": _csv_row_count("data/bayut_palm_listings.csv"),
        "pf_listings": _file_info("scraped_data/propertyfinder_scraped_leads.csv"),
        "pf_rows": _csv_row_count("scraped_data/propertyfinder_scraped_leads.csv"),
    }

    # ---- SQLite database ----
    db_initialized = database_exists()
    checks["sqlite"] = {
        "initialized": db_initialized,
        "path": str(get_db_path()),
        "size_mb": (
            round(Path(get_db_path()).stat().st_size / (1024 * 1024), 2)
            if db_initialized else None
        ),
        "table_counts": get_table_counts() if db_initialized else {},
    }

    # ---- Environment ----
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    jwt_secret = os.getenv("JWT_SECRET", "")
    checks["environment"] = {
        "anthropic_api_key_set": bool(api_key),
        "anthropic_api_key_preview": (
            f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) >= 12 else None
        ),
        "jwt_secret_set": bool(jwt_secret),
        "jwt_secret_strong": len(jwt_secret) >= 32,
        "claude_model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }

    # ---- Python module health ----
    module_status: dict[str, bool] = {}
    for mod in ("data_processor", "ai_queries", "building_intelligence",
                "unit_registry", "contact_manager", "rental_processor",
                "listing_matcher.matcher"):
        try:
            __import__(mod)
            module_status[mod] = True
        except Exception:
            module_status[mod] = False
    checks["modules"] = module_status

    # ---- Building intelligence stats (if loadable) ----
    try:
        from building_intelligence import SHORELINE_TOWER_MAPPING, BUILDING_ALIASES  # noqa
        checks["building_intelligence"] = {
            "loaded": True,
            "shoreline_towers": len(SHORELINE_TOWER_MAPPING),
            "building_aliases": len(BUILDING_ALIASES),
        }
    except Exception as exc:
        checks["building_intelligence"] = {"loaded": False, "error": str(exc)}

    # ---- Overall status ----
    all_critical_ok = (
        checks["environment"]["jwt_secret_set"]
        and checks["environment"]["jwt_secret_strong"]
        and (leads_xlsx["present"] or leads_csv["present"] or db_initialized)
        and any(checks["modules"].values())
    )
    checks["overall"] = {
        "status": "ok" if all_critical_ok else "degraded",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    return checks


# ---------------------------------------------------------------------------
# /api/admin/db-counts -- legacy alias used by the existing UI
# ---------------------------------------------------------------------------

@router.get("/db-counts")
def db_counts(user: dict = Depends(get_current_user)) -> dict:
    """Row counts for every SQLite table -- useful for ops dashboards."""
    from database import get_table_counts, database_exists  # noqa: E402
    if not database_exists():
        return {"database_initialized": False, "counts": {}}
    return {"database_initialized": True, "counts": get_table_counts()}


# ---------------------------------------------------------------------------
# /api/admin/pf-leads -- read PropertyFinder scraped CSV for the /tools/pf-scraper UI
# ---------------------------------------------------------------------------

PF_CSV = Path("scraped_data/propertyfinder_scraped_leads.csv")


@router.get("/pf-leads")
def pf_leads(
    limit: int = Query(200, ge=1, le=2000),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Return rows from the PropertyFinder scraper output (data/.../propertyfinder_scraped_leads.csv)
    for the /tools/pf-scraper page. The scraper itself runs via CLI on a host
    with Chrome on port 9222 -- this endpoint is read-only.
    """
    if not PF_CSV.exists():
        return {
            "rows": [],
            "total": 0,
            "last_scraped": None,
            "csv_path": str(PF_CSV),
            "csv_present": False,
        }

    rows: list[dict] = []
    columns: list[str] = []
    total = 0
    try:
        with PF_CSV.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            columns = list(reader.fieldnames or [])
            for r in reader:
                total += 1
                if len(rows) < limit:
                    rows.append(r)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read PF CSV: {exc}") from exc

    last_scraped = datetime.fromtimestamp(PF_CSV.stat().st_mtime).isoformat(timespec="seconds")

    return {
        "rows": rows,
        "total": total,
        "columns": columns,
        "last_scraped": last_scraped,
        "csv_path": str(PF_CSV),
        "csv_present": True,
    }


@router.get("/backup")
def backup_database(user: dict = Depends(get_current_user)):
    """
    Stream a hot copy of the SQLite database file. Uses sqlite3.Connection.backup()
    so concurrent writes don't corrupt the snapshot.

    Returns the .db file as an attachment with a timestamped filename.
    """
    import sqlite3
    import tempfile
    from database import get_db_path  # noqa: E402

    src_path = get_db_path()
    if not src_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No SQLite database to back up. Run migrate_existing_data.py first.",
        )

    # Hot backup -- safe under WAL mode while writes are in flight.
    fd_dir = tempfile.mkdtemp(prefix="orva_backup_")
    out_name = f"orva_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    out_path = Path(fd_dir) / out_name

    try:
        src = sqlite3.connect(str(src_path))
        dst = sqlite3.connect(str(out_path))
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc

    return FileResponse(
        path=str(out_path),
        media_type="application/octet-stream",
        filename=out_name,
    )
