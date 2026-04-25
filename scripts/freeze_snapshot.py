"""
Freeze a dated, content-addressed snapshot of every data file the platform
relies on, so we can rebuild the SQLite database deterministically and
prove which input produced which database state.

Why this exists
---------------
Most data files are gitignored (too large for git). The user's main
machine is the only place they live. Before we cut over from CSV to
SQLite, we need a frozen copy of every input -- otherwise a CSV edit
six months from now silently changes the answers the SaaS gives.

What it does
------------
1. Walks a manifest of expected file paths (defined below).
2. For each file that exists locally:
     - Copies it into  data/snapshots/<YYYY-MM-DD>-frozen/<original/relative/path>
     - Records  filename, bytes, sha256, row count (for csv/parquet/xlsx)
       in   data/snapshots/<YYYY-MM-DD>-frozen/MANIFEST.json
3. Files that don't exist are recorded as `missing` -- not an error,
   so the script is safe to run on a partial checkout (e.g. this
   worktree, where most data files are gitignored).
4. Idempotent for a given date: running twice in one day overwrites
   the same folder. Running on a new date creates a new folder so
   you have a history of snapshots.

Run:
    python -m scripts.freeze_snapshot
    python -m scripts.freeze_snapshot --date 2026-04-25
    python -m scripts.freeze_snapshot --out data/snapshots/release-1.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Manifest -- every data file the platform reads, grouped by purpose.
#
# Edit this list when new data sources are added. Each entry is just a
# project-relative path; missing files are skipped, so adding a path that
# doesn't exist yet is harmless.
# ---------------------------------------------------------------------------

MANIFEST: dict[str, list[str]] = {
    "leads": [
        "lead_database/leads_master.csv",
        "lead_database/leads_master.xlsx",
    ],
    "reference_dld_sales": [
        "Master reference datasets/reference_master.csv",
        "Master reference datasets/reference_master_with_units.csv",
        "Master reference datasets/reference_backup_20260208_155912.csv",
        # Long DXBInteract export filename -- glob would be cleaner, but we
        # keep names explicit so the manifest is auditable.
        "Master reference datasets/palm-jumeirah-market-data-harry-stracey-e-and-t-real-estate-broker-llc-05-02-2026-79c428f41d5f7d494678e182d99a373da2a11876.csv",
        "reference_data/title_deed_reference.csv",
    ],
    "scraped_propertymonitor_historical": [
        # PM live scraper has been removed; these CSVs are the frozen
        # snapshot of what the user already had when access ended.
        "scraped_data/unit_numbers_palm_jumeirah.csv",
        "scraped_data/palm_jumeirah_rentals.csv",
        "scraped_data/palm_jumeirah_transactions_clean.xlsx",
    ],
    "reidin_historical": [
        # Reidin live scraper removed; the parquet/csv stay as the frozen
        # historical export the user had.
        "data/reidin_master.parquet",
        "data/reidin_master.csv",
    ],
    "propertyfinder_public": [
        "scraped_data/propertyfinder_scraped_leads.csv",
    ],
    "bayut_public": [
        "data/bayut_palm_listings.csv",
        "data/bayut_unit_types.csv",
    ],
    "derived_unit_registry": [
        "data/unit_registry.csv",
        "data/unit_registry_with_bayut.csv",
    ],
    "client_data": [
        "client_data/notes.json",
        "client_data/reminders.json",
        "client_data/call_log.json",
        "client_data/lead_overrides.json",
        "client_data/clients.json",
        "client_data/contacts.json",
    ],
    "whatsapp": [
        "whatsapp_bot/message_log.csv",
        "whatsapp_bot/chat_scans.csv",
        "whatsapp_bot/sent_log.csv",
    ],
    "sqlite_db": [
        # Snapshot the SQLite DB itself if it already exists -- gives
        # us a point-in-time backup alongside the CSV inputs.
        "data/palm_intelligence.db",
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    """Streaming sha256 -- works on multi-GB files without loading them all."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _row_count(path: Path) -> int | None:
    """Best-effort row count. Returns None if the file isn't tabular or
    pandas isn't available (we don't want to add a hard dep on pandas
    just for the snapshot tool)."""
    try:
        import pandas as pd  # local import so the script runs without pandas if needed
    except ImportError:
        return None

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            # Use only=lineterminator counting to avoid loading huge frames.
            with path.open("r", encoding="utf-8", errors="replace") as f:
                # Subtract 1 for header
                return max(sum(1 for _ in f) - 1, 0)
        if suffix in (".xlsx", ".xls"):
            return len(pd.read_excel(path, usecols=[0]))
        if suffix == ".parquet":
            return len(pd.read_parquet(path))
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, list):
                return len(obj)
            if isinstance(obj, dict):
                # client_data/notes.json shape: {client_id: [note, ...], ...}
                return sum(len(v) if isinstance(v, list) else 1 for v in obj.values())
            return None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def freeze_snapshot(
    *,
    project_root: Path,
    out_dir: Path,
    manifest: dict[str, list[str]] = MANIFEST,
    verbose: bool = True,
) -> dict:
    """
    Copy every file in `manifest` (relative to `project_root`) into `out_dir`,
    preserving the relative directory structure, and write a MANIFEST.json
    next to them with metadata for every entry.

    Returns the manifest dict it just wrote (also useful in tests).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_record: dict = {
        "snapshot_date": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root.resolve()),
        "groups": {},
        "totals": {"present": 0, "missing": 0, "bytes": 0, "rows": 0},
    }

    for group_name, paths in manifest.items():
        group_entries: list[dict] = []
        for rel in paths:
            src = project_root / rel
            entry: dict = {"path": rel}

            if not src.exists():
                entry["status"] = "missing"
                manifest_record["totals"]["missing"] += 1
                group_entries.append(entry)
                if verbose:
                    print(f"  [skip] {rel}  (not present locally)")
                continue

            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            size = src.stat().st_size
            entry.update({
                "status": "frozen",
                "bytes": size,
                "sha256": _sha256(src),
            })
            rows = _row_count(src)
            if rows is not None:
                entry["rows"] = rows
                manifest_record["totals"]["rows"] += rows

            manifest_record["totals"]["present"] += 1
            manifest_record["totals"]["bytes"] += size
            group_entries.append(entry)
            if verbose:
                detail = f"{size:,} bytes" + (f", {rows:,} rows" if rows is not None else "")
                print(f"  [ok]   {rel}  ({detail})")

        manifest_record["groups"][group_name] = group_entries

    manifest_path = out_dir / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest_record, indent=2),
        encoding="utf-8",
    )

    if verbose:
        t = manifest_record["totals"]
        print()
        print(f"Snapshot written to: {out_dir}")
        print(f"  files frozen:  {t['present']}")
        print(f"  files missing: {t['missing']}")
        print(f"  total size:    {t['bytes'] / 1024 / 1024:.1f} MB")
        if t["rows"]:
            print(f"  total rows:    {t['rows']:,}")
        print(f"  manifest:      {manifest_path}")

    return manifest_record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date label for the snapshot folder (default: today).",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Override output directory. Default: data/snapshots/<date>-frozen.",
    )
    p.add_argument(
        "--root",
        default=None,
        help="Override project root. Default: parent of this scripts/ folder.",
    )
    p.add_argument("--quiet", action="store_true", help="Suppress per-file output.")
    args = p.parse_args(argv)

    project_root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    out_dir = Path(args.out) if args.out else project_root / "data" / "snapshots" / f"{args.date}-frozen"

    record = freeze_snapshot(
        project_root=project_root,
        out_dir=out_dir,
        verbose=not args.quiet,
    )
    # Non-zero exit only if the snapshot is empty -- that almost certainly
    # means the user ran it from the wrong directory.
    if record["totals"]["present"] == 0:
        print("\nNo data files were found. Did you run this from the wrong project root?", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
