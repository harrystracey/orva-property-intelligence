"""Admin router -- ops endpoints (backup, table counts).

Only accessible to authenticated users for now. In a true multi-tenant
deployment these would be gated by an `admin` role; that's Phase 7+ work.
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .. import _sys_paths  # noqa: F401

from ..auth import get_current_user


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/db-counts")
def db_counts(user: dict = Depends(get_current_user)) -> dict:
    """Row counts for every SQLite table -- useful for ops dashboards."""
    from database import get_table_counts, database_exists  # noqa: E402
    if not database_exists():
        return {"database_initialized": False, "counts": {}}
    return {"database_initialized": True, "counts": get_table_counts()}


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
