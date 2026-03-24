"""Pydantic models for lead search API."""

from pydantic import BaseModel
from typing import Optional


class LeadFilter(BaseModel):
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    owner_name: Optional[str] = None
    building_search: Optional[str] = None
    bedrooms: Optional[str] = None
    unit_number: Optional[str] = None
    phone: Optional[str] = None
    phone_required: bool = False
    min_completeness: int = 0
    min_size_sqft: Optional[float] = None
    max_size_sqft: Optional[float] = None
    hide_flagged: bool = False
    source_filter: Optional[str] = None
    sort_by: str = "completeness"  # completeness, newest, oldest
    page: int = 1
    page_size: int = 250


class LeadRecord(BaseModel):
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    building_name: Optional[str] = None
    unit_number: Optional[str] = None
    bedrooms: Optional[float] = None
    size_sqft: Optional[float] = None
    floor: Optional[str] = None
    date: Optional[str] = None
    completeness: Optional[float] = None
    source: Optional[str] = None
    listing_type: Optional[str] = None
    transaction_value: Optional[float] = None
    bedroom_method: Optional[str] = None
    bedroom_confidence: Optional[str] = None


class LeadSearchResponse(BaseModel):
    leads: list[LeadRecord]
    total: int
    page: int
    page_size: int
    total_pages: int


class BuildingListResponse(BaseModel):
    buildings: list[str]
    count: int
