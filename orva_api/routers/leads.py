"""Lead search API — paginated, filtered, sorted."""

import io
import math

import pandas as pd
from fastapi import APIRouter, Depends, Query, Response

from .. import _sys_paths  # noqa: F401 -- puts project root on sys.path

from data_processor import apply_filters  # noqa: E402

from ..auth import get_current_user
from ..deps import DataStore, get_data_store
from ..schemas.leads import (
    BuildingListResponse,
    LeadFilter,
    LeadRecord,
    LeadSearchResponse,
)

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _sort_df(df: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    if sort_by == "newest":
        return df.sort_values("date", ascending=False, na_position="last")
    elif sort_by == "oldest":
        return df.sort_values("date", ascending=True, na_position="last")
    else:  # completeness (default)
        return df.sort_values("completeness", ascending=False, na_position="last")


def _df_to_records(df: pd.DataFrame) -> list[LeadRecord]:
    records = []
    for _, row in df.iterrows():
        date_val = row.get("date")
        date_str = None
        if pd.notna(date_val):
            try:
                date_str = str(date_val)[:10]
            except Exception:
                pass

        records.append(LeadRecord(
            owner_name=row.get("owner_name") if pd.notna(row.get("owner_name")) else None,
            phone=row.get("phone") if pd.notna(row.get("phone")) else None,
            building_name=row.get("building_name") if pd.notna(row.get("building_name")) else None,
            unit_number=row.get("unit_number") if pd.notna(row.get("unit_number")) else None,
            bedrooms=float(row["bedrooms"]) if pd.notna(row.get("bedrooms")) else None,
            size_sqft=float(row["size_sqft"]) if pd.notna(row.get("size_sqft")) else None,
            floor=str(row["floor"]) if pd.notna(row.get("floor")) else None,
            date=date_str,
            completeness=float(row["completeness"]) if pd.notna(row.get("completeness")) else None,
            source=row.get("source") if pd.notna(row.get("source")) else None,
            listing_type=row.get("listing_type") if pd.notna(row.get("listing_type")) else None,
            transaction_value=float(row["transaction_value"]) if pd.notna(row.get("transaction_value")) else None,
            bedroom_method=row.get("bedroom_method") if pd.notna(row.get("bedroom_method")) else None,
            bedroom_confidence=row.get("bedroom_confidence") if pd.notna(row.get("bedroom_confidence")) else None,
        ))
    return records


@router.get("", response_model=LeadSearchResponse)
def search_leads(
    date_start: str | None = None,
    date_end: str | None = None,
    owner_name: str | None = None,
    building_search: str | None = None,
    bedrooms: str | None = None,
    unit_number: str | None = None,
    phone: str | None = None,
    phone_required: bool = False,
    min_completeness: int = 0,
    min_size_sqft: float | None = None,
    max_size_sqft: float | None = None,
    hide_flagged: bool = False,
    source_filter: str | None = None,
    sort_by: str = "completeness",
    page: int = Query(1, ge=1),
    page_size: int = Query(250, ge=1, le=1000),
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    filtered = apply_filters(
        store.leads_df,
        date_start=date_start,
        date_end=date_end,
        owner_name=owner_name,
        building_search=building_search,
        bedrooms=bedrooms,
        unit_number=unit_number,
        phone=phone,
        phone_required=phone_required,
        min_completeness=min_completeness,
        min_size_sqft=min_size_sqft,
        max_size_sqft=max_size_sqft,
        hide_flagged=hide_flagged,
        source_filter=source_filter,
    )

    sorted_df = _sort_df(filtered, sort_by)
    total = len(sorted_df)
    total_pages = max(1, math.ceil(total / page_size))

    start = (page - 1) * page_size
    end = start + page_size
    page_df = sorted_df.iloc[start:end]

    return LeadSearchResponse(
        leads=_df_to_records(page_df),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/export")
def export_leads(
    filters: LeadFilter,
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    filtered = apply_filters(
        store.leads_df,
        date_start=filters.date_start,
        date_end=filters.date_end,
        owner_name=filters.owner_name,
        building_search=filters.building_search,
        bedrooms=filters.bedrooms,
        unit_number=filters.unit_number,
        phone=filters.phone,
        phone_required=filters.phone_required,
        min_completeness=filters.min_completeness,
        min_size_sqft=filters.min_size_sqft,
        max_size_sqft=filters.max_size_sqft,
        hide_flagged=filters.hide_flagged,
        source_filter=filters.source_filter,
    )
    sorted_df = _sort_df(filtered, filters.sort_by)

    buf = io.StringIO()
    export_cols = [
        "owner_name", "phone", "building_name", "unit_number",
        "bedrooms", "size_sqft", "date", "completeness", "source",
    ]
    cols = [c for c in export_cols if c in sorted_df.columns]
    sorted_df[cols].to_csv(buf, index=False)

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orva_leads_export.csv"},
    )


@router.get("/buildings", response_model=BuildingListResponse)
def list_buildings(
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    buildings = store.buildings
    return BuildingListResponse(buildings=buildings, count=len(buildings))


@router.post("/reload")
def reload_data(
    store: DataStore = Depends(get_data_store),
    user: dict = Depends(get_current_user),
):
    store.reload()
    return {"status": "ok", "total_leads": len(store.leads_df)}
