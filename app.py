"""
Streamlit Lead Search Application
Palm Jumeirah Real Estate - Clean Output Format with AI Assistant
Multi-page layout with ChatGPT-style AI interface
"""

import streamlit as st
import pandas as pd
import os
import re
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

try:
    from data_processor import (
        process_and_clean_data, apply_filters, format_for_display, export_to_csv,
        get_unique_buildings, get_unique_bedrooms, aggregate_portfolios, format_portfolio_for_display,
        BUILDING_UNIT_SCHEMA, get_portfolio_summary_for_ai, load_reference_data,
        search_building_names_for_ai, get_complete_building_intel_for_ai,
        get_recent_transaction_lead_mask,
        get_recent_transaction_dates,
        get_recent_transaction_details,
        get_last_sale_per_units,
        get_listings_below_market_for_ai,
        get_propertyfinder_listings_for_ai,
        standardize_building_name,
    )
    import chat_manager as cm
    import client_data_manager as cdm
    from database import init_database
    import contact_manager as con_man
    from rental_processor import (
        load_rental_data, get_expiring_leases, get_active_rental_count,
        get_rental_intel_for_ai, cross_reference_rentals_with_owners,
        get_unit_rental_status, get_lease_renewal_history,
    )
except ImportError as e:
    st.error("**Critical Module Missing**")
    st.error(f"Error: {e}")
    st.info("**Solution:**")
    st.code("pip install -r requirements.txt --break-system-packages")
    st.info("If that doesn't work, check that all .py files are in the correct directory.")
    st.stop()
except Exception as e:
    st.error("**Unexpected Error During Import**")
    st.error(f"{type(e).__name__}: {e}")
    st.info("Check that all dependencies are installed and files are not corrupted.")
    st.stop()

from logger_config import app_logger, ai_logger

# WhatsApp bot imports
sys.path.insert(0, str(Path(__file__).resolve().parent / 'whatsapp_bot'))
from whatsapp_bot.message_log import (
    get_send_stats,
    get_recent_messages,
    get_today_send_count,
    get_reply_stats,
    get_sent_entries_for_reply_check,
    record_reply,
)
from whatsapp_bot.campaign_manager import (
    build_landlord_lease_expiry_queue, build_cold_owner_queue,
    build_portfolio_owner_queue, build_active_seller_queue, build_active_renter_queue,
    apply_dedup_to_queue, generate_messages_for_queue
)
from whatsapp_bot.bot import format_phone_for_whatsapp, connect_to_whatsapp, check_replies_for_sent_messages

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="ORVA — Property Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL CSS STYLES
# ═══════════════════════════════════════════════════════════════════════════════

def apply_global_styles():
    """Apply global CSS styles — ORVA emerald dark theme."""
    st.markdown("""
    <style>
        /* ── Base dark background ── */
        .stApp {
            background-color: #0f1117 !important;
        }
        .main .block-container {
            background-color: #0f1117 !important;
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }

        /* ── Sidebar dark ── */
        [data-testid="stSidebar"] {
            background-color: #141720 !important;
            border-right: 1px solid #1e2433 !important;
        }
        [data-testid="stSidebar"] .stButton button {
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            color: #94a3b8 !important;
        }
        [data-testid="stSidebar"] .stButton button:hover {
            background-color: #10b981 !important;
            border-color: #10b981 !important;
            color: #0f1117 !important;
        }

        /* ── Nav buttons (secondary) — no wrapping ── */
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            border-left: 2px solid #10b981 !important;
            color: #94a3b8 !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            transition: all 0.2s ease !important;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover {
            background-color: #10b981 !important;
            border-color: #10b981 !important;
            border-left-color: #10b981 !important;
            color: #0f1117 !important;
            font-weight: 600 !important;
        }

        /* ── Primary button (HLM) — emerald ── */
        div[data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            border: none !important;
            color: #0f1117 !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
            white-space: nowrap !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35) !important;
            transition: all 0.2s ease !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover {
            background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.5) !important;
            transform: translateY(-1px) !important;
        }

        /* ── Popover button ── */
        div[data-testid="stPopover"] > div > button {
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            border-left: 2px solid #10b981 !important;
            color: #94a3b8 !important;
            border-radius: 8px !important;
            font-size: 12px !important;
            white-space: nowrap !important;
            transition: all 0.2s ease !important;
        }
        div[data-testid="stPopover"] > div > button:hover {
            border-color: #10b981 !important;
            color: #10b981 !important;
        }

        /* ── Metrics ── */
        div[data-testid="stMetric"] {
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            border-radius: 10px !important;
            padding: 12px 16px !important;
        }
        div[data-testid="stMetricValue"] {
            color: #10b981 !important;
        }
        div[data-testid="stMetricLabel"] {
            color: #94a3b8 !important;
        }

        /* ── Expanders ── */
        div[data-testid="stExpander"] {
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            border-radius: 10px !important;
        }

        /* ── Tabs ── */
        button[data-baseweb="tab"] {
            color: #94a3b8 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #10b981 !important;
            border-bottom-color: #10b981 !important;
        }

        /* ── Dividers ── */
        hr {
            border-color: #2d3748 !important;
        }

        /* ── Chat messages ── */
        [data-testid="stChatMessage"] {
            border-radius: 12px;
            background-color: #1a1d27 !important;
            border: 1px solid #2d3748 !important;
            margin-bottom: 0.5rem;
        }
    </style>
    """, unsafe_allow_html=True)


def apply_ai_page_styles():
    """Apply CSS styles specific to the AI chat page."""
    st.markdown("""
    <style>
        /* Dark sidebar for AI page */
        [data-testid="stSidebar"] {
            background-color: #171717 !important;
        }
        
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            color: #e5e5e5 !important;
        }
        
        [data-testid="stSidebar"] .stButton button {
            background-color: #262626 !important;
            border: 1px solid #404040 !important;
            color: #e5e5e5 !important;
        }
        
        [data-testid="stSidebar"] .stButton button:hover {
            background-color: #404040 !important;
            border-color: #525252 !important;
        }
        
        /* Active chat button */
        [data-testid="stSidebar"] .stButton button[kind="primary"] {
            background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%) !important;
            border: none !important;
        }
        
        /* Full width chat area */
        .main .block-container {
            max-width: 100%;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        
        /* Chat input styling */
        .stChatInput {
            border-radius: 24px !important;
        }
        
        /* Welcome message styling */
        .welcome-box {
            background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
            border-radius: 16px;
            padding: 2rem;
            margin: 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _pf_csv_mtime():
    """Mtime of PropertyFinder scraped CSV so load_data cache invalidates when scraper adds rows."""
    p = Path(__file__).resolve().parent / "scraped_data" / "propertyfinder_scraped_leads.csv"
    return p.stat().st_mtime if p.exists() else 0.0


def _parquet_mtime():
    p = Path(__file__).resolve().parent / "lead_database" / "leads_master.parquet"
    return p.stat().st_mtime if p.exists() else 0.0


# Map from app column names back to parquet column names for write-back
_APP_TO_PARQUET_COLS = {
    "owner_name": "Owner Name",
    "phone": "Phone",
    "building_name": "Building Name",
    "unit_number": "Unit Number",
    "bedrooms": "Bedrooms",
    "size_sqft": "Size (sqft)",
}


def _update_lead_in_parquet(owner_name: str, building: str, unit: str, updates: dict) -> bool:
    """Write field edits directly into leads_master.parquet and bust the load_data cache."""
    pq = Path(__file__).resolve().parent / "lead_database" / "leads_master.parquet"
    if not pq.exists():
        return False
    try:
        df = pd.read_parquet(pq)
        mask = (
            df["Owner Name"].fillna("").str.strip().str.lower() == str(owner_name).strip().lower()
        )
        if "Building Name" in df.columns:
            mask &= df["Building Name"].fillna("").str.strip().str.lower() == str(building).strip().lower()
        if "Unit Number" in df.columns:
            mask &= df["Unit Number"].fillna("").str.strip().str.lower() == str(unit).strip().lower()
        if not mask.any():
            return False
        for app_col, value in updates.items():
            pq_col = _APP_TO_PARQUET_COLS.get(app_col, app_col)
            if pq_col in df.columns and value not in ("", None):
                # Coerce numeric fields
                if pq_col == "Bedrooms":
                    try:
                        value = float(value) if str(value).lower() != "studio" else 0.0
                    except ValueError:
                        pass
                elif pq_col == "Size (sqft)":
                    try:
                        value = float(str(value).replace(",", ""))
                    except ValueError:
                        continue
                df.loc[mask, pq_col] = value
        df.to_parquet(pq, index=False)
        load_data.clear()  # bust the Streamlit cache so changes appear immediately
        return True
    except Exception:
        return False


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


@st.cache_data(show_spinner=False)
def load_data(_pf_mtime=0.0, _pq_mtime=0.0):
    """Fast-path: load from leads_master.parquet (built by consolidate_data.py).
    Falls back to the slow process_and_clean_data pipeline only if no parquet exists."""
    _root = Path(__file__).resolve().parent
    pq = _root / "lead_database" / "leads_master.parquet"

    if pq.exists():
        app_logger.info("Fast-loading leads from parquet")
        df = pd.read_parquet(pq)
        df.rename(columns=_PARQUET_TO_APP_COLS, inplace=True)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "bedrooms" in df.columns:
            df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce")
        if "size_sqft" in df.columns:
            df["size_sqft"] = pd.to_numeric(df["size_sqft"], errors="coerce")

        # Columns the app expects but parquet may not have
        for col, default in [
            ("size_sqm", pd.NA), ("size_method", ""), ("size_confidence", ""),
            ("bedroom_method", ""), ("bedroom_confidence", ""),
            ("listing_price", pd.NA), ("listing_type", ""), ("listing_url", ""),
            ("furnished", ""), ("pf_listing_count", 0), ("source", "crm"),
            ("completeness", 0), ("data_quality", ""),
        ]:
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

        # Merge PF scraped data if it exists
        pf_csv = _root / "scraped_data" / "propertyfinder_scraped_leads.csv"
        if pf_csv.exists():
            try:
                pf = pd.read_csv(pf_csv, encoding="utf-8", low_memory=False, on_bad_lines="skip")
                if not pf.empty and "owner_name" in pf.columns:
                    pf["source"] = "propertyfinder"
                    for c in df.columns:
                        if c not in pf.columns:
                            pf[c] = pd.NA
                    pf = pf[[c for c in df.columns if c in pf.columns]]
                    df = pd.concat([df, pf], ignore_index=True)
            except Exception as exc:
                app_logger.warning(f"PF merge skipped: {exc}")

        # Synthesise a minimal diag dict so the sidebar doesn't break
        ref_df, ref_stats = load_reference_data()
        diag = {
            "files_loaded": ["leads_master.parquet"],
            "file_row_counts": {"leads_master.parquet": len(df)},
            "raw_rows": len(df),
            "rows_after_cleaning": len(df),
            "duplicates_removed": 0,
            "invalid_rows_removed": 0,
            "errors": [],
            "ref_stats": ref_stats,
            "enrichment_stats": {
                "beds_original": int(df["bedrooms"].notna().sum()),
                "beds_from_exact": 0, "beds_from_schema": 0,
                "beds_from_pattern": 0, "beds_from_size": 0,
                "beds_from_default": 0, "beds_unresolved": int(df["bedrooms"].isna().sum()),
                "size_original": int(df["size_sqft"].notna().sum()),
                "size_from_exact": 0, "size_estimated": 0,
                "size_unresolved": int(df["size_sqft"].isna().sum()),
                "validation_flags": 0,
            },
            "unit_patterns_learned": 0,
            "schema_buildings": 0,
            "default_buildings": 0,
        }
        app_logger.info(f"Loaded {len(df):,} leads from parquet (fast path)")
        return df, diag

    # Slow fallback — only if parquet doesn't exist
    try:
        app_logger.info("Loading lead data from ./data (slow path)")
        df, diag = process_and_clean_data('./data')
        app_logger.info(f"Successfully loaded {len(df):,} leads")
        return df, diag
    except Exception as e:
        app_logger.error(f"Failed to load data: {e}", exc_info=True)
        raise


@st.cache_data(show_spinner=False)
def get_reference_data():
    """Load reference data for AI."""
    ref_df, _ = load_reference_data()
    return ref_df


@st.cache_data(show_spinner=False)
def load_rentals():
    """Load rental transaction data."""
    return load_rental_data()


@st.cache_data(ttl=300, show_spinner=False)
def load_registry_financial():
    """Load unit registry as fast lookup dict for client matching."""
    p = Path("data/unit_registry.csv")
    if not p.exists():
        return {}
    df = pd.read_csv(p, encoding="utf-8", low_memory=False)
    lookup = {}
    for _, r in df.iterrows():
        bkey = str(r["building_name"]).strip().lower().replace(" ", "").replace("-", "")
        ukey = str(r["unit_number"]).strip().upper().replace(" ", "").replace("-", "")
        key = f"{bkey}|{ukey}"
        lookup[key] = {
            "view":            str(r["view"]) if pd.notna(r.get("view")) else None,
            "confidence":      str(r.get("confidence", "MEDIUM")),
            "last_sale_price": float(r["last_sale_price"]) if pd.notna(r.get("last_sale_price")) else None,
            "last_sale_date":  str(r["last_sale_date"]) if pd.notna(r.get("last_sale_date")) else None,
            "last_annual_rent":float(r["last_annual_rent"]) if pd.notna(r.get("last_annual_rent")) else None,
            "rental_count":    int(r["rental_count"]) if pd.notna(r.get("rental_count")) else 0,
            "sale_count":      int(r["sale_count"]) if pd.notna(r.get("sale_count")) else 0,
        }
    return lookup


@st.cache_data(ttl=300, show_spinner=False)
def load_bayut_listings():
    """Load active Bayut listings from bayut_palm_listings.csv."""
    p = Path("data/bayut_palm_listings.csv")
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8", low_memory=False)
    # Normalise building name for matching
    df["_building_key"] = (
        df["building_name"].fillna("").str.lower()
        .str.replace(r"[\s\-]", "", regex=True)
    )
    return df


def get_bayut_listings_for_ai(listing_type="all", building=None, bedrooms=None,
                               min_price=None, max_price=None, limit=30):
    """Return Bayut listings as formatted text for the AI to read."""
    df = load_bayut_listings()
    if df.empty:
        return "No Bayut listings data available. Run the Bayut scraper first."

    # Filters
    if listing_type and listing_type != "all":
        df = df[df["listing_type"].str.lower() == listing_type.lower()]
    if building:
        std = standardize_building_name(building) or building
        bkey = std.strip().lower().replace(" ", "").replace("-", "")
        df = df[df["_building_key"].str.contains(bkey, na=False)]
    if bedrooms is not None:
        df = df[pd.to_numeric(df["bedrooms"], errors="coerce").round() == int(bedrooms)]
    if min_price is not None:
        df = df[pd.to_numeric(df["price_aed"], errors="coerce") >= min_price]
    if max_price is not None:
        df = df[pd.to_numeric(df["price_aed"], errors="coerce") <= max_price]

    if df.empty:
        return f"No Bayut listings found matching those filters."

    total = len(df)
    sale_n = int((df["listing_type"].str.lower() == "sale").sum())
    rent_n = int((df["listing_type"].str.lower() == "rent").sum())
    buildings_n = df["building_name"].nunique()
    last_scraped = ""
    if "scraped_at" in df.columns:
        ts = df["scraped_at"].dropna()
        if not ts.empty:
            last_scraped = f" — last updated {str(ts.max())[:10]}"

    lines = [
        f"BAYUT LISTINGS ({total} total: {sale_n} for sale, {rent_n} for rent, {buildings_n} buildings{last_scraped})",
        "",
        f"{'Building':<30} {'Type':<5} {'Beds':<5} {'Size sqft':<10} {'Price AED':<14} {'View':<18} URL",
        "-" * 120,
    ]

    display = df.head(limit)
    for _, r in display.iterrows():
        bld = str(r.get("building_name", ""))[:29]
        typ = str(r.get("listing_type", ""))[:4].upper()
        beds = str(int(r["bedrooms"])) if pd.notna(r.get("bedrooms")) else "-"
        size = f"{int(r['size_sqft']):,}" if pd.notna(r.get("size_sqft")) else "-"
        price = f"AED {int(r['price_aed']):,}" if pd.notna(r.get("price_aed")) else "-"
        view = str(r.get("view", "") or "")[:17]
        url = str(r.get("listing_url", "") or "")
        lines.append(f"{bld:<30} {typ:<5} {beds:<5} {size:<10} {price:<14} {view:<18} {url}")

    if total > limit:
        lines.append(f"\n... {total - limit} more listings (use building/bedroom/price filters to narrow down)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR COMPONENTS (LEAD SEARCH PAGE)
# ═══════════════════════════════════════════════════════════════════════════════

def render_reference_status(diag):
    """Render reference data status."""
    st.sidebar.header(" Reference Data")
    ref_stats = diag.get('ref_stats', {})
    
    if ref_stats.get('loaded'):
        st.sidebar.success("✓ Reference: Active")
        st.sidebar.caption(f" • {ref_stats.get('record_count', 0):,} transactions")
        st.sidebar.caption(f" • {ref_stats.get('unique_buildings', 0)} buildings")
        if ref_stats.get('sale_date_min') and ref_stats.get('sale_date_max'):
            st.sidebar.caption(f" • Reference sales: {ref_stats['sale_date_min']} to {ref_stats['sale_date_max']}")
    else:
        st.sidebar.warning("⚠ No Reference Data")
        st.sidebar.caption(f" {ref_stats.get('error', 'Not found')}")


def render_enrichment_stats(diag):
    """Render enrichment statistics (flat keys from data_processor enrichment_stats)."""
    st.sidebar.header(" Enrichment Stats")
    stats = diag.get('enrichment_stats', {})
    schema_count = diag.get('schema_buildings', 0)
    default_count = diag.get('default_buildings', 0)

    beds_from_exact = stats.get('beds_from_exact', 0)
    beds_original = stats.get('beds_original', 0)
    beds_from_schema = stats.get('beds_from_schema', 0)
    beds_from_pattern = stats.get('beds_from_pattern', 0)
    beds_from_size = stats.get('beds_from_size', 0)
    beds_from_default = stats.get('beds_from_default', 0)
    beds_unresolved = stats.get('beds_unresolved', 0)
    total_beds = beds_from_exact + beds_original + beds_from_schema + beds_from_pattern + beds_from_size + beds_from_default

    size_from_exact = stats.get('size_from_exact', 0)
    size_original = stats.get('size_original', 0)
    size_estimated = stats.get('size_estimated', 0)
    size_unresolved = stats.get('size_unresolved', 0)
    total_size = size_from_exact + size_original + size_estimated

    st.sidebar.metric("Bedrooms Resolved", f"{total_beds:,}",
                     delta=f"{beds_unresolved:,} unresolved")
    st.sidebar.metric("Size Data", f"{total_size:,}",
                     delta=f"{size_unresolved:,} unresolved")
    if beds_from_exact or size_from_exact:
        st.sidebar.caption(f" From Reference (Exact): beds {beds_from_exact:,} / size {size_from_exact:,}")
    st.sidebar.caption(f" Schema buildings: {schema_count}")
    st.sidebar.caption(f" Default fallback: {default_count}")
    
    # Unit registry stats
    try:
        from unit_registry import get_registry_stats
        stats_reg = get_registry_stats()
        if stats_reg.get("total_units", 0) > 0:
            st.sidebar.divider()
            st.sidebar.markdown("** Unit Registry**")
            st.sidebar.caption(f"Total units: {stats_reg['total_units']:,}")
            st.sidebar.caption(f"Buildings: {stats_reg['buildings']:,}")
            st.sidebar.caption(f"HIGH confidence: {stats_reg['high_confidence']:,}")
            st.sidebar.caption(f"With views: {stats_reg['with_view']:,}")
    except Exception:
        pass


def render_diagnostics(diag):
    """Render diagnostic information."""
    with st.sidebar.expander(" Data Diagnostics"):
        st.write(f"**Total Leads:** {diag.get('total_rows', 0):,}")
        st.write(f"**Duplicates Removed:** {diag.get('duplicates_removed', 0):,}")
        st.write(f"**Files Loaded:** {diag.get('files_loaded', 0)}")
        if diag.get('errors'):
            st.error(f"Errors: {len(diag['errors'])}")


def render_schema_guide():
    """Render schema guide expander."""
    with st.sidebar.expander(" Building Schemas"):
        st.caption("Buildings with unit number patterns:")
        for building in sorted(BUILDING_UNIT_SCHEMA.keys())[:10]:
            st.caption(f" • {building}")
        if len(BUILDING_UNIT_SCHEMA) > 10:
            st.caption(f" ... and {len(BUILDING_UNIT_SCHEMA) - 10} more")


def render_building_reference():
    """Render building reference guide."""
    with st.sidebar.expander(" Building Reference"):
        st.markdown("""
        **Shoreline (Arabic → English):**
        - Al Basri → Shoreline 1
        - Al Sahab → Shoreline 2
        - Al Dawaar → Shoreline 4
        - Al Das → Shoreline 10
        
        **Major Buildings:**
        - Oceana (Caribbean, Pacific, Atlantic)
        - Marina Residences
        - Seven Palm / Palm Tower
        - Fairmont, Tiara, Anantara
        """)


def render_filters(df, portfolio_mode=False):
    """Render filter controls."""
    with st.expander(" Search Filters", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            date_start = st.date_input("From Date", value=None, key="date_start")
            owner_name = st.text_input("Owner Name", placeholder="Search owner...", key="owner_search")
        
        with col2:
            date_end = st.date_input("To Date", value=None, key="date_end")
            building_search = st.text_input("Building", placeholder="e.g., Shoreline 5", key="building_search")
        
        with col3:
            bedroom_options = ['All'] + sorted([str(b) for b in get_unique_bedrooms(df) if pd.notna(b)])
            bedrooms = st.selectbox("Bedrooms", bedroom_options, key="bedrooms")
            unit_number = st.text_input("Unit Number", placeholder="e.g., 1203", key="unit_search")
        
        with col4:
            phone = st.text_input("Phone Number", placeholder="Search phone...", key="phone_search")
            phone_required = st.checkbox("Has Phone Only", value=True, key="phone_required")
        
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            min_completeness = st.slider("Min Completeness %", 0, 100, 0, key="completeness")
        
        with col6:
            min_size = st.number_input("Min Size (sqft)", min_value=0, value=0, key="min_size")
        
        with col7:
            max_size = st.number_input("Max Size (sqft)", min_value=0, value=0, key="max_size")
        
        with col8:
            hide_flagged = st.checkbox("Hide Flagged", value=False, key="hide_flagged")
            source_filter = st.selectbox(
                "Source",
                options=["All", "CRM", "PropertyFinder"],
                key="source_filter",
                help="CRM = lead list only; PropertyFinder = scraped listing leads"
            )
            recently_transacted = st.checkbox(
                "Recently transacted only",
                value=False,
                key="recently_transacted",
                help="Show only leads whose building+unit has a sale in reference data (last 90 / 180 / 365 days)"
            )
            recent_transacted_days = st.selectbox(
                "Sales in last",
                options=[90, 180, 365],
                format_func=lambda x: f"{x} days" if x == 90 else f"{x} days ({'6 months' if x == 180 else '1 year'})",
                index=0,
                key="recent_transacted_days",
                help="How far back to look for matching transactions"
            )
            title_deed_only = st.checkbox(
                "Title Deed only",
                value=True,
                key="title_deed_only",
                help="Exclude Oqood (off-plan); match only Title Deed transactions"
            )
            resale_only = st.checkbox(
                "Resale only",
                value=True,
                key="resale_only",
                help="Exclude Initial Sale; match only Resale (owner-to-owner)"
            )
            if portfolio_mode:
                min_properties = st.number_input("Min Properties", min_value=2, value=2, key="min_props")
            else:
                min_properties = 2
    
    return {
        'date_start': date_start,
        'date_end': date_end,
        'owner_name': owner_name,
        'building_search': building_search,
        'bedrooms': None if bedrooms == 'All' else int(bedrooms) if bedrooms.isdigit() else bedrooms,
        'unit_number': unit_number,
        'phone': phone,
        'phone_required': phone_required,
        'min_completeness': min_completeness,
        'min_size_sqft': min_size if min_size > 0 else None,
        'max_size_sqft': max_size if max_size > 0 else None,
        'hide_flagged': hide_flagged,
        'source_filter': source_filter,
        'recently_transacted_only': recently_transacted,
        'recent_transacted_days': recent_transacted_days,
        'title_deed_only': title_deed_only,
        'resale_only': resale_only,
        'min_properties': min_properties
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AI QUERY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def query_leads_with_ai(user_query: str, leads_df: pd.DataFrame, reference_df: pd.DataFrame, chat_history: list = None) -> str:
    """Process natural language query using Claude API with function calling."""
    import time
    
    ai_logger.info(f"AI Query: {user_query[:100]}")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return """⚠ **Claude API Key Required**

To use the AI assistant:
1. Get your API key from: https://console.anthropic.com/
2. Create a `.env` file with: `ANTHROPIC_API_KEY=your-key-here`
3. Or use `start_app.ps1` which has the key pre-configured"""
    
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        # Full tool set - cross-referencing enabled (unit numbers scraped from Property Monitor)
        tools = [
            {
                "name": "get_building_intel",
                "description": "Get building intelligence: market pricing with unit numbers, owner contacts, and cross-referenced matches. Set matched_only=true when user asks for sales 'where you know the owner' or 'with contacts'.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {"type": "string", "description": "Building name (e.g., 'Ellington', 'Shoreline 5', 'Al Masalli', 'Fairmont')"},
                        "bedrooms": {"type": "integer", "description": "Filter by bedrooms (0=studio, 1, 2, 3, 4+). Optional."},
                        "matched_only": {"type": "boolean", "description": "If true, only return sales where owner contact is known from lead database. Use when user asks for sales 'where you know the owner' or 'with contacts'. Default false."},
                        "limit": {"type": "integer", "description": "Max number of recent sales to return. Default 10."}
                    },
                    "required": ["building"]
                }
            },
            {
                "name": "get_owner_portfolio",
                "description": "Get all properties owned by a specific person from lead database.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner_name": {"type": "string", "description": "Owner name"}
                    },
                    "required": ["owner_name"]
                }
            },
            {
                "name": "search_building_names",
                "description": "Find building by partial name. Use ONLY if get_building_intel returns no data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "search_term": {"type": "string", "description": "Partial building name"}
                    },
                    "required": ["search_term"]
                }
            },
            {
                "name": "get_rental_intel",
                "description": "Get rental transaction data, lease expiry information, and rental yield analysis for a building or unit on Palm Jumeirah",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {"type": "string", "description": "Building name"},
                        "bedrooms": {"type": "string", "description": "Bedroom count filter (optional)"},
                        "unit_number": {"type": "string", "description": "Specific unit number (optional)"},
                        "query_type": {
                            "type": "string",
                            "enum": ["expiring_leases", "rental_history", "rental_yield", "unit_status"],
                            "description": "Type of rental query"
                        },
                        "days_ahead": {"type": "integer", "description": "For expiring_leases: how many days ahead to look (default 90)"},
                        "limit": {"type": "integer", "description": "Max results to return (default 50)"}
                    },
                    "required": ["building", "query_type"]
                }
            },
            {
                "name": "find_listings_below_market",
                "description": "Find scraped PropertyFinder listings priced below the typical title-deed market for that building (and optionally bedroom count). Use when the user asks for properties below market, good deals, undervalued, or bargains.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {"type": "string", "description": "Optional building name filter (e.g. Oceana, Shoreline 5)"},
                        "bedrooms": {"type": "integer", "description": "Optional bedroom filter (0=studio, 1, 2, 3)"},
                        "below_pct": {"type": "number", "description": "Minimum discount below market (default 10 = at least 10% below median)"},
                        "limit": {"type": "integer", "description": "Max number of listings to return (default 20)"}
                    },
                    "required": []
                }
            },
            {
                "name": "get_propertyfinder_listings",
                "description": "Query active PropertyFinder scraped listings (rentals or sales). Use when user asks about current listings, available units, furnished/unfurnished rentals, or PropertyFinder data. Returns listing details including price, furnished status, URL, and how many times each unit is listed (pf_listing_count = priority).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {"type": "string", "description": "Building name filter (e.g., 'Ellington Beach House'). Optional."},
                        "listing_type": {"type": "string", "enum": ["rent", "sell", "all"], "description": "Filter by rent or sell. Default 'all'."},
                        "bedrooms": {"type": "integer", "description": "Bedroom count filter (0=studio, 1, 2, 3). Optional."},
                        "furnished": {"type": "string", "enum": ["Furnished", "Unfurnished", "all"], "description": "Filter by furnished status. Default 'all'."},
                        "unit_number": {"type": "string", "description": "Specific unit number. Optional."},
                        "limit": {"type": "integer", "description": "Max results (default 50)."}
                    },
                    "required": []
                }
            },
            {
                "name": "get_bayut_listings",
                "description": "Get active Bayut property listings on Palm Jumeirah. Use when user asks about active listings, motivated sellers/landlords currently on Bayut, competition analysis, how many units are listed, or current market supply. Returns live listing prices, sizes, views, and Bayut URLs.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "listing_type": {"type": "string", "enum": ["all", "sale", "rent"], "description": "Filter by listing type. Default 'all'."},
                        "building": {"type": "string", "description": "Optional building name filter (e.g. 'Shoreline 5', 'Ellington')."},
                        "bedrooms": {"type": "integer", "description": "Optional bedroom count filter (1, 2, 3, 4)."},
                        "min_price": {"type": "number", "description": "Optional minimum price in AED."},
                        "max_price": {"type": "number", "description": "Optional maximum price in AED."},
                        "limit": {"type": "integer", "description": "Max listings to return (default 30)."}
                    },
                    "required": []
                }
            },
            {
                "name": "get_unit_info",
                "description": "Look up confirmed unit specifications from the master unit registry (cross-referenced from leads, sales, and rentals). Returns bedrooms, size, view, floor, and transaction history for a specific unit.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {"type": "string", "description": "Building name (e.g., 'Shoreline 9', 'Fairmont')"},
                        "unit_number": {"type": "string", "description": "Unit number (e.g., '1003', 'S-607')"}
                    },
                    "required": ["building", "unit_number"]
                }
            },
            {
                "name": "open_whatsapp",
                "description": "Launch Chrome with WhatsApp Web so the user can run campaigns. Use when the user says to open WhatsApp, launch WhatsApp, or start WhatsApp Chrome.",
                "input_schema": {"type": "object", "properties": {}, "required": []}
            },
            {
                "name": "start_whatsapp_campaign",
                "description": "Start a WhatsApp outreach campaign. Use when the user asks to start, run, or launch a campaign (e.g. cold owner, landlord lease expiry, recent sale). Prefer dry_run true if they say preview or dry run.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "campaign_type": {
                            "type": "string",
                            "enum": ["landlord_lease_expiry", "cold_owner", "recent_sale", "portfolio_owner", "active_seller", "active_renter"],
                            "description": "landlord_lease_expiry = expiring leases, cold_owner = cold owner outreach, recent_sale = recent sale follow-up, portfolio_owner = dedicated portfolio owners (3+ units), active_seller = PropertyFinder listings (selling), active_renter = PropertyFinder listings (renting)"
                        },
                        "building": {"type": "string", "description": "Optional building filter (e.g. Shoreline 12)"},
                        "bedrooms": {"type": "string", "description": "Optional bedroom filter (All, Studio, 1, 2, 3, 4, 5, 6)"},
                        "days_ahead": {"type": "integer", "description": "Lease/sale window in days (default 90)"},
                        "portfolio_only": {"type": "boolean", "description": "Cold owner only: limit to portfolio investors (2+ units). Default false."},
                        "min_units": {"type": "integer", "description": "Portfolio owner campaign: minimum units per owner (default 3)."},
                        "limit": {"type": "integer", "description": "Optional cap on queue size"},
                        "dry_run": {"type": "boolean", "description": "If true, preview only, no messages sent. Default false unless user asks for preview."},
                        "override_limit": {"type": "boolean", "description": "Skip ramp-up, use full daily cap. Default false."}
                    },
                    "required": ["campaign_type"]
                }
            },
            {
                "name": "match_listing_to_owner",
                "description": (
                    "Match a portal listing (Bayut/PF/Dubizzle) against the owner lead database "
                    "to identify who owns the unit. Use when the agent asks 'who owns the X-bed in "
                    "Shoreline 10 listed at Y', 'find the owner of unit 607 in Ellington', or "
                    "'match this listing'. Returns owner name, phone, and confidence score."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "building": {
                            "type": "string",
                            "description": "Building name as on the portal (e.g. 'Shoreline 10', 'Al Hallawi', 'Tiara Emerald')"
                        },
                        "size_sqft": {
                            "type": "number",
                            "description": "Listing size in sqft (from portal). Optional but strongly improves accuracy."
                        },
                        "bedrooms": {
                            "type": "string",
                            "description": "Bedroom count string: '1', '2', '3', 'Studio', 'PH'. Optional."
                        },
                        "unit_number": {
                            "type": "string",
                            "description": "Exact unit number if visible in listing (e.g. '1101', 'S-607'). Optional."
                        }
                    },
                    "required": ["building"]
                }
            },
            {
                "name": "validate_trakheesi_listing",
                "description": (
                    "Resolve a Trakheesi/Madmoun listing GUID to verified property details "
                    "(building, zone, size, beds, agency, permit number, status) via the DLD API, "
                    "then auto-cross-reference with the lead database to find the owner's name "
                    "and phone number. Use when the user provides a Madmoun GUID, a Trakheesi URL, "
                    "or asks to look up a specific DLD listing. Free (uses Playwright browser). Takes ~20s."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "guid_or_url": {
                            "type": "string",
                            "description": (
                                "The Madmoun GUID string (e.g. 'gc2hzdo7t8plgx47pfisx1h5mhuf3wfsbw3kujydscuhchrrn') "
                                "or full Trakheesi validation URL (https://trakheesi.dubailand.gov.ae/…?khevJujtDig=…)"
                            )
                        }
                    },
                    "required": ["guid_or_url"]
                }
            }
        ]

        # ── Live database stats for dynamic system prompt ─────────────────────
        _bayut_df = load_bayut_listings()
        _bayut_total = len(_bayut_df) if not _bayut_df.empty else 0
        _bayut_sale  = int((_bayut_df["listing_type"].str.lower() == "sale").sum()) if not _bayut_df.empty else 0
        _bayut_rent  = int((_bayut_df["listing_type"].str.lower() == "rent").sum()) if not _bayut_df.empty else 0
        _bayut_bldgs = _bayut_df["building_name"].nunique() if not _bayut_df.empty else 0
        _bayut_date  = str(_bayut_df["scraped_at"].dropna().max())[:10] if not _bayut_df.empty and "scraped_at" in _bayut_df.columns else "unknown"
        _total_leads = len(leads_df) if not leads_df.empty else 0
        _leads_phone = int((leads_df["phone"].fillna("").str.strip() != "").sum()) if not leads_df.empty and "phone" in leads_df.columns else 0
        _leads_bldgs = leads_df["building_name"].nunique() if not leads_df.empty and "building_name" in leads_df.columns else 0
        _ref_count   = len(reference_df) if reference_df is not None and not reference_df.empty else 0

        system_prompt = f"""You are HLM, a real estate intelligence system for Palm Jumeirah, Dubai. You help a broker find owners to call, analyse market pricing, and identify leads.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATABASE SNAPSHOT (live)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lead Database:     {_total_leads:,} owner records | {_leads_phone:,} with phone numbers | {_leads_bldgs} buildings (DLD 2018–2025)
Title Deeds:       {_ref_count:,} sales transactions (Property Monitor — official government source)
Unit Registry:     30,000+ units cross-referenced from 5 sources across 189 buildings
                   Confirmed bedrooms, sizes, views, floor levels with HIGH/MEDIUM/INFERRED confidence
Active Bayut:      {_bayut_total:,} listings ({_bayut_sale} for sale, {_bayut_rent} for rent, {_bayut_bldgs} buildings) — updated {_bayut_date}
PropertyFinder:    Scraped sale/rent listings merged into lead database (with owner contacts where matched)
Rental Contracts:  Ejari data (last 3 years) — lease dates, yields, turnover history

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS — PICK THE RIGHT ONE IMMEDIATELY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
get_building_intel         → Market prices (title deeds) + owner contacts for a building
get_rental_intel           → Rental yields, expiring leases, tenant turnover history
get_bayut_listings         → Active Bayut listings — who is currently selling/renting, supply analysis
get_propertyfinder_listings→ Active PF listings with owner contacts (pf_listing_count = motivation)
find_listings_below_market → Listings priced below title deed market (deals / undervalued)
get_unit_info              → Confirmed specs for a specific unit (beds, size, view, floor)
get_owner_portfolio        → All properties owned by one person
search_building_names      → Fuzzy search if building name is unclear
start_whatsapp_campaign    → Send WhatsApp messages to a filtered owner list
open_whatsapp              → Open WhatsApp Web in Chrome

RULE: Use exactly 1 tool per response turn. Do not chain tool calls unless the first returns no data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA SOURCES — WHAT EACH CONTAINS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITLE DEEDS (Property Monitor — highest reliability)
  ✓ Sale prices, dates, sizes, bedroom counts, building names
  ✕ NO unit numbers in CSV exports (government security measure)
  ✕ NO owner phone numbers
  → Use for: Pricing analysis, transaction volumes, market trends

LEAD DATABASE (DLD consolidated — 2018–2025)
  ✓ Unit numbers, owner names, phone numbers, building names
  ✕ Contacts may be 1–2 years old (owner may have sold)
  → Use for: Who to call, portfolio analysis

UNIT REGISTRY (cross-referenced from 5 sources)
  ✓ Confirmed bedrooms, sizes, views, floor levels
  ✓ Last sale price + date, last rental price
  → Use get_unit_info for any specific unit lookup

BAYUT LISTINGS (scraped — updated {_bayut_date})
  ✓ Active listings with price, size, beds, view, Bayut URL
  ✓ Identifies motivated sellers/landlords currently marketing
  → Use get_bayut_listings to query

PROPERTYFINDER LISTINGS (scraped + merged with owners)
  ✓ listing_type (rent/sell), price, furnished status, URL
  ✓ pf_listing_count: 5+ = very motivated owner
  → Use get_propertyfinder_listings

RENTAL CONTRACTS (Ejari — last 3 years)
  ✓ Lease start/end, annual rent, unit details, furnished
  ✓ rent_recurrence: "Renewal" = same tenant / "New Contract" = new tenant
  → Use get_rental_intel

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL LIMITATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Property Monitor title deed exports DO NOT include unit numbers. We CANNOT directly match a recent sale to a current owner. Title deed data and owner contact data are SEPARATE — always present them as two distinct sections.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILDING NAME HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fuzzy matching is built in. Examples:
- "Shoreline 9" / "Al Masalli" → Al Masalli (Tower 9)
- "Fairmont" → The Fairmont Palm Residences
- "The 8" → The Crescent (matched via unit numbers)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNIT NUMBER SCHEMAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MARINA (1–6)  Format: [floor][unit][letter] e.g. "0401D"
  A=3BR(3,979sqft) B=3BR(2,199sqft) C=2BR(1,621sqft) D=2BR(1,680sqft)
  F=4BR(6,753sqft) G=4BR(5,973sqft) H=5BR(9,555sqft)
  Views: units 01-03=Palm lagoon side | units 05-07=Arabian Gulf side

PALM TOWER  Format: [floor][unit] e.g. "3406"
  Studio≈446-525sqft | 1BR≈900-951sqft | 2BR≈1,842-2,118sqft | 3BR≈2,589sqft

SHORELINE (1–20)  Format: [floor][unit] e.g. "607"=Floor6 Unit07
  1=Al Ramth, 2=Al Nabat, 3=Al Sultana, 4=Al Tamr, 5=Al Jeer,
  6=Al Shahla, 7=Al Khudrawi, 8=Al Sarrood, 9=Al Msalli,
  10=Al Dabas, 11=Al Habool, 12=Al Haseer, 13=Al Ameera,
  14=Al Hallawi, 15=Al Das, 16=Al Khushkar, 17=Al Hamri,
  18=Al Safeena, 19=Al Basri, 20=Al Ghozlan

ELLINGTON BEACH HOUSE  Format: [Tower]-[Floor][Unit] e.g. "N-604"
  N=North Tower (sea view) | S=South Tower (garden/inland view)
  G=ground floor (G01, G02…). No studios — 1BR, 2BR, 3BR only.

AZURE RESIDENCES  Blocks A, B, C, D. e.g. "Block D, Unit 703"=Block D Floor7 Unit03
OCEANA  Sub-buildings: Adriatic, Aegean, Atlantic, Caribbean, Pacific, Baltic, Southern, Ruby, Luce, Emerald, Diamond, Tanzanite, Aquamarine
FRONDS  Letters A-P = individual fronds. Units = villa numbers on frond.
CANAL COVES  E=East, W=West
PALM VIEWS  E=East tower, W=West tower

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRICING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Default to LAST 6 MONTHS for averages/PSF unless user specifies otherwise
- Label timeframe clearly: "6-Month Avg: AED X.XXM | AED X,XXX/sqft"
- <3 transactions in 6 months → expand to 12 months and note it
- Gross Rental Yield = (Annual Rent / Purchase Price) × 100
- Typical Palm Jumeirah yields: 5–8% for apartments

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMATTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Owner tables — column order: Unit | Owner | Phone | Beds | Size | Date
- Show ALL phone numbers for every contact (if "phone" contains " | " those are multiple numbers — show all)
- Flag portfolio investors (2+ units) prominently
- Sort by unit number ascending by default
- Lead contacts may be previous owners if unit sold recently — note once at bottom

Lease intelligence:
- "Renewal" = same tenant renewed → stable, less likely to sell
- "New Contract" = new tenant → higher turnover, owner may be tired, open to selling
- Expiring in 1–3 months = HOT lead

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARD RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER suggest "contact DLD" — the broker does not do this
- NEVER invent contacts, prices, phone numbers, or unit numbers
- If no contact found: say "No contact" — do not suggest alternatives
- No filler text, no unnecessary commentary
- WhatsApp campaigns: if user says "preview" or "dry run" → set dry_run=true
  Campaign types: landlord_lease_expiry | cold_owner | recent_sale | portfolio_owner | active_seller | active_renter"""
        
        if chat_history and len(chat_history) > 1:
            messages = chat_history[:-1].copy()
            messages.append({"role": "user", "content": user_query})
        else:
            messages = [{"role": "user", "content": user_query}]
        
        # Initial API call
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            tools=tools,
            messages=messages,
            timeout=30.0
        )
        
        # Tool execution with strict limits
        MAX_TOOLS = 3
        tool_count = 0
        start_time = time.time()
        
        while response.stop_reason == "tool_use" and tool_count < MAX_TOOLS:
            if time.time() - start_time > 25:  # 25 second timeout
                break
            
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break
            
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for block in tool_use_blocks:
                tool_name = block.name
                tool_input = block.input
                tool_count += 1
                try:
                    if tool_name == "get_building_intel":
                        result = get_complete_building_intel_for_ai(
                            reference_df=reference_df,
                            leads_df=leads_df,
                            building=tool_input.get('building', ''),
                            bedrooms=tool_input.get('bedrooms'),
                            matched_only=tool_input.get('matched_only', False),
                            limit=tool_input.get('limit', 10)
                        )
                    elif tool_name == "get_owner_portfolio":
                        result = get_portfolio_summary_for_ai(leads_df, **tool_input)
                    elif tool_name == "search_building_names":
                        result = search_building_names_for_ai(reference_df, tool_input.get('search_term', ''))
                    elif tool_name == "get_rental_intel":
                        # Load rental data for this query
                        rental_df = load_rentals()
                        result = get_rental_intel_for_ai(
                            rental_df=rental_df,
                            leads_df=leads_df,
                            reference_df=reference_df,
                            building=tool_input.get('building', ''),
                            query_type=tool_input.get('query_type', 'expiring_leases'),
                            bedrooms=tool_input.get('bedrooms'),
                            unit_number=tool_input.get('unit_number'),
                            days_ahead=tool_input.get('days_ahead', 90),
                            limit=tool_input.get('limit', 50)
                        )
                    elif tool_name == "get_unit_info":
                        from unit_registry import get_unit_info
                        building = tool_input.get('building', '')
                        unit = tool_input.get('unit_number', '')
                        info = get_unit_info(building, unit)
                        if info:
                            result = {
                                "found": True,
                                "building": info["building_name"],
                                "unit": info["unit_number"],
                                "bedrooms": info["bedrooms"],
                                "size_sqft": info["size_sqft"],
                                "floor": info["floor_level"],
                                "view": info["view"] or "Not available",
                                "position": info["unit_position"],
                                "confidence": info["confidence"],
                                "sources": info["sources"],
                                "transaction_history": {
                                    "sale_count": info["sale_count"],
                                    "rental_count": info["rental_count"],
                                    "last_sale_price": info["last_sale_price"],
                                    "last_sale_date": info["last_sale_date"],
                                    "last_annual_rent": info["last_annual_rent"]
                                }
                            }
                        else:
                            result = {"found": False, "message": f"Unit not found in registry: {building} {unit}"}
                    elif tool_name == "find_listings_below_market":
                        result = get_listings_below_market_for_ai(
                            leads_df=leads_df,
                            reference_df=reference_df,
                            building=tool_input.get('building') or None,
                            bedrooms=tool_input.get('bedrooms'),
                            below_pct=float(tool_input.get('below_pct', 10)),
                            limit=int(tool_input.get('limit', 20))
                        )
                    elif tool_name == "get_propertyfinder_listings":
                        result = get_propertyfinder_listings_for_ai(
                            leads_df,
                            building=tool_input.get("building"),
                            listing_type=tool_input.get("listing_type", "all"),
                            bedrooms=tool_input.get("bedrooms"),
                            furnished=tool_input.get("furnished", "all"),
                            unit_number=tool_input.get("unit_number"),
                            limit=tool_input.get("limit", 50)
                        )
                    elif tool_name == "get_bayut_listings":
                        result = get_bayut_listings_for_ai(
                            listing_type=tool_input.get("listing_type", "all"),
                            building=tool_input.get("building"),
                            bedrooms=tool_input.get("bedrooms"),
                            min_price=tool_input.get("min_price"),
                            max_price=tool_input.get("max_price"),
                            limit=int(tool_input.get("limit", 30))
                        )
                    elif tool_name == "open_whatsapp":
                        root = Path(__file__).resolve().parent
                        ps1 = root / "whatsapp_bot" / "start_whatsapp_chrome.ps1"
                        if not ps1.exists():
                            result = {"error": "WhatsApp launcher script not found."}
                        else:
                            subprocess.Popen(
                                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                                cwd=str(root),
                            )
                            result = {"status": "ok", "message": "Chrome with WhatsApp Web is launching. Log in if needed, then you can start a campaign."}
                    elif tool_name == "start_whatsapp_campaign":
                        root = Path(__file__).resolve().parent
                        cmd = [
                            sys.executable,
                            str(root / "whatsapp_bot" / "run_campaign.py"),
                            "--type", tool_input.get("campaign_type", "cold_owner"),
                            "--days", str(tool_input.get("days_ahead", 90)),
                        ]
                        if tool_input.get("building"):
                            cmd.extend(["--building", tool_input["building"]])
                        if tool_input.get("bedrooms") and tool_input["bedrooms"] != "All":
                            cmd.extend(["--bedrooms", tool_input["bedrooms"]])
                        if tool_input.get("portfolio_only"):
                            cmd.append("--portfolio-only")
                        if tool_input.get("campaign_type") == "portfolio_owner" and tool_input.get("min_units", 3) != 3:
                            cmd.extend(["--min-units", str(tool_input["min_units"])])
                        if tool_input.get("limit"):
                            cmd.extend(["--limit", str(tool_input["limit"])])
                        if tool_input.get("dry_run"):
                            cmd.append("--dry-run")
                        if tool_input.get("override_limit"):
                            cmd.append("--override-limit")
                        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                        cwd_wa = str(root / "whatsapp_bot")
                        if sys.platform == "win32":
                            subprocess.Popen(
                                ["cmd", "/k", sys.executable] + cmd[1:],
                                cwd=cwd_wa,
                                creationflags=flags,
                            )
                        else:
                            subprocess.Popen(cmd, cwd=cwd_wa, creationflags=flags)
                        result = {"status": "started", "message": "Campaign started in a new window. Watch that window for progress."}
                    elif tool_name == "match_listing_to_owner":
                        try:
                            from listing_matcher.matcher import match_listing_tool, load_leads_df as _load_leads
                            _matcher_leads = _load_leads()
                            result = match_listing_tool(
                                building=tool_input.get("building", ""),
                                size_sqft=tool_input.get("size_sqft"),
                                bedrooms=tool_input.get("bedrooms"),
                                unit_number=tool_input.get("unit_number"),
                                leads_df=_matcher_leads,
                            )
                        except Exception as _e:
                            result = {"error": f"Matcher error: {_e}"}
                    elif tool_name == "validate_trakheesi_listing":
                        try:
                            from scraper.dld_validator import (
                                validate_listing as _dld_validate,
                                extract_guid_from_url as _dld_extract_guid,
                            )
                            from listing_matcher.matcher import (
                                match_listing_tool as _match_tool,
                                load_leads_df as _load_leads_dld,
                            )

                            _raw = tool_input.get("guid_or_url", "").strip()
                            _guid = _dld_extract_guid(_raw) or _raw
                            _dld_res = _dld_validate(_guid)

                            if not _dld_res["success"]:
                                result = (
                                    f"✕ DLD lookup failed: {_dld_res['error']}\n\n"
                                    "Tips:\n"
                                    "- Verify the GUID came from a Madmoun QR code\n"
                                    "- Try again — browser automation can occasionally fail\n"
                                    "- The GUID may be invalid or expired"
                                )
                            else:
                                _start = _dld_res["permit_start"][:10] if _dld_res["permit_start"] else "N/A"
                                _end   = _dld_res["permit_end"][:10]   if _dld_res["permit_end"]   else "N/A"
                                _display_bld = _get_shoreline_display_name(_dld_res["building"])
                                _out = (
                                    f"✓ PROPERTY DETAILS (from DLD Trakheesi)\n"
                                    f"Building: {_display_bld} ({_dld_res['building_ar']})\n"
                                    f"Zone: {_dld_res['zone']}\n"
                                    f"Size: {_dld_res['size_sqm']} sqm / {_dld_res['size_sqft']:,.0f} sqft\n"
                                    f"Bedrooms: {_dld_res['beds']}\n"
                                    f"Floor: {_dld_res['floor'] or 'N/A'}\n"
                                    f"Value: AED {_dld_res['value']:,.0f}\n"
                                    f"Type: {_dld_res['permit_type']}\n"
                                    f"Agency: {_dld_res['agency']}\n"
                                    f"Permit: {_dld_res['permit_number']}\n"
                                    f"Status: {_dld_res['permit_status']}\n"
                                    f"Valid: {_start} → {_end}\n"
                                )
                                _beds_clean = _clean_beds_from_dld(_dld_res["beds"])
                                try:
                                    _leads = _load_leads_dld()
                                    _owner_text = _match_tool(
                                        building=_dld_res["building"],
                                        size_sqft=_dld_res["size_sqft"] or None,
                                        bedrooms=_beds_clean,
                                        leads_df=_leads,
                                    )
                                    _out += f"\n OWNER MATCH (lead database):\n{_owner_text}"
                                except Exception as _me:
                                    _out += f"\n⚠ Owner lookup failed: {_me}"
                                result = _out
                        except Exception as _e:
                            result = {"error": f"DLD validator error: {_e}"}
                    else:
                        result = {"error": f"Unknown tool: {tool_name}"}
                except Exception as e:
                    result = {"error": str(e)}
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str)
                })
            
            messages.append({"role": "user", "content": tool_results})
            
            # After 2 tools, force text response
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=system_prompt,
                tools=tools if tool_count < 2 else [],
                messages=messages,
                timeout=30.0
            )
        
        # Force final response if still using tools
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if tool_use_blocks:
                messages.append({"role": "assistant", "content": response.content})
                tool_results = [{
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps({"status": "Limit reached - respond with data gathered"})
                } for b in tool_use_blocks]
                messages.append({"role": "user", "content": tool_results})
                
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8192,
                    system=system_prompt,
                    tools=[],
                    messages=messages,
                    timeout=30.0
                )
        
        # Extract response
        final_text = next((b.text for b in response.content if hasattr(b, "text")), None)
        ai_logger.info(f"AI Response generated ({len(final_text or '')} chars)")
        return final_text or "Could not generate response. Please try rephrasing."
        
    except anthropic.APIError as e:
        error_str = str(e).lower()
        if "rate_limit" in error_str or "429" in error_str:
            ai_logger.warning(f"Rate limit hit: {e}")
            return """⏳ **Rate Limit Reached**

The AI system is currently at capacity. Please:
- Wait 1-2 minutes before trying again
- Use simpler queries to reduce processing time
- Contact admin if this persists

This protects against excessive API usage."""
        if "authentication" in error_str or "401" in error_str:
            ai_logger.error(f"Authentication failed: {e}")
            return """ **API Authentication Error**

The API key is invalid or expired. Please contact the system administrator.

Technical details: Invalid Anthropic API key"""
        if "timeout" in error_str or "504" in error_str:
            ai_logger.warning(f"Timeout: {e}")
            return """⏱ **Request Timeout**

The query took too long to process. Please try:
- A simpler query
- Breaking your request into smaller parts
- Trying again in a moment"""
        if "invalid" in error_str or "400" in error_str:
            ai_logger.error(f"Invalid request: {e}")
            return """✕ **Invalid Request**

Your query could not be processed. Please try rephrasing it or contact support.

Technical details: Malformed API request"""
        ai_logger.error(f"Unexpected API error: {e}", exc_info=True)
        return f"""✕ **API Error**

An unexpected error occurred: {type(e).__name__}

Please try again. If this persists, contact support."""
    except ImportError:
        return "✕ **anthropic package not installed**\n\nRun: `pip install anthropic`"
    except Exception as e:
        ai_logger.error(f"Unexpected error during AI query: {e}", exc_info=True)
        return f"""✕ **System Error**

An unexpected error occurred: {type(e).__name__}: {str(e)}

Please try again or contact support if this persists."""


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD SEARCH PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_lead_search_page():
    """Render the main lead search page."""
    apply_global_styles()

    # ── ORVA logo + nav header ─────────────────────────────────────────────────
    logo_col, nav_fu, nav_rent, nav_wa, nav_call, nav_cont, nav_bayut, nav_match, nav_tools, nav_hlm = st.columns(
        [2.2, 1, 1, 1, 1, 1, 1, 1, 1.1, 1]
    )

    with logo_col:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:12px; padding:6px 0;">
            <div style="
                width:40px; height:40px;
                background:linear-gradient(135deg,#10b981,#059669);
                border-radius:10px;
                display:flex; align-items:center; justify-content:center;
                font-weight:900; font-size:20px; color:#0f1117;
                flex-shrink:0;
                box-shadow:0 4px 12px rgba(16,185,129,0.4);
            ">O</div>
            <div>
                <div style="font-size:22px; font-weight:800; color:#f1f5f9; letter-spacing:4px; line-height:1.1;">ORVA</div>
                <div style="font-size:9px; color:#10b981; letter-spacing:2.5px; text-transform:uppercase; opacity:0.9;">Property Intelligence</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with nav_fu:
        pending_count = cdm.get_pending_reminder_count()
        btn_fu = st.button("Follow-Ups", key="followup_button", help="View follow-up reminders", use_container_width=True)
        if pending_count > 0:
            badge_color = "#ef4444"
            st.markdown(f"""
            <div style="position:relative;height:0;overflow:visible;margin-top:-34px;pointer-events:none;z-index:999;">
                <span style="
                    position:absolute;top:4px;right:4px;
                    background:{badge_color};color:white;
                    border-radius:50%;width:17px;height:17px;
                    font-size:10px;font-weight:700;
                    display:inline-flex;align-items:center;justify-content:center;
                    border:2px solid #0f1117;
                ">{pending_count}</span>
            </div>
            """, unsafe_allow_html=True)
        if btn_fu:
            st.session_state.current_page = 'follow_ups'
            st.rerun()

    with nav_rent:
        if st.button("Rentals", key="rentals_button", help="Lease Expiry Dashboard", use_container_width=True):
            st.session_state.current_page = 'lease_expiry'
            st.rerun()

    with nav_wa:
        if st.button("WhatsApp", key="whatsapp_button", help="Campaign Manager", use_container_width=True):
            st.session_state.current_page = 'whatsapp'
            st.rerun()

    with nav_call:
        if st.button("Call Log", key="calllog_button", help="View call log", use_container_width=True):
            st.session_state.current_page = 'call_log'
            st.rerun()

    with nav_cont:
        if st.button("Contacts", key="contacts_button", help="Contact management", use_container_width=True):
            st.session_state.current_page = 'contacts'
            st.rerun()

    with nav_tools:
        with st.popover("Tools  ▾", use_container_width=True):
            st.markdown("**Scrapers & Tools**")
            if st.button("PF Scraper", key="tools_pf_btn", help="PropertyFinder + permit scraper", use_container_width=True):
                st.session_state.current_page = 'pf_scraper'
                st.rerun()
            if st.button("PM Scraper", key="tools_pm_btn", help="Property Monitor scrapers", use_container_width=True):
                st.session_state.current_page = 'property_monitor'
                st.rerun()
            if st.button("Matcher", key="tools_matcher_btn", help="Match listings to owners", use_container_width=True):
                st.session_state.current_page = 'listing_matcher'
                st.rerun()
            st.divider()
            st.caption("Bayut Refresh — Chrome port 9222")
            refresh_type = st.radio("Type", ["Both", "Sale", "Rent"], horizontal=True, key="tools_refresh_type")
            if st.button("Refresh Bayut", key="tools_bayut_refresh_btn", use_container_width=True):
                type_map = {"Both": "both", "Sale": "sale", "Rent": "rent"}
                cmd = [sys.executable, "bayut_scraper/run_palm_listings.py",
                       "--type", type_map[refresh_type], "--max-pages", "3"]
                with st.spinner("Scanning pages 1–3…"):
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                        if result.returncode == 0:
                            st.success("Done — reload to see updates")
                            load_bayut_listings.clear()
                        else:
                            st.error(f"Scraper error: {result.stderr[-300:]}")
                    except subprocess.TimeoutExpired:
                        st.warning("Timed out after 3 min")
                    except Exception as exc:
                        st.error(f"Error: {exc}")
            st.divider()
            if st.button("Reload Data", key="tools_reload_btn", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
            if st.button("System Health", key="tools_health_btn", use_container_width=True):
                st.session_state.current_page = 'health_check'
                st.rerun()

    with nav_bayut:
        if st.button("Bayut", key="bayut_listings_button", help="Active Bayut listings", use_container_width=True):
            st.session_state.current_page = 'bayut_listings'
            st.rerun()

    with nav_match:
        if st.button("Match", key="client_match_button", help="Find owners for your client", use_container_width=True):
            st.session_state.current_page = 'client_match'
            st.rerun()

    with nav_hlm:
        if st.button("HLM", key="hlm_button", help="Open AI Assistant", type="primary", use_container_width=True):
            st.session_state.current_page = 'ai_chat'
            st.rerun()

    # Load data (cache invalidates when PF scraped CSV changes so new scrapes show without restart)
    with st.spinner("Loading data..."):
        df, diag = load_data(_pf_mtime=_pf_csv_mtime(), _pq_mtime=_parquet_mtime())
        rental_df = load_rentals()
    
    if df.empty:
        st.warning("No data loaded. Add CSV/Excel files to ./data folder.")
        return
    
    # Portfolio toggle
    portfolio_mode = st.toggle(" **Large Portfolio Mode**", value=False, key="portfolio_toggle")
    
    # Filters
    filters = render_filters(df, portfolio_mode)
    st.divider()
    
    # Apply filters
    filtered = apply_filters(
        df,
        date_start=filters['date_start'],
        date_end=filters['date_end'],
        owner_name=filters['owner_name'],
        building_search=filters['building_search'],
        bedrooms=filters['bedrooms'],
        unit_number=filters['unit_number'],
        phone=filters['phone'],
        phone_required=filters['phone_required'],
        min_completeness=filters['min_completeness'],
        min_size_sqft=filters['min_size_sqft'],
        max_size_sqft=filters['max_size_sqft'],
        hide_flagged=filters['hide_flagged'],
        source_filter=filters.get('source_filter')
    )
    if filters.get('recently_transacted_only') and filters.get('source_filter', '').lower() == 'propertyfinder':
        st.info("ℹ **Recently transacted only** is ignored when Source = PropertyFinder (scraped listings have no title deed data).")
    if filters.get('recently_transacted_only') and not filtered.empty and filters.get('source_filter', '').lower() != 'propertyfinder':
        ref_df, _ = load_reference_data()
        if ref_df is not None and not ref_df.empty:
            title_deed = filters.get('title_deed_only', True)
            resale = filters.get('resale_only', True)
            since_days = filters.get('recent_transacted_days', 90)
            mask = get_recent_transaction_lead_mask(
                filtered, ref_df, since_days=since_days,
                title_deed_only=title_deed, resale_only=resale
            )
            filtered = filtered[mask]
            details = get_recent_transaction_details(
                filtered, ref_df, since_days=since_days,
                title_deed_only=title_deed, resale_only=resale
            )
            filtered['display_date'] = details['display_date']
            filtered['trans_type'] = details['trans_type']
            filtered['sale_type'] = details['sale_type']
            filtered['sale_price_aed'] = details['sale_price_aed']
            # Lead age warning: flag leads whose original date is >5 years old
            lead_dates = pd.to_datetime(filtered['date'], errors='coerce')
            age_days = (pd.Timestamp.now() - lead_dates).dt.days
            filtered['lead_age_warning'] = age_days.apply(lambda d: "Lead >5yr" if d > 5 * 365 else "")
        else:
            st.warning("Reference data not loaded; \"Recently transacted only\" filter skipped.")
    
    # Display results
    if portfolio_mode:
        portfolio_df = aggregate_portfolios(filtered, min_properties=filters['min_properties'])
        
        if portfolio_df.empty:
            st.info(f"No portfolio owners with {filters['min_properties']}+ properties found.")
        else:
            display_df = format_portfolio_for_display(portfolio_df)
            st.subheader(f" Portfolio Owners ({len(portfolio_df):,})")
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row",
                key="portfolio_table",
            )
            selected_rows = event.selection.rows if event.selection else []
            if selected_rows:
                idx = selected_rows[0]
                row = portfolio_df.iloc[idx]
                owner_name = str(row.get("owner_name", "") or "").strip()
                portfolio_id = cdm.make_client_id(owner_name, "PORTFOLIO", "ALL")
                owner_props = filtered[filtered["owner_name"].fillna("").str.strip() == owner_name]
                st.info(f"**{owner_name}** — {len(owner_props)} properties")
                with st.expander("View all properties", expanded=True):
                    ref_df, _ = load_reference_data()
                    last_sale = get_last_sale_per_units(owner_props, ref_df)
                    rental_statuses = []
                    for _, r in owner_props.iterrows():
                        st_dict = get_unit_rental_status(rental_df, str(r.get("building_name") or ""), str(r.get("unit_number") or ""))
                        rental_statuses.append(st_dict.get("status", "no_rental_data"))
                    props_display = owner_props[["building_name", "unit_number", "bedrooms", "size_sqft", "date", "phone"]].copy()
                    props_display["last_sale_date"] = last_sale["last_sale_date"]
                    props_display["trans_type"] = last_sale["trans_type"]
                    props_display["sale_type"] = last_sale["sale_type"]
                    props_display["likely_sold"] = last_sale["likely_sold"]
                    props_display["rental"] = rental_statuses
                    def fmt_sale_date(x):
                        if pd.isna(x):
                            return ""
                        try:
                            return pd.Timestamp(x).strftime("%Y-%m-%d")
                        except Exception:
                            return ""
                    props_display["Last sale"] = props_display["last_sale_date"].apply(fmt_sale_date)
                    props_display["Status"] = props_display["likely_sold"].map(lambda v: "Likely sold" if v else "No later sale")
                    props_display["Rental"] = props_display["rental"].replace({"active": "Active", "expired": "Expired", "no_rental_history": "No data", "no_rental_data": "No data"})
                    display_cols = ["building_name", "unit_number", "bedrooms", "size_sqft", "date", "phone", "Last sale", "trans_type", "sale_type", "Status", "Rental"]
                    props_display = props_display[display_cols]
                    props_display.columns = ["Building", "Unit", "Beds", "Size (sqft)", "Date", "Phone", "Last sale", "Trans type", "Sale type", "Status", "Rental"]
                    filter_status = st.selectbox("Filter by status", ["All", "Likely sold", "No later sale"], key="portfolio_props_filter")
                    if filter_status == "Likely sold":
                        props_display = props_display[props_display["Status"] == "Likely sold"]
                    elif filter_status == "No later sale":
                        props_display = props_display[props_display["Status"] == "No later sale"]
                    st.dataframe(props_display, use_container_width=True, hide_index=True, height=min(400, 80 + len(props_display) * 22))
                    st.caption("Last sale from title deed data. If after record date, unit may have been sold; if no later sale, may still be owned. Rental status from rental contracts.")
                notes_col, reminder_col = st.columns([3, 2])
                with notes_col:
                    st.subheader("Notes")
                    new_note_text = st.text_area("Write a note...", placeholder="e.g. Portfolio owner, interested in bulk deal...", key="portfolio_note_input", height=80)
                    if st.button("Save Note", key="portfolio_save_note_btn"):
                        if new_note_text and new_note_text.strip():
                            cdm.add_note(portfolio_id, new_note_text.strip())
                            st.rerun()
                    notes = cdm.get_notes(portfolio_id)
                    if notes:
                        st.markdown("---")
                        for note in notes:
                            nid = note["id"]
                            ts = note.get("timestamp", "")[:19].replace("T", " ")
                            st.markdown(f"**{ts}**")
                            st.markdown(f"> {note['text']}")
                            if st.session_state.get(f"portfolio_edit_note_{nid}", False):
                                et = st.text_area("Edit:", value=note["text"], key=f"portfolio_edit_text_{nid}", height=60)
                                if st.button("Save", key=f"portfolio_save_edit_{nid}"):
                                    cdm.edit_note(portfolio_id, nid, et.strip())
                                    st.session_state[f"portfolio_edit_note_{nid}"] = False
                                    st.rerun()
                                if st.button("Cancel", key=f"portfolio_cancel_edit_{nid}"):
                                    st.session_state[f"portfolio_edit_note_{nid}"] = False
                                    st.rerun()
                            else:
                                if st.button("Edit", key=f"portfolio_edit_btn_{nid}"):
                                    st.session_state[f"portfolio_edit_note_{nid}"] = True
                                    st.rerun()
                            st.markdown("---")
                with reminder_col:
                    st.subheader("Reminders")
                    with st.expander("New reminder", expanded=False):
                        rem_date = st.text_input("Date & time", placeholder="e.g. 15/02/2026, 3pm", key="portfolio_reminder_dt")
                        rem_note = st.text_input("Reason", placeholder="e.g. Follow up call", key="portfolio_reminder_note")
                        if st.button("Save reminder", key="portfolio_save_rem_btn"):
                            parsed = cdm.parse_reminder_datetime(rem_date)
                            if parsed and rem_note and rem_note.strip():
                                cdm.add_reminder(portfolio_id, owner_name, "", "", row.get("phones", [""])[0] if row.get("phones") else "", parsed, rem_note.strip())
                                st.rerun()
                            elif not parsed:
                                st.error("Enter a valid date.")
                            else:
                                st.warning("Add a reason.")
                    client_reminders = cdm.get_reminders_for_client(portfolio_id)
                    if client_reminders:
                        st.caption("Upcoming:")
                        for rem in client_reminders:
                            rem_id = rem["id"]
                            try:
                                rem_dt = datetime.fromisoformat(rem["datetime"])
                                dt_str = rem_dt.strftime('%d/%m/%Y %H:%M')
                            except Exception:
                                rem_dt = None
                                dt_str = rem.get('datetime', '?')
                            is_editing = st.session_state.get('editing_reminder_id') == rem_id
                            if is_editing and rem.get('status') == 'pending':
                                new_dt_str = st.text_input("Date & time", value=dt_str, placeholder="e.g. 15/02/2026, 3pm", key=f"portfolio_edit_dt_{rem_id}")
                                new_note = st.text_input("Reason", value=rem.get('note') or '', key=f"portfolio_edit_note_{rem_id}")
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("Save", key=f"portfolio_edit_save_{rem_id}"):
                                        parsed = cdm.parse_reminder_datetime((new_dt_str or "").strip())
                                        if parsed:
                                            cdm.update_reminder(rem_id, reminder_dt=parsed, note=(new_note or "").strip() or "")
                                            st.session_state.pop('editing_reminder_id', None)
                                            st.rerun()
                                        else:
                                            st.error("Enter a valid date.")
                                with c2:
                                    if st.button("Cancel", key=f"portfolio_edit_cancel_{rem_id}"):
                                        st.session_state.pop('editing_reminder_id', None)
                                        st.rerun()
                            else:
                                st.markdown(f" {dt_str} — {rem.get('note', '')}")
                                if rem.get('status') == 'pending':
                                    if st.button(" Edit date", key=f"portfolio_edit_btn_{rem_id}"):
                                        st.session_state['editing_reminder_id'] = rem_id
                                        st.rerun()
                phone_for_call = (row.get("phones") or [""])[0] if row.get("phones") else ""
                if st.button("Log call", key="portfolio_log_call_btn"):
                    st.session_state.portfolio_log_call_expanded = True
                    st.rerun()
                if st.session_state.get("portfolio_log_call_expanded", False):
                    with st.expander("Log call", expanded=True):
                        outcome = st.radio("Outcome", options=list(cdm.CALL_OUTCOMES), format_func=lambda x: x.replace("_", " ").title(), key="portfolio_call_outcome", horizontal=True)
                        call_notes = st.text_input("Notes", key="portfolio_call_notes")
                        show_rem = outcome in ("voicemail", "no_answer", "callback")
                        rem_dt_str = None
                        rem_note_str = None
                        if show_rem:
                            rem_dt_str = st.text_input("Follow-up date", placeholder="e.g. 15/02/2026, 3pm", key="portfolio_call_rem_dt")
                            rem_note_str = st.text_input("Reminder reason", key="portfolio_call_rem_note")
                        if st.button("Save call", key="portfolio_call_save"):
                            rem_dt = cdm.parse_reminder_datetime((rem_dt_str or "").strip()) if show_rem and (rem_dt_str or "").strip() else None
                            cdm.log_call(portfolio_id, owner_name, "", "", phone_for_call, outcome, call_notes or "", rem_dt, ((rem_note_str or "").strip() or None) if show_rem else None)
                            st.session_state.portfolio_log_call_expanded = False
                            st.rerun()
                        if st.button("Cancel", key="portfolio_call_cancel"):
                            st.session_state.portfolio_log_call_expanded = False
                            st.rerun()
            csv_data = export_to_csv(display_df)
            st.download_button("↓ Download Portfolios CSV", data=csv_data,
                             file_name="palm_jumeirah_portfolios.csv", mime="text/csv")
    else:
        if filtered.empty:
            st.info("No leads match the current filters.")
        else:
            st.subheader(f" Results ({len(filtered):,} leads)")
            
            sort_col1, sort_col2 = st.columns([1, 5])
            with sort_col1:
                sort_order = st.selectbox("Sort by Date", ["Newest First", "Oldest First"], index=0)
            
            sort_col = 'display_date' if 'display_date' in filtered.columns else 'date'
            if sort_col in filtered.columns:
                ascending = (sort_order == "Oldest First")
                filtered = filtered.sort_values(sort_col, ascending=ascending, na_position='last')
                filtered = filtered.reset_index(drop=True)
            
            # Add rental status indicators (vectorized)
            if not rental_df.empty:
                def add_rental_indicators_vectorized(leads_df, rentals_df):
                    """Vectorized rental status calculation."""
                    today = pd.Timestamp.now()
                    rentals_work = rentals_df.copy()
                    leads_df = leads_df.copy()
                    leads_df['_match_key'] = (
                        leads_df['building_name'].fillna('').str.lower().str.strip() + '|' +
                        leads_df['unit_number'].fillna('').astype(str).str.lower().str.strip()
                    )
                    rentals_work['_match_key'] = (
                        rentals_work['building_name'].fillna('').str.lower().str.strip() + '|' +
                        rentals_work['unit_number'].fillna('').astype(str).str.lower().str.strip()
                    )
                    latest_rentals = (
                        rentals_work
                        .sort_values('contract_end', ascending=False)
                        .groupby('_match_key', as_index=False)
                        .first()
                    )
                    latest_rentals['days_remaining'] = (
                        (latest_rentals['contract_end'] - today).dt.days
                    )
                    def get_indicator(row):
                        if pd.isna(row['contract_end']):
                            return '⚪'
                        if row['contract_end'] > today:
                            return '🟡' if row['days_remaining'] <= 90 else '🟢'
                        return '🔴'
                    latest_rentals['indicator'] = latest_rentals.apply(get_indicator, axis=1)
                    status_map = dict(zip(latest_rentals['_match_key'], latest_rentals['indicator']))
                    leads_df['Rental'] = leads_df['_match_key'].map(status_map).fillna('⚪')
                    leads_df.drop(columns=['_match_key'], inplace=True)
                    return leads_df
                filtered = add_rental_indicators_vectorized(filtered, rental_df)
            
            # Pagination (250 leads per page)
            LEADS_PER_PAGE = 250
            total_leads = len(filtered)
            total_pages = max(1, (total_leads + LEADS_PER_PAGE - 1) // LEADS_PER_PAGE)
            if 'current_page_leads' not in st.session_state:
                st.session_state.current_page_leads = 1
            current_page = max(1, min(st.session_state.current_page_leads, total_pages))
            page_col1, page_col2, page_col3 = st.columns([1, 3, 1])
            with page_col2:
                current_page = st.number_input(
                    f"Page (of {total_pages})",
                    min_value=1,
                    max_value=max(1, total_pages),
                    value=current_page,
                    step=1,
                    key="page_selector"
                )
            st.session_state.current_page_leads = current_page
            start_idx = (current_page - 1) * LEADS_PER_PAGE
            end_idx = min(start_idx + LEADS_PER_PAGE, total_leads)
            filtered_page = filtered.iloc[start_idx:end_idx]
            
            date_col = 'display_date' if filters.get('recently_transacted_only') and 'display_date' in filtered.columns else None
            display_df = format_for_display(filtered_page, date_column=date_col)
            called_ids = cdm.get_all_called_client_ids()
            called_flags = filtered_page.apply(
                lambda r: "✓" if cdm.make_client_id(r.get("owner_name"), r.get("building_name"), r.get("unit_number")) in called_ids else "",
                axis=1,
            )
            display_df["Called"] = called_flags.values

            # Stats (full filtered set)
            with_size = filtered['size_sqft'].notna().sum()
            with_beds = filtered['bedrooms'].notna().sum()
            with_phone = (filtered['phone'].fillna('').str.strip() != '').sum()
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Leads Found", f"{total_leads:,} (pg {current_page}/{total_pages})")
            col2.metric("With Phone", f"{with_phone:,}")
            col3.metric("With Beds", f"{with_beds:,}")
            col4.metric("With Size", f"{with_size:,}")
            
            # Rental status legend
            if 'Rental' in filtered.columns and not rental_df.empty:
                st.caption("**Rental Status:** 🟢 Active rental | 🟡 Lease expiring <90 days | 🔴 Expired/vacant | ⚪ No rental data")
            
            # Dataframe with checkbox row selection
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row",
                key="lead_table"
            )
            
            # Show "View Profile" button when a row is selected
            selected_rows = event.selection.rows if event.selection else []
            if selected_rows:
                idx = selected_rows[0]
                row = filtered_page.iloc[idx]
                sel_name = str(row.get('owner_name', '') or 'Unknown')
                sel_building = str(row.get('building_name', '') or '')
                sel_unit = str(row.get('unit_number', '') or '')
                
                st.info(f"Selected: **{sel_name}** — {sel_building}, Unit {sel_unit}")
                btn_col1, btn_col2, btn_col3 = st.columns(3)
                with btn_col1:
                    if st.button(" View Client Profile", key="open_profile_btn", type="primary", use_container_width=True):
                        st.session_state.selected_client = {
                            'owner_name': str(row.get('owner_name', '') or ''),
                            'building_name': str(row.get('building_name', '') or ''),
                            'unit_number': str(row.get('unit_number', '') or ''),
                            'phone': str(row.get('phone', '') or ''),
                            'bedrooms': row.get('bedrooms'),
                            'size_sqft': row.get('size_sqft'),
                            'size_sqm': row.get('size_sqm'),
                            'date': str(row.get('date', '') or ''),
                            'completeness': row.get('completeness', ''),
                            'data_quality': str(row.get('data_quality', '') or ''),
                        }
                        st.session_state.profile_return_page = 'lead_search'
                        st.session_state.current_page = 'client_profile'
                        st.rerun()
                with btn_col2:
                    if st.button(" Log Call", key="log_call_btn", use_container_width=True):
                        st.session_state.log_call_expanded = True
                        st.rerun()
                with btn_col3:
                    if st.button(" Create Contact", key="create_contact_from_lead_btn", use_container_width=True):
                        st.session_state.create_contact_from_lead = {
                            "owner_name": str(row.get("owner_name", "") or ""),
                            "phone": str(row.get("phone", "") or ""),
                            "email": str(row.get("email", "") or ""),
                            "building_name": str(row.get("building_name", "") or ""),
                            "unit_number": str(row.get("unit_number", "") or ""),
                            "bedrooms": str(row.get("bedrooms", "")) if row.get("bedrooms") is not None else None,
                            "lead_id": int(row["id"]) if row.get("id") is not None and str(row.get("id")).isdigit() else None,
                        }
                        st.session_state.contacts_subpage = "create"
                        st.session_state.current_page = "contacts"
                        st.rerun()

                # ── Active Bayut listings for this building ──────────────────
                bayut_df = load_bayut_listings()
                if not bayut_df.empty and sel_building:
                    bkey = sel_building.lower().replace(" ", "").replace("-", "")
                    bmatches = bayut_df[bayut_df["_building_key"] == bkey]
                    if not bmatches.empty:
                        with st.expander(
                            f" {len(bmatches)} Active Bayut Listing{'s' if len(bmatches) != 1 else ''} — {sel_building}",
                            expanded=True,
                        ):
                            for _, bl in bmatches.iterrows():
                                beds_label = f"{int(bl['bedrooms'])}BR" if pd.notna(bl.get("bedrooms")) else "?"
                                baths_label = f"{int(bl['bathrooms'])}BA" if pd.notna(bl.get("bathrooms")) else ""
                                size_label = f"{int(bl['size_sqft']):,} sqft" if pd.notna(bl.get("size_sqft")) else ""
                                price_label = f"AED {int(bl['price_aed']):,}" if pd.notna(bl.get("price_aed")) else ""
                                view_label = f" · {bl['view']}" if pd.notna(bl.get("view")) and bl["view"] else ""
                                ltype = str(bl.get("listing_type", "")).upper()
                                url = bl.get("listing_url", "")
                                title = bl.get("listing_title", "")
                                parts = [p for p in [beds_label, baths_label, size_label, price_label] if p]
                                summary = " · ".join(parts) + view_label
                                if url and pd.notna(url):
                                    st.markdown(f"**[{ltype}]** {summary} — [{title[:60]}]({url})")
                                else:
                                    st.markdown(f"**[{ltype}]** {summary} — {title[:60]}")
                            st.caption(f"Scraped: {bmatches['scraped_at'].iloc[0][:10] if 'scraped_at' in bmatches.columns else 'unknown'}")

                # Inline call log form (expander when "Log Call" was clicked)
                if st.session_state.get("log_call_expanded", False):
                    with st.expander(" Log call", expanded=True):
                        outcome = st.radio(
                            "Outcome",
                            options=["voicemail", "no_answer", "not_interested", "interested", "callback"],
                            format_func=lambda x: x.replace("_", " ").title(),
                            key="log_call_outcome",
                            horizontal=True,
                        )
                        call_notes = st.text_input("Notes", placeholder="Quick note...", key="log_call_notes")
                        show_reminder = outcome in ("voicemail", "no_answer", "callback")
                        reminder_dt_str = None
                        reminder_note = None
                        if show_reminder:
                            rem_col1, rem_col2 = st.columns(2)
                            with rem_col1:
                                reminder_dt_str = st.text_input(
                                    "Follow-up date & time",
                                    placeholder="e.g. 15/02/2026, 3pm",
                                    key="log_call_reminder_dt",
                                )
                            with rem_col2:
                                reminder_note = st.text_input(
                                    "Reminder reason",
                                    placeholder="e.g. Try again Friday",
                                    key="log_call_reminder_note",
                                )
                        save_col, cancel_col = st.columns(2)
                        with save_col:
                            if st.button("Save call", key="log_call_save"):
                                client_id = cdm.make_client_id(sel_name, sel_building, sel_unit)
                                phone = str(row.get("phone", "") or "")
                                reminder_dt = None
                                if show_reminder and reminder_dt_str and reminder_dt_str.strip():
                                    reminder_dt = cdm.parse_reminder_datetime(reminder_dt_str.strip())
                                ok = cdm.log_call(
                                    client_id=client_id,
                                    client_name=sel_name,
                                    building=sel_building,
                                    unit=sel_unit,
                                    phone=phone,
                                    outcome=outcome,
                                    notes=call_notes or "",
                                    reminder_dt=reminder_dt,
                                    reminder_note=(reminder_note or "").strip() or None,
                                )
                                if ok:
                                    st.session_state.log_call_expanded = False
                                    st.success("Call logged.")
                                    st.rerun()
                                else:
                                    st.error("Failed to save call.")
                        with cancel_col:
                            if st.button("Cancel", key="log_call_cancel"):
                                st.session_state.log_call_expanded = False
                                st.rerun()

            csv_data = export_to_csv(display_df)
            st.download_button("↓ Download CSV", data=csv_data,
                             file_name="palm_jumeirah_leads.csv", mime="text/csv")


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT PROFILE PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_client_profile_page():
    """Render client profile with notes and reminder controls."""
    apply_global_styles()
    
    client = st.session_state.get('selected_client')
    if not client:
        st.warning("No client selected. Returning to lead search.")
        st.session_state.current_page = 'lead_search'
        st.rerun()
        return
    
    # Derive client_id deterministically
    client_id = cdm.make_client_id(
        client.get('owner_name', ''),
        client.get('building_name', ''),
        client.get('unit_number', '')
    )
    
    # ── Header ──────────────────────────────────────────────────────────────
    back_col, title_col = st.columns([1, 6])
    with back_col:
        if st.button("← Back", key="profile_back", use_container_width=True):
            st.session_state.current_page = st.session_state.get('profile_return_page', 'lead_search')
            st.rerun()
    with title_col:
        name_display = client.get('owner_name') or 'Unknown Owner'
        st.title(f" {name_display}")
    
    # ── Portfolio (all properties for this owner from leads data) ────────────
    owner_props = None
    try:
        leads_df, _ = load_data(_pf_mtime=_pf_csv_mtime(), _pq_mtime=_parquet_mtime())
        owner_name = (client.get('owner_name') or '').strip()
        if owner_name and not leads_df.empty and 'owner_name' in leads_df.columns:
            owner_props = leads_df[leads_df['owner_name'].fillna('').str.strip().str.lower() == owner_name.lower()]
            if not owner_props.empty:
                st.subheader(" Portfolio")
                if len(owner_props) == 1:
                    st.caption("Single property in our data. Click a row to see title deed and rental history.")
                else:
                    st.caption(f"{len(owner_props)} properties for this owner. Click a row to see title deed and rental history.")
                base_cols = ['building_name', 'unit_number', 'bedrooms', 'size_sqft', 'phone']
                if 'date' in owner_props.columns:
                    base_cols = ['building_name', 'unit_number', 'date', 'bedrooms', 'size_sqft', 'phone']
                disp = owner_props[[c for c in base_cols if c in owner_props.columns]].copy()
                if 'date' in disp.columns:
                    disp['date'] = pd.to_datetime(disp['date'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('—')
                disp['bedrooms'] = disp['bedrooms'].apply(lambda x: 'Studio' if x == 0 else (str(int(x)) if pd.notna(x) else '—'))
                disp['size_sqft'] = disp['size_sqft'].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x else '—')
                portfolio_event = st.dataframe(
                    disp,
                    use_container_width=True,
                    hide_index=True,
                    height=min(220, 80 + 35 * len(owner_props)),
                    on_select="rerun",
                    selection_mode="single-row",
                    key="profile_portfolio_table",
                )
                selected_rows = portfolio_event.selection.rows if portfolio_event.selection else []
                if selected_rows:
                    idx = selected_rows[0]
                    sel_row = owner_props.iloc[idx]
                    sel_building = str(sel_row.get('building_name', '') or '')
                    sel_unit = str(sel_row.get('unit_number', '') or '')
                    with st.expander(f"Unit details: **{sel_building}** — Unit {sel_unit}", expanded=True):
                        tab_td, tab_rent = st.tabs(["Title Deed History", "Rental History"])
                        with tab_td:
                            ref_df = get_reference_data()
                            if ref_df is not None and not ref_df.empty and 'building_std' in ref_df.columns and 'unit_no' in ref_df.columns:
                                b_std = (standardize_building_name(sel_building) or sel_building).strip().lower()
                                u_norm = str(sel_unit).strip().upper()
                                unit_txns = ref_df[
                                    (ref_df['building_std'].fillna('').astype(str).str.strip().str.lower() == b_std) &
                                    (ref_df['unit_no'].fillna('').astype(str).str.strip().str.upper() == u_norm)
                                ].copy()
                                if 'sale_date' in unit_txns.columns:
                                    unit_txns = unit_txns.sort_values('sale_date', ascending=False)
                                if not unit_txns.empty:
                                    td_disp = unit_txns[['sale_date', 'sale_price_aed', 'trans_group_en', 'sales_recurrence', 'size_sqft']].copy()
                                    td_disp['sale_date'] = pd.to_datetime(td_disp['sale_date'], errors='coerce').dt.strftime('%d/%m/%Y')
                                    td_disp['sale_price_aed'] = td_disp['sale_price_aed'].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x else '—')
                                    td_disp['size_sqft'] = td_disp['size_sqft'].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x else '—')
                                    st.dataframe(td_disp, use_container_width=True, hide_index=True)
                                else:
                                    st.caption("No title deed history found for this unit.")
                            else:
                                st.caption("No title deed history found for this unit.")
                        with tab_rent:
                            rental_df = load_rentals()
                            if rental_df is not None and not rental_df.empty:
                                status = get_unit_rental_status(rental_df, sel_building, sel_unit)
                                st.markdown(f"**Status:** {status.get('status', '—').replace('_', ' ').title()}")
                                rent_history = get_lease_renewal_history(rental_df, sel_building, sel_unit)
                                if not rent_history.empty and 'contract_end' in rent_history.columns:
                                    rent_history = rent_history.sort_values('contract_end', ascending=False, na_position='last')
                                if not rent_history.empty:
                                    rh_cols = [c for c in ['contract_start', 'contract_end', 'annualized_rent', 'contract_type', 'bedrooms', 'furnished', 'broker'] if c in rent_history.columns]
                                    rh_disp = rent_history[rh_cols].copy() if rh_cols else rent_history
                                    for col in ['contract_start', 'contract_end']:
                                        if col in rh_disp.columns:
                                            rh_disp[col] = pd.to_datetime(rh_disp[col], errors='coerce').dt.strftime('%d/%m/%Y')
                                    if 'annualized_rent' in rh_disp.columns:
                                        rh_disp['annualized_rent'] = rh_disp['annualized_rent'].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x else '—')
                                    st.dataframe(rh_disp, use_container_width=True, hide_index=True)
                                else:
                                    st.caption("No rental history found for this unit.")
                            else:
                                st.caption("No rental history found for this unit.")
    except Exception:
        pass
    
    # ── Client Info Card ────────────────────────────────────────────────────
    st.markdown("---")

    # Load any saved overrides and merge into display values
    overrides = cdm.get_lead_overrides(client_id)
    def _ov(field, raw):
        """Return override value if present, else raw lead value."""
        return overrides[field] if field in overrides else raw

    edit_mode = st.session_state.get(f"edit_lead_{client_id}", False)

    if not edit_mode:
        info_c1, info_c2, info_c3, info_c4, info_edit = st.columns([2, 2, 2, 2, 1])
        with info_c1:
            st.markdown(f"**Building:** {_ov('building_name', client.get('building_name', 'N/A'))}")
            st.markdown(f"**Unit:** {_ov('unit_number', client.get('unit_number', 'N/A'))}")
        with info_c2:
            beds = _ov('bedrooms', client.get('bedrooms'))
            beds_str = 'Studio' if str(beds) in ('0', '0.0', 'Studio') else (str(int(float(beds))) if beds and str(beds) not in ('', 'nan', 'None', 'N/A') else 'N/A')
            sqft = _ov('size_sqft', client.get('size_sqft'))
            sqft_str = f"{int(float(sqft)):,}" if sqft and str(sqft) not in ('', 'nan', 'None', 'N/A') else 'N/A'
            st.markdown(f"**Bedrooms:** {beds_str}")
            st.markdown(f"**Size:** {sqft_str} sqft")
        with info_c3:
            st.markdown(f"**Phone:** {_ov('phone', client.get('phone', 'N/A')) or 'N/A'}")
            st.markdown(f"**Date:** {client.get('date', 'N/A') or 'N/A'}")
        with info_c4:
            st.markdown(f"**Completeness:** {client.get('completeness', 'N/A')}%")
            st.markdown(f"**Quality:** {client.get('data_quality', 'N/A')}")
        with info_edit:
            st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
            if st.button("Edit", key=f"edit_lead_btn_{client_id}"):
                st.session_state[f"edit_lead_{client_id}"] = True
                st.rerun()
    else:
        st.markdown("**Edit lead details** — changes are saved as overrides (original data unchanged)")
        e1, e2, e3 = st.columns(3)
        with e1:
            new_building = st.text_input("Building", value=str(_ov('building_name', client.get('building_name', '')) or ''), key="edit_building")
            new_unit = st.text_input("Unit", value=str(_ov('unit_number', client.get('unit_number', '')) or ''), key="edit_unit")
        with e2:
            beds_raw = _ov('bedrooms', client.get('bedrooms'))
            beds_default = '' if beds_raw is None or str(beds_raw) in ('nan', 'None') else str(beds_raw)
            new_beds = st.text_input("Bedrooms (number or 'Studio')", value=beds_default, key="edit_beds")
            sqft_raw = _ov('size_sqft', client.get('size_sqft'))
            sqft_default = '' if sqft_raw is None or str(sqft_raw) in ('nan', 'None') else str(int(float(sqft_raw)))
            new_sqft = st.text_input("Size (sqft)", value=sqft_default, key="edit_sqft")
        with e3:
            new_phone = st.text_input("Phone", value=str(_ov('phone', client.get('phone', '')) or ''), key="edit_phone")

        save_col, cancel_col = st.columns([1, 4])
        with save_col:
            if st.button("Save changes", key=f"save_lead_edits_{client_id}", type="primary"):
                new_overrides = {
                    'building_name': new_building.strip(),
                    'unit_number': new_unit.strip(),
                    'bedrooms': new_beds.strip(),
                    'size_sqft': new_sqft.strip(),
                    'phone': new_phone.strip(),
                }
                cdm.save_lead_overrides(client_id, new_overrides)
                # Write back to parquet so main lead table reflects changes immediately
                _update_lead_in_parquet(
                    client.get('owner_name', ''),
                    client.get('building_name', ''),
                    client.get('unit_number', ''),
                    {k: v for k, v in new_overrides.items() if v},
                )
                # Reflect changes in the selected_client session state so the page updates
                for field, val in new_overrides.items():
                    if val:
                        st.session_state['selected_client'][field] = val
                st.session_state[f"edit_lead_{client_id}"] = False
                st.success("Saved.")
                st.rerun()
        with cancel_col:
            if st.button("Cancel", key=f"cancel_lead_edits_{client_id}"):
                st.session_state[f"edit_lead_{client_id}"] = False
                st.rerun()

    st.markdown("---")
    
    # ── Two-column layout: Notes (left) + Reminders (right) ────────────────
    notes_col, reminder_col = st.columns([3, 2])
    
    # ── NOTES SECTION ───────────────────────────────────────────────────────
    with notes_col:
        st.subheader(" Notes")
        
        # Add new note
        new_note_text = st.text_area(
            "Write a note...",
            placeholder="e.g., Spoke with owner, interested in selling at AED 5M...",
            key="new_note_input",
            height=100
        )
        if st.button(" Save Note", key="save_note_btn"):
            if new_note_text and new_note_text.strip():
                cdm.add_note(client_id, new_note_text.strip())
                st.rerun()
            else:
                st.warning("Note cannot be empty.")
        
        st.markdown("---")
        
        # Display existing notes
        notes = cdm.get_notes(client_id)
        if not notes:
            st.caption("No notes yet. Add your first note above.")
        else:
            for note in notes:
                note_id = note['id']
                timestamp = note.get('timestamp', '')[:19].replace('T', ' ')
                edited = note.get('edited_at')
                edit_label = f" *(edited {edited[:19].replace('T', ' ')})*" if edited else ""
                
                st.markdown(f"**{timestamp}**{edit_label}")
                
                # Check if this note is being edited
                if st.session_state.get(f'editing_note_{note_id}', False):
                    edited_text = st.text_area(
                        "Edit note:",
                        value=note['text'],
                        key=f"edit_text_{note_id}",
                        height=80
                    )
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        if st.button("✓ Save", key=f"save_edit_{note_id}"):
                            if edited_text and edited_text.strip():
                                cdm.edit_note(client_id, note_id, edited_text.strip())
                                st.session_state[f'editing_note_{note_id}'] = False
                                st.rerun()
                    with ec2:
                        if st.button("Cancel", key=f"cancel_edit_{note_id}"):
                            st.session_state[f'editing_note_{note_id}'] = False
                            st.rerun()
                else:
                    st.markdown(f"> {note['text']}")
                    
                    btn_c1, btn_c2, btn_c3 = st.columns([1, 1, 6])
                    with btn_c1:
                        if st.button("Edit", key=f"edit_note_{note_id}", help="Edit"):
                            st.session_state[f'editing_note_{note_id}'] = True
                            st.rerun()
                    with btn_c2:
                        # Delete with confirmation
                        if st.session_state.get(f'confirm_del_note_{note_id}', False):
                            if st.button("✕ Confirm", key=f"confirm_del_{note_id}"):
                                cdm.delete_note(client_id, note_id)
                                st.session_state[f'confirm_del_note_{note_id}'] = False
                                st.rerun()
                        else:
                            if st.button("Del", key=f"del_note_{note_id}", help="Delete"):
                                st.session_state[f'confirm_del_note_{note_id}'] = True
                                st.rerun()
                    
                st.markdown("---")
    
    # ── REMINDER SECTION (set another follow-up anytime from profile) ────────
    with reminder_col:
        st.subheader("⏰ Set another follow-up")
        
        with st.expander(" Set another follow-up", expanded=True):
            reminder_date_str = st.text_input(
                "Date & Time",
                placeholder="e.g., 08/02/2026, 2pm",
                key="reminder_date_input",
                help="Accepted: DD/MM/YYYY, time  |  e.g. 15/03/2026, 10:30am"
            )
            reminder_note = st.text_input(
                "Reason / Note",
                placeholder="e.g., Follow up on viewing, Call back re: offer",
                key="reminder_note_input"
            )
            
            if st.button(" Save Reminder", key="save_reminder_btn", use_container_width=True):
                parsed_dt = cdm.parse_reminder_datetime(reminder_date_str)
                if parsed_dt is None:
                    st.error("Could not parse date. Try: 08/02/2026, 2pm")
                elif not reminder_note or not reminder_note.strip():
                    st.warning("Please add a reason for the reminder.")
                else:
                    cdm.add_reminder(
                        client_id=client_id,
                        client_name=client.get('owner_name', ''),
                        building=client.get('building_name', ''),
                        unit=client.get('unit_number', ''),
                        phone=client.get('phone', ''),
                        reminder_dt=parsed_dt,
                        note=reminder_note.strip()
                    )
                    st.success(f"Reminder set for {parsed_dt.strftime('%d/%m/%Y %I:%M %p')}")
                    st.rerun()
        
        # Show existing reminders for this client
        st.markdown("---")
        st.markdown("**Upcoming reminders for this client:**")
        client_reminders = cdm.get_reminders_for_client(client_id)
        if not client_reminders:
            st.caption("No reminders set.")
        else:
            for rem in client_reminders:
                rem_id = rem['id']
                try:
                    from datetime import datetime as _dt
                    rem_dt = _dt.fromisoformat(rem['datetime'])
                    dt_str = rem_dt.strftime('%d/%m/%Y %I:%M %p')
                except (ValueError, TypeError):
                    rem_dt = None
                    dt_str = rem.get('datetime', '?')
                status_icon = "✓" if rem['status'] == 'done' else ""
                is_editing = st.session_state.get('editing_reminder_id') == rem_id
                if is_editing and rem.get('status') == 'pending':
                    new_dt_str = st.text_input("Date & time", value=dt_str, placeholder="e.g. 15/02/2026, 3pm", key=f"profile_edit_dt_{rem_id}")
                    new_note = st.text_input("Reason", value=rem.get('note') or '', key=f"profile_edit_note_{rem_id}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Save", key=f"profile_edit_save_{rem_id}"):
                            parsed = cdm.parse_reminder_datetime((new_dt_str or "").strip())
                            if parsed:
                                cdm.update_reminder(rem_id, reminder_dt=parsed, note=(new_note or "").strip() or "")
                                st.session_state.pop('editing_reminder_id', None)
                                st.rerun()
                            else:
                                st.error("Enter a valid date.")
                    with c2:
                        if st.button("Cancel", key=f"profile_edit_cancel_{rem_id}"):
                            st.session_state.pop('editing_reminder_id', None)
                            st.rerun()
                else:
                    st.markdown(f"{status_icon} **{dt_str}** — {rem.get('note', '')}")
                    if rem.get('status') == 'pending':
                        if st.button(" Edit date", key=f"profile_edit_btn_{rem_id}"):
                            st.session_state['editing_reminder_id'] = rem_id
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# CONTACTS LIST PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_contacts_page():
    """Render contacts list with search and filters."""
    apply_global_styles()

    back_col, title_col, new_col = st.columns([1, 4, 1])
    with back_col:
        if st.button("← Back", key="contacts_back", use_container_width=True):
            st.session_state.current_page = "lead_search"
            st.session_state.pop("contacts_subpage", None)
            st.session_state.pop("create_contact_from_lead", None)
            st.rerun()
    with title_col:
        st.title(" Contacts")
        st.caption("Manage contacts, properties, notes and follow-ups")
    with new_col:
        if st.button("+ New Contact", key="new_contact_btn", use_container_width=True):
            st.session_state.contacts_subpage = "create"
            st.session_state.pop("create_contact_from_lead", None)
            st.rerun()

    st.markdown("---")

    # Create contact form (when subpage is create or pre-filled from lead)
    from_lead = st.session_state.get("create_contact_from_lead")
    if st.session_state.get("contacts_subpage") == "create" or from_lead:
        with st.expander("+ New contact", expanded=True):
            pre = from_lead or {}
            full_name = st.text_input("Full name", value=pre.get("owner_name", ""), key="create_contact_name")
            phone = st.text_input("Phone", value=pre.get("phone", ""), key="create_contact_phone")
            email = st.text_input("Email", value=pre.get("email", ""), key="create_contact_email")
            contact_type = st.selectbox("Type", ["", "Owner", "Buyer", "Investor", "Broker", "Tenant", "Other"], key="create_contact_type")
            source = st.text_input("Source", key="create_contact_source")
            budget_min = st.number_input("Budget min (AED)", min_value=0, value=0, key="create_contact_bmin")
            budget_max = st.number_input("Budget max (AED)", min_value=0, value=0, key="create_contact_bmax")
            agent_assigned = st.text_input("Agent assigned", key="create_contact_agent")
            save_btn, cancel_btn = st.columns(2)
            with save_btn:
                if st.button("Save contact", key="create_contact_save"):
                    cid, err = con_man.create_contact(
                        full_name=full_name or None,
                        phone=phone or None,
                        email=email or None,
                        contact_type=contact_type or None,
                        source=source or None,
                        budget_min=budget_min if budget_min else None,
                        budget_max=budget_max if budget_max else None,
                        agent_assigned=agent_assigned or None,
                        properties=[{
                            "building_name": pre.get("building_name"),
                            "unit_number": pre.get("unit_number"),
                            "bedrooms": pre.get("bedrooms"),
                            "lead_id": pre.get("lead_id"),
                        }] if from_lead and (pre.get("building_name") or pre.get("unit_number")) else None,
                        leads_df=load_data(_pf_mtime=_pf_csv_mtime(), _pq_mtime=_parquet_mtime())[0],
                    )
                    if err:
                        st.error(err)
                    elif cid:
                        st.session_state.pop("contacts_subpage", None)
                        st.session_state.pop("create_contact_from_lead", None)
                        st.success("Contact created.")
                        st.session_state.selected_contact_id = cid
                        st.session_state.current_page = "contact_profile"
                        st.session_state.profile_return_page = "contacts"
                        st.rerun()
            with cancel_btn:
                if st.button("Cancel", key="create_contact_cancel"):
                    st.session_state.pop("contacts_subpage", None)
                    st.session_state.pop("create_contact_from_lead", None)
                    st.rerun()
        st.markdown("---")

    # Search and filters
    search_col, type_col, agent_col = st.columns([3, 1, 1])
    with search_col:
        query = st.text_input("Search (name, phone, email)", key="contacts_search", placeholder="Type to search...")
    with type_col:
        type_opt = st.selectbox(
            "Type",
            ["All", "Owner", "Buyer", "Investor", "Broker", "Tenant", "Other"],
            key="contacts_type_filter",
        )
    with agent_col:
        all_agents = sorted(set((r.get("agent_assigned") or "").strip() for r in con_man.search_contacts(limit=2000)))
        agents = ["All"] + [a for a in all_agents if a]
        agent_filter = st.selectbox("Agent", agents, key="contacts_agent_filter")

    contact_type = None if type_opt == "All" else type_opt
    agent_assigned = None if (agent_filter == "All" or not agent_filter) else agent_filter
    contacts_list = con_man.search_contacts(query=query or None, contact_type=contact_type, agent_assigned=agent_assigned)

    if not contacts_list:
        st.info("No contacts found. Click **+ New Contact** to create one, or adjust filters.")
        return

    # Table: Name, Phone, Type, Properties Count, Last Contact, Agent, Budget, Actions
    rows = []
    for c in contacts_list:
        props = con_man.get_contact_properties(c["id"])
        last_contact = c.get("last_contact_date")
        if last_contact:
            try:
                last_contact = datetime.fromisoformat(str(last_contact)).strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                last_contact = str(last_contact)[:10]
        else:
            last_contact = "—"
        budget = ""
        if c.get("budget_min") is not None or c.get("budget_max") is not None:
            if c.get("budget_min") and c.get("budget_max"):
                budget = f"{int(c['budget_min']):,}–{int(c['budget_max']):,}"
            elif c.get("budget_min"):
                budget = f"{int(c['budget_min']):,}+"
            else:
                budget = f"≤{int(c['budget_max']):,}"
        rows.append({
            "id": c["id"],
            "Name": c.get("full_name") or "—",
            "Phone": c.get("phone") or "—",
            "Type": c.get("contact_type") or "—",
            "Properties": len(props),
            "Last Contact": last_contact,
            "Agent": c.get("agent_assigned") or "—",
            "Budget": budget or "—",
        })

    df = pd.DataFrame(rows)
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400,
        on_select="rerun",
        selection_mode="single-row",
        key="contacts_table",
    )
    selected = event.selection.rows if event.selection else []
    if selected:
        idx = selected[0]
        contact_id = int(rows[idx]["id"])
        if st.button("Open profile", key="open_contact_profile_btn"):
            st.session_state.selected_contact_id = contact_id
            st.session_state.current_page = "contact_profile"
            st.session_state.profile_return_page = "contacts"
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# CONTACT PROFILE PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_contact_profile_page():
    """Render contact detail: info, properties, linked leads, notes, follow-ups, call log."""
    apply_global_styles()

    contact_id = st.session_state.get("selected_contact_id")
    if not contact_id:
        st.warning("No contact selected. Returning to Contacts.")
        st.session_state.current_page = "contacts"
        st.rerun()
        return

    contact = con_man.get_contact(contact_id)
    if not contact:
        st.error("Contact not found.")
        st.session_state.current_page = "contacts"
        st.rerun()
        return

    client_id = con_man.contact_client_id(contact_id)
    display_name = contact.get("full_name") or "Unknown"

    # Back button and title
    back_col, title_col = st.columns([1, 6])
    with back_col:
        if st.button("← Back", key="contact_profile_back", use_container_width=True):
            st.session_state.current_page = st.session_state.get("profile_return_page", "contacts")
            st.rerun()
    with title_col:
        st.title(f" {display_name}")

    # Contact info section (read-only display + editable expander)
    st.subheader("Contact info")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"**Phone:** {contact.get('phone') or '—'}")
        st.markdown(f"**Email:** {contact.get('email') or '—'}")
    with c2:
        st.markdown(f"**Type:** {contact.get('contact_type') or '—'}")
        st.markdown(f"**Source:** {contact.get('source') or '—'}")
    with c3:
        bmin, bmax = contact.get("budget_min"), contact.get("budget_max")
        budget_str = "—"
        if bmin is not None or bmax is not None:
            if bmin is not None and bmax is not None:
                budget_str = f"{int(bmin):,} – {int(bmax):,} AED"
            elif bmin is not None:
                budget_str = f"{int(bmin):,}+ AED"
            else:
                budget_str = f"≤ {int(bmax):,} AED"
        st.markdown(f"**Budget:** {budget_str}")
        st.markdown(f"**Agent:** {contact.get('agent_assigned') or '—'}")
    with c4:
        last = contact.get("last_contact_date")
        st.markdown(f"**Last contact:** {last[:10] if last else '—'}")

    with st.expander(" Edit contact"):
        edit_name = st.text_input("Full name", value=contact.get("full_name") or "", key="contact_edit_name")
        edit_phone = st.text_input("Phone", value=contact.get("phone") or "", key="contact_edit_phone")
        edit_email = st.text_input("Email", value=contact.get("email") or "", key="contact_edit_email")
        type_opts = ["", "Owner", "Buyer", "Investor", "Broker", "Tenant", "Other"]
        current_type = (contact.get("contact_type") or "").strip()
        type_index = type_opts.index(current_type) if current_type in type_opts else 0
        edit_type = st.selectbox("Type", type_opts, index=type_index, key="contact_edit_type")
        edit_source = st.text_input("Source", value=contact.get("source") or "", key="contact_edit_source")
        edit_bmin = st.number_input("Budget min (AED)", min_value=0, value=int(contact.get("budget_min") or 0), key="contact_edit_bmin")
        edit_bmax = st.number_input("Budget max (AED)", min_value=0, value=int(contact.get("budget_max") or 0), key="contact_edit_bmax")
        edit_agent = st.text_input("Agent assigned", value=contact.get("agent_assigned") or "", key="contact_edit_agent")
        if st.button("Save changes", key="contact_edit_save"):
            con_man.update_contact(contact_id, full_name=edit_name or None, phone=edit_phone or None, email=edit_email or None, contact_type=edit_type or None, source=edit_source or None, budget_min=edit_bmin if edit_bmin else None, budget_max=edit_bmax if edit_bmax else None, agent_assigned=edit_agent or None)
            st.rerun()

    st.markdown("---")
    st.subheader("Properties")
    props = contact.get("properties", [])
    if not props:
        st.caption("No properties added yet.")
    else:
        for p in props:
            lead_badge = " From Lead DB" if p.get("lead_id") else ""
            scraped_badge = " Active Listing" if p.get("is_scraped_listing") else ""
            st.markdown(f"**{p.get('building_name') or '—'}** — Unit {p.get('unit_number') or '—'} | BR: {p.get('bedrooms') or '—'} | Bath: {p.get('bathrooms') or '—'} | Price: {p.get('price_aed') or '—'} | Intent: {p.get('intent') or '—'} | View: {p.get('view_type') or '—'}{lead_badge}{scraped_badge}")
            if p.get("scraped_listing_url"):
                st.markdown(f" [Listing link]({p['scraped_listing_url']})")
            if p.get("notes"):
                st.caption(f" Note: {p['notes']}")
            # Resolve BR/Bath/View from unit number when any are missing
            has_building_unit = (p.get("building_name") or "").strip() and (p.get("unit_number") or "").strip()
            missing_any = not (p.get("bedrooms") or "").strip() or not (p.get("bathrooms") or "").strip() or not (p.get("view_type") or "").strip()
            if has_building_unit and missing_any and st.button("Resolve BR / Bath / View from unit", key=f"resolve_prop_{p.get('id')}"):
                resolved = con_man.resolve_unit_specs(p.get("building_name"), p.get("unit_number"))
                con_man.update_contact_property(
                    p["id"],
                    bedrooms=resolved.get("bedrooms") if resolved.get("bedrooms") else p.get("bedrooms"),
                    bathrooms=resolved.get("bathrooms") if resolved.get("bathrooms") else p.get("bathrooms"),
                    view_type=resolved.get("view_type") if resolved.get("view_type") else p.get("view_type"),
                )
                st.rerun()

    with st.expander("+ Add property"):
        add_building = st.text_input("Building", key="contact_add_prop_building")
        add_unit = st.text_input("Unit number", key="contact_add_prop_unit")
        add_br = st.text_input("Bedrooms", key="contact_add_prop_br")
        add_bath = st.text_input("Bathrooms", key="contact_add_prop_bath")
        add_price = st.number_input("Price (AED)", min_value=0, value=0, key="contact_add_prop_price")
        add_intent = st.selectbox("Intent", ["", "selling", "renting", "buying", "renting_looking"], key="contact_add_prop_intent")
        add_view = st.text_input("View type", key="contact_add_prop_view")
        add_notes = st.text_input("Notes", key="contact_add_prop_notes")
        if st.button("Add property", key="contact_add_prop_btn"):
            add_br_final = add_br or None
            add_bath_final = add_bath or None
            add_view_final = add_view or None
            if (add_building or add_unit) and (not add_br_final or not add_bath_final or not add_view_final):
                resolved = con_man.resolve_unit_specs(add_building or None, add_unit or None)
                if not add_br_final and resolved.get("bedrooms"):
                    add_br_final = resolved["bedrooms"]
                if not add_bath_final and resolved.get("bathrooms"):
                    add_bath_final = resolved["bathrooms"]
                if not add_view_final and resolved.get("view_type"):
                    add_view_final = resolved["view_type"]
            con_man.add_property_to_contact(
                contact_id,
                building_name=add_building or None,
                unit_number=add_unit or None,
                bedrooms=add_br_final,
                bathrooms=add_bath_final,
                price_aed=add_price if add_price else None,
                intent=add_intent or None,
                view_type=add_view_final,
                notes=add_notes or None,
            )
            st.rerun()

    # Linked portfolio (from leads)
    linked = contact.get("linked_leads", [])
    if linked:
        st.markdown("---")
        st.subheader("Linked portfolio (from lead database)")
        for link in linked:
            lead = link.get("lead")
            if lead:
                lid = lead.get("id")
                building = lead.get("building_name") or ""
                unit = lead.get("unit_number") or ""
                br = lead.get("bedrooms")
                br_str = str(br) if br is not None else "—"
                st.markdown(f"- **{building}** — {unit} | {br_str} BR | {lead.get('phone') or '—'}")
                # Add to Contact Properties (import this lead as a contact property)
                already = any(p.get("lead_id") == lid for p in contact.get("properties", []))
                if not already and st.button("+ Add to Contact Properties", key=f"add_lead_prop_{lid}"):
                    resolved = con_man.resolve_unit_specs(building or None, unit or None)
                    con_man.add_property_to_contact(
                        contact_id,
                        building_name=building,
                        unit_number=unit,
                        bedrooms=str(br) if br is not None else resolved.get("bedrooms"),
                        bathrooms=resolved.get("bathrooms"),
                        view_type=resolved.get("view_type"),
                        lead_id=lid,
                    )
                    st.rerun()

    st.markdown("---")
    notes_col, reminder_col = st.columns([3, 2])

    with notes_col:
        st.subheader("Notes")
        new_note = st.text_area("Write a note...", key="contact_note_input", height=80)
        if st.button("Save note", key="contact_save_note_btn"):
            if new_note and new_note.strip():
                cdm.add_note(client_id, new_note.strip())
                st.rerun()
        notes = cdm.get_notes(client_id)
        for note in notes:
            ts = note.get("timestamp", "")[:19].replace("T", " ")
            st.markdown(f"**{ts}**")
            st.markdown(f"> {note['text']}")
            st.markdown("---")

    with reminder_col:
        st.subheader("Follow-ups")
        with st.expander("Set follow-up", expanded=False):
            rem_date = st.text_input("Date & time", placeholder="e.g. 15/02/2026, 3pm", key="contact_rem_date")
            rem_note = st.text_input("Reason", key="contact_rem_note")
            if st.button("Save reminder", key="contact_save_rem_btn"):
                parsed = cdm.parse_reminder_datetime(rem_date)
                if parsed and rem_note and rem_note.strip():
                    cdm.add_reminder(
                        client_id=client_id,
                        client_name=display_name,
                        building="",
                        unit="",
                        phone=contact.get("phone") or "",
                        reminder_dt=parsed,
                        note=rem_note.strip(),
                    )
                    st.rerun()
                elif not parsed:
                    st.error("Enter a valid date.")
                else:
                    st.warning("Add a reason.")
        for rem in cdm.get_reminders_for_client(client_id):
            rem_id = rem["id"]
            try:
                rem_dt = datetime.fromisoformat(rem["datetime"])
                dt_str = rem_dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                rem_dt = None
                dt_str = rem.get('datetime', '?')
            is_editing = st.session_state.get('editing_reminder_id') == rem_id
            if is_editing and rem.get('status') == 'pending':
                new_dt_str = st.text_input("Date & time", value=dt_str, placeholder="e.g. 15/02/2026, 3pm", key=f"contact_edit_dt_{rem_id}")
                new_note = st.text_input("Reason", value=rem.get('note') or '', key=f"contact_edit_note_{rem_id}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Save", key=f"contact_edit_save_{rem_id}"):
                        parsed = cdm.parse_reminder_datetime((new_dt_str or "").strip())
                        if parsed:
                            cdm.update_reminder(rem_id, reminder_dt=parsed, note=(new_note or "").strip() or "")
                            st.session_state.pop('editing_reminder_id', None)
                            st.rerun()
                        else:
                            st.error("Enter a valid date.")
                with c2:
                    if st.button("Cancel", key=f"contact_edit_cancel_{rem_id}"):
                        st.session_state.pop('editing_reminder_id', None)
                        st.rerun()
            else:
                st.markdown(f" {dt_str} — {rem.get('note', '')}")
                if rem.get('status') == 'pending':
                    if st.button(" Edit date", key=f"contact_edit_btn_{rem_id}"):
                        st.session_state['editing_reminder_id'] = rem_id
                        st.rerun()

    st.markdown("---")
    st.subheader("Call log")
    if st.button("Log call", key="contact_log_call_btn"):
        st.session_state.contact_log_call_expanded = True
        st.rerun()
    if st.session_state.get("contact_log_call_expanded", False):
        with st.expander("Log call", expanded=True):
            outcome = st.radio("Outcome", options=list(cdm.CALL_OUTCOMES), format_func=lambda x: x.replace("_", " ").title(), key="contact_call_outcome", horizontal=True)
            call_notes = st.text_input("Notes", key="contact_call_notes")
            show_rem = outcome in ("voicemail", "no_answer", "callback")
            rem_dt_str = ""
            rem_note_str = ""
            if show_rem:
                rem_dt_str = st.text_input("Follow-up date", placeholder="e.g. 15/02/2026, 3pm", key="contact_call_rem_dt")
                rem_note_str = st.text_input("Reminder reason", key="contact_call_rem_note")
            if st.button("Save call", key="contact_call_save"):
                rem_dt = cdm.parse_reminder_datetime((rem_dt_str or "").strip()) if show_rem and (rem_dt_str or "").strip() else None
                cdm.log_call(
                    client_id, display_name, "", "", contact.get("phone") or "",
                    outcome, call_notes or "", rem_dt,
                    (rem_note_str or "").strip() or None if show_rem else None,
                )
                con_man.update_last_contact_date(contact_id)
                st.session_state.contact_log_call_expanded = False
                st.rerun()
            if st.button("Cancel", key="contact_call_cancel"):
                st.session_state.contact_log_call_expanded = False
                st.rerun()
    calls = cdm.get_call_log(client_id=client_id)
    for c in calls[:20]:
        called = c.get("called_at", "")[:19].replace("T", " ")
        st.caption(f"{called} — {c.get('outcome', '')} — {c.get('notes', '')}")


# ═══════════════════════════════════════════════════════════════════════════════
# FOLLOW-UP LIST PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_follow_ups_page():
    """Render the follow-up / reminder list page."""
    apply_global_styles()
    from datetime import datetime as _dt
    
    # Header
    back_col, title_col = st.columns([1, 6])
    with back_col:
        if st.button("← Back", key="followup_back", use_container_width=True):
            st.session_state.current_page = 'lead_search'
            st.rerun()
    with title_col:
        st.title(" Follow-Up List")
        st.caption("All reminders: overdue at top, completed at bottom")
    
    st.markdown("---")
    
    reminders = cdm.get_all_reminders()
    
    if not reminders:
        st.info("No follow-up reminders set yet. Open a client profile to create one.")
        return
    
    now = _dt.now()
    
    # Column headers (Profile = open client profile with portfolio)
    hdr = st.columns([2, 2, 1, 2, 2, 1, 1, 1, 1, 1])
    hdr[0].markdown("**Client**")
    hdr[1].markdown("**Building**")
    hdr[2].markdown("**Unit**")
    hdr[3].markdown("**Phone**")
    hdr[4].markdown("**Reminder**")
    hdr[5].markdown("**Status**")
    hdr[6].markdown("**Done**")
    hdr[7].markdown("**Del**")
    hdr[8].markdown("**Edit**")
    hdr[9].markdown("**Profile**")
    st.markdown("---")
    
    for rem in reminders:
        rem_id = rem['id']
        
        # Parse reminder datetime for display
        try:
            rem_dt = _dt.fromisoformat(rem.get('datetime', ''))
            dt_display = rem_dt.strftime('%d/%m/%Y %I:%M %p')
        except (ValueError, TypeError):
            rem_dt = None
            dt_display = rem.get('datetime', '?')
        
        # Determine visual status
        status = rem.get('status', 'pending')
        if status == 'done':
            status_label = "✓ Done"
        elif rem_dt and rem_dt <= now:
            status_label = "🔴 Overdue"
        elif rem_dt and rem_dt.date() == now.date():
            status_label = "🟡 Today"
        else:
            status_label = " Upcoming"
        
        cols = st.columns([2, 2, 1, 2, 2, 1, 1, 1, 1, 1])
        cols[0].write(rem.get('client_name', 'Unknown'))
        cols[1].write(rem.get('building', ''))
        cols[2].write(rem.get('unit', ''))
        cols[3].write(rem.get('phone', ''))
        cols[4].write(f"{dt_display}")
        cols[5].write(status_label)
        
        # Done button (green tick)
        with cols[6]:
            if status == 'pending':
                if st.button("✓", key=f"done_{rem_id}", help="Mark as done"):
                    cdm.mark_reminder_done(rem_id)
                    # Prompt for follow-up: store the reminder ID so we show the form
                    st.session_state[f'followup_prompt_{rem_id}'] = True
                    st.rerun()
            else:
                st.write("—")
        
        # Delete button
        with cols[7]:
            if st.session_state.get(f'confirm_del_rem_{rem_id}', False):
                if st.button("✕", key=f"confirm_del_rem_{rem_id}_btn", help="Confirm delete"):
                    cdm.delete_reminder(rem_id)
                    st.session_state[f'confirm_del_rem_{rem_id}'] = False
                    st.rerun()
            else:
                if st.button("Del", key=f"del_rem_{rem_id}", help="Delete permanently"):
                    st.session_state[f'confirm_del_rem_{rem_id}'] = True
                    st.rerun()
        
        # Edit button (change date/note)
        with cols[8]:
            if status == 'pending':
                if st.button("Edit", key=f"edit_rem_{rem_id}", help="Change date or reason"):
                    st.session_state['editing_reminder_id'] = rem_id
                    st.rerun()
            else:
                st.write("—")
        
        # Open client or contact profile
        with cols[9]:
            if st.button("View", key=f"profile_{rem_id}", help="Open profile"):
                client_id = rem.get('client_id', '')
                if con_man.is_contact_client_id(client_id):
                    cid = con_man.contact_id_from_client_id(client_id)
                    if cid is not None:
                        st.session_state.selected_contact_id = cid
                        st.session_state.profile_return_page = 'follow_ups'
                        st.session_state.current_page = 'contact_profile'
                        st.rerun()
                else:
                    st.session_state.selected_client = {
                        'owner_name': rem.get('client_name', ''),
                        'building_name': rem.get('building', ''),
                        'unit_number': rem.get('unit', ''),
                        'phone': rem.get('phone', ''),
                    }
                    st.session_state.profile_return_page = 'follow_ups'
                    st.session_state.current_page = 'client_profile'
                    st.rerun()
        
        # Reminder note display
        if rem.get('note'):
            st.caption(f" {rem['note']}")
        
        # Edit reminder (change date / reason)
        if st.session_state.get('editing_reminder_id') == rem_id and status == 'pending':
            with st.container():
                st.caption("Change date or reason:")
                edit_c1, edit_c2 = st.columns(2)
                with edit_c1:
                    new_dt_str = st.text_input(
                        "Date & time",
                        value=dt_display,
                        placeholder="e.g. 15/02/2026, 3pm",
                        key=f"edit_rem_dt_{rem_id}"
                    )
                    new_note = st.text_input(
                        "Reason",
                        value=rem.get('note') or '',
                        key=f"edit_rem_note_{rem_id}"
                    )
                with edit_c2:
                    st.markdown("")
                    st.markdown("")
                    if st.button("Save", key=f"edit_rem_save_{rem_id}"):
                        parsed = cdm.parse_reminder_datetime(new_dt_str.strip())
                        if parsed:
                            cdm.update_reminder(rem_id, reminder_dt=parsed, note=(new_note or "").strip() or "")
                            st.session_state.pop('editing_reminder_id', None)
                            st.rerun()
                        else:
                            st.error("Enter a valid date.")
                    if st.button("Cancel", key=f"edit_rem_cancel_{rem_id}"):
                        st.session_state.pop('editing_reminder_id', None)
                        st.rerun()
        
        # Follow-up prompt after marking done
        if st.session_state.get(f'followup_prompt_{rem_id}', False):
            with st.container():
                st.success(f"Marked done! Set a follow-up for **{rem.get('client_name', '')}**?")
                fu_c1, fu_c2 = st.columns(2)
                with fu_c1:
                    fu_date = st.text_input(
                        "Follow-up date & time",
                        placeholder="e.g., 15/02/2026, 3pm",
                        key=f"fu_date_{rem_id}"
                    )
                    fu_note = st.text_input(
                        "Follow-up reason",
                        placeholder="e.g., Second follow-up call",
                        key=f"fu_note_{rem_id}"
                    )
                with fu_c2:
                    st.markdown("")
                    st.markdown("")
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        if st.button(" Set Follow-Up", key=f"set_fu_{rem_id}"):
                            parsed_fu = cdm.parse_reminder_datetime(fu_date)
                            if parsed_fu and fu_note and fu_note.strip():
                                cdm.add_reminder(
                                    client_id=rem.get('client_id', ''),
                                    client_name=rem.get('client_name', ''),
                                    building=rem.get('building', ''),
                                    unit=rem.get('unit', ''),
                                    phone=rem.get('phone', ''),
                                    reminder_dt=parsed_fu,
                                    note=fu_note.strip()
                                )
                                st.session_state[f'followup_prompt_{rem_id}'] = False
                                st.rerun()
                            else:
                                st.error("Enter a valid date and reason.")
                    with fc2:
                        if st.button("Skip", key=f"skip_fu_{rem_id}"):
                            st.session_state[f'followup_prompt_{rem_id}'] = False
                            st.rerun()
        
        st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# CALL LOG PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def _outcome_badge(outcome: str) -> str:
    """Return a short badge label for call outcome (for display)."""
    labels = {
        "voicemail": " Voicemail",
        "no_answer": " No answer",
        "not_interested": "✕ Not interested",
        "interested": "✓ Interested",
        "callback": "↺ Callback",
    }
    return labels.get(outcome, outcome or "—")


def render_call_log_page():
    """Render the call log: all logged calls with filters and stats."""
    apply_global_styles()
    from datetime import datetime as _dt
    from datetime import timedelta

    back_col, title_col = st.columns([1, 6])
    with back_col:
        if st.button("← Back", key="calllog_back", use_container_width=True):
            st.session_state.current_page = "lead_search"
            st.rerun()
    with title_col:
        st.title(" Call Log")
        st.caption("All logged calls with outcome, notes, and reminders")

    calls = cdm.get_call_log()
    now = _dt.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    if not calls:
        st.info("No calls logged yet. Select a lead on the Lead Search page and click **Log Call**.")
        return

    # Stats summary
    calls_today = sum(1 for c in calls if c.get("called_at") and _dt.fromisoformat(c["called_at"]).date() == now.date())
    calls_week = sum(1 for c in calls if c.get("called_at") and _dt.fromisoformat(c["called_at"]) >= week_start)
    outcome_counts = {}
    for c in calls:
        o = c.get("outcome") or "—"
        outcome_counts[o] = outcome_counts.get(o, 0) + 1

    st.markdown("---")
    stat1, stat2, stat3, stat4, stat5 = st.columns(5)
    stat1.metric("Calls today", calls_today)
    stat2.metric("Calls (7 days)", calls_week)
    stat3.metric("Voicemail", outcome_counts.get("voicemail", 0))
    stat4.metric("No answer", outcome_counts.get("no_answer", 0))
    stat5.metric("Not interested", outcome_counts.get("not_interested", 0))
    st.markdown("---")

    # Filters
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        outcome_filter = st.selectbox(
            "Filter by outcome",
            options=["All"] + list(cdm.CALL_OUTCOMES),
            format_func=lambda x: "All" if x == "All" else x.replace("_", " ").title(),
            key="calllog_outcome_filter",
        )
    with filter_col2:
        date_range = st.selectbox(
            "Date range",
            options=["All", "Today", "Last 7 days", "Last 30 days"],
            key="calllog_date_filter",
        )

    filtered_calls = calls
    if outcome_filter != "All":
        filtered_calls = [c for c in filtered_calls if c.get("outcome") == outcome_filter]
    if date_range == "Today":
        filtered_calls = [c for c in filtered_calls if c.get("called_at") and _dt.fromisoformat(c["called_at"]).date() == now.date()]
    elif date_range == "Last 7 days":
        filtered_calls = [c for c in filtered_calls if c.get("called_at") and _dt.fromisoformat(c["called_at"]) >= week_start]
    elif date_range == "Last 30 days":
        month_start = today_start - timedelta(days=30)
        filtered_calls = [c for c in filtered_calls if c.get("called_at") and _dt.fromisoformat(c["called_at"]) >= month_start]

    # Column headers
    hdr = st.columns([2, 2, 1, 2, 1.5, 2, 1.5, 0.8])
    hdr[0].markdown("**Client**")
    hdr[1].markdown("**Building**")
    hdr[2].markdown("**Unit**")
    hdr[3].markdown("**Phone**")
    hdr[4].markdown("**Called at**")
    hdr[5].markdown("**Outcome**")
    hdr[6].markdown("**Reminder**")
    hdr[7].markdown("**Profile**")
    st.markdown("---")

    for i, c in enumerate(filtered_calls):
        try:
            called_dt = _dt.fromisoformat(c.get("called_at", ""))
            called_display = called_dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            called_display = c.get("called_at", "?")
        reminder_display = "—"
        if c.get("reminder_dt") and c.get("reminder_note"):
            try:
                rem_dt = _dt.fromisoformat(c["reminder_dt"])
                reminder_display = f"{rem_dt.strftime('%d/%m/%Y')} — {c.get('reminder_note', '')}"
            except (ValueError, TypeError):
                reminder_display = c.get("reminder_note", "—")

        cols = st.columns([2, 2, 1, 2, 1.5, 2, 1.5, 0.8])
        cols[0].write(c.get("client_name", "Unknown"))
        cols[1].write(c.get("building", ""))
        cols[2].write(c.get("unit", ""))
        cols[3].write(c.get("phone", ""))
        cols[4].write(called_display)
        cols[5].write(_outcome_badge(c.get("outcome", "")))
        cols[6].write(reminder_display)
        with cols[7]:
            if st.button("View", key=f"calllog_profile_{i}_{c.get('id', i)}", help="Open profile"):
                client_id = c.get("client_id", "")
                if con_man.is_contact_client_id(client_id):
                    cid = con_man.contact_id_from_client_id(client_id)
                    if cid is not None:
                        st.session_state.selected_contact_id = cid
                        st.session_state.profile_return_page = "call_log"
                        st.session_state.current_page = "contact_profile"
                        st.rerun()
                else:
                    st.session_state.selected_client = {
                        "owner_name": c.get("client_name", ""),
                        "building_name": c.get("building", ""),
                        "unit_number": c.get("unit", ""),
                        "phone": c.get("phone", ""),
                    }
                    st.session_state.profile_return_page = "call_log"
                    st.session_state.current_page = "client_profile"
                    st.rerun()
        if c.get("notes"):
            st.caption(f" {c['notes']}")
        st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# LEASE EXPIRY DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_lease_expiry_page():
    """Render the lease expiry dashboard page."""
    apply_global_styles()
    from datetime import datetime as _dt
    
    # Header
    back_col, title_col, hlm_col = st.columns([1, 5, 1])
    with back_col:
        if st.button("← Back", key="rental_back", use_container_width=True):
            st.session_state.current_page = 'lead_search'
            st.rerun()
    with title_col:
        st.title(" Lease Expiry Dashboard")
        st.caption("Landlord hot leads: expiring leases with owner contacts")
    with hlm_col:
        if st.button(" HLM", key="rental_hlm", type="primary", use_container_width=True):
            st.session_state.current_page = 'ai_chat'
            st.rerun()
    
    st.markdown("---")
    
    # Load data
    with st.spinner("Loading rental data..."):
        rental_df = load_rentals()
        leads_df, _ = load_data(_pf_mtime=_pf_csv_mtime(), _pq_mtime=_parquet_mtime())
    
    if rental_df.empty:
        st.warning("⚠ No rental data loaded. Run the rental scraper first:")
        st.code("python property_research_agent/rental_scraper.py")
        st.info("**Instructions:**\n1. Open Chrome with remote debugging\n2. Log into Property Monitor\n3. Navigate to Rentals, select Palm Jumeirah, set date range to last 3 years\n4. Run the scraper")
        return
    
    # Filters
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    
    with filter_col1:
        buildings = sorted(rental_df['building_name'].dropna().unique())
        building_filter = st.selectbox("Building", options=['All'] + buildings, key="rental_building_filter")
    
    with filter_col2:
        bedrooms_options = ['All', 'Studio', '1', '2', '3', '4', '5']
        bedroom_filter = st.selectbox("Bedrooms", options=bedrooms_options, key="rental_bedroom_filter")
    
    with filter_col3:
        expiry_window = st.selectbox(
            "Expiry Window",
            options=[30, 60, 90, 180],
            index=2,
            format_func=lambda x: f"{x} days",
            key="rental_expiry_window"
        )
    
    st.markdown("---")
    
    # Get expiring leases with cross-reference to owners
    expiring_cross_ref = cross_reference_rentals_with_owners(
        rental_df=rental_df,
        leads_df=leads_df,
        days_ahead=expiry_window
    )
    
    # Apply filters
    if not expiring_cross_ref.empty:
        filtered_expiring = expiring_cross_ref.copy()
        
        if building_filter != 'All':
            filtered_expiring = filtered_expiring[
                filtered_expiring['building_name'].fillna('').str.lower().str.contains(
                    building_filter.lower(), regex=False, na=False
                )
            ]
        
        if bedroom_filter != 'All':
            if bedroom_filter == 'Studio':
                filtered_expiring = filtered_expiring[
                    filtered_expiring['bedrooms'].fillna('').str.lower().str.contains('studio', regex=False, na=False)
                ]
            else:
                filtered_expiring = filtered_expiring[
                    filtered_expiring['bedrooms'].astype(str).str.strip() == bedroom_filter
                ]
    else:
        filtered_expiring = expiring_cross_ref
    
    # Summary metrics
    total_expiring = len(filtered_expiring)
    with_contacts = filtered_expiring['has_owner_contact'].sum() if not filtered_expiring.empty else 0
    active_rentals = get_active_rental_count(rental_df)
    
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric(f"Expiring in {expiry_window} days", f"{total_expiring}")
    metric_col2.metric("With Owner Contact", f"{with_contacts}", delta=f"{(with_contacts/total_expiring*100) if total_expiring > 0 else 0:.0f}%")
    metric_col3.metric("Active Rentals", f"{active_rentals:,}")
    metric_col4.metric("Unique Buildings", f"{rental_df['building_name'].nunique()}")
    
    st.markdown("---")
    
    if filtered_expiring.empty:
        st.info(f"No leases expiring in the next {expiry_window} days for the selected filters.")
        return
    
    # Results table
    st.subheader(f" {total_expiring} Expiring Leases")
    st.caption(f"Sorted by expiry date (most urgent first) |  = Owner contact available")
    
    # Display dataframe with custom formatting
    display_df = filtered_expiring.copy()
    
    # Format date
    display_df['Lease Expiry'] = pd.to_datetime(display_df['contract_end']).dt.strftime('%d %b %Y')
    
    # Format days remaining
    display_df['Days'] = display_df['days_remaining'].fillna(0).astype(int)
    
    # Format rent
    display_df['Annual Rent'] = display_df['annual_rent'].apply(
        lambda x: f"AED {x:,.0f}" if pd.notna(x) else "-"
    )
    
    # Contact indicator
    display_df['Contact'] = display_df['has_owner_contact'].apply(lambda x: " ✓" if x else "✕")
    
    # Select and order columns
    output_cols = {
        'building_name': 'Building',
        'unit_number': 'Unit',
        'bedrooms': 'Beds',
        'Lease Expiry': 'Lease Expiry',
        'Days': 'Days',
        'Annual Rent': 'Annual Rent',
        'Contact': 'Contact',
        'owner_name': 'Owner',
        'owner_phone': 'Phone'
    }
    
    display_columns = [col for col in output_cols.keys() if col in display_df.columns]
    display_df_final = display_df[display_columns].rename(columns=output_cols)
    
    # Display with alternating row colors
    st.dataframe(
        display_df_final,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Days": st.column_config.NumberColumn(
                "Days",
                help="Days until lease expires",
                format="%d"
            ),
            "Phone": st.column_config.TextColumn(
                "Phone",
                width="medium",
            ),
        }
    )
    
    # Export button
    st.markdown("---")
    export_col1, export_col2 = st.columns([1, 4])
    with export_col1:
        csv = display_df_final.to_csv(index=False, encoding='utf-8')
        st.download_button(
            label="↓ Export to CSV",
            data=csv,
            file_name=f"expiring_leases_{expiry_window}days_{_dt.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            key="export_rentals_csv"
        )
    with export_col2:
        st.caption(f"**HOT LEADS:** {with_contacts} landlords with expiring leases that you can call directly")


# ═══════════════════════════════════════════════════════════════════════════════
# WHATSAPP CAMPAIGN PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_whatsapp_page():
    """Render WhatsApp campaign management page."""
    apply_global_styles()
    
    # Header
    header_col1, header_col2, header_col3 = st.columns([4, 1.5, 1])
    
    with header_col1:
        st.title(" WhatsApp Outreach")
        st.caption("Campaign builder and message log")
    
    with header_col2:
        if st.button("Open WhatsApp", type="primary", use_container_width=True, help="Launch Chrome with WhatsApp Web (debug port 9222). Log in there, then run campaigns."):
            root = Path(__file__).resolve().parent
            ps1 = root / "whatsapp_bot" / "start_whatsapp_chrome.ps1"
            if ps1.exists():
                subprocess.Popen(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                    cwd=str(root),
                )
                st.success("Chrome is opening — log in to WhatsApp Web.")
            else:
                st.error("WhatsApp launcher script not found.")
    
    with header_col3:
        if st.button("← Lead Search", use_container_width=True):
            st.session_state.current_page = 'lead_search'
            st.rerun()
    
    st.divider()
    
    # Tab layout
    tab1, tab2, tab3 = st.tabs(["↑ New Campaign", " Statistics", " Message Log"])
    
    # =========================================================================
    # TAB 1: NEW CAMPAIGN BUILDER
    # =========================================================================
    with tab1:
        st.markdown("### Campaign Builder")
        
        campaign_type = st.radio(
            "Campaign Type",
            options=['landlord_lease_expiry', 'cold_owner', 'recent_sale', 'portfolio_owner', 'active_seller', 'active_renter'],
            format_func=lambda x: {
                'landlord_lease_expiry': ' Landlord Lease Expiry',
                'cold_owner': ' Cold Owner Outreach',
                'recent_sale': ' Recent Sale Follow-up',
                'portfolio_owner': ' Portfolio Owner Outreach',
                'active_seller': ' Actively Selling (PropertyFinder)',
                'active_renter': ' Actively Renting (PropertyFinder)'
            }[x]
        )
        
        st.divider()
        
        # Filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            building_filter = st.text_input(
                "Building Filter (optional)",
                placeholder="e.g., Shoreline 12",
                help="Leave empty for all buildings"
            )
        
        with col2:
            bedrooms_filter = st.selectbox(
                "Bedrooms Filter (optional)",
                options=['All', 'Studio', '1', '2', '3', '4', '5', '6']
            )
        
        with col3:
            area_filter = st.selectbox(
                "Area",
                options=['All', 'Palm Jumeirah', 'Dubai Marina', 'JBR'],
                help="Filter by area (building names matched to area)"
            )
        
        # Campaign-specific options
        if campaign_type == 'landlord_lease_expiry':
            days_ahead = st.slider(
                "Lease expiry window (days)",
                min_value=30,
                max_value=180,
                value=90,
                step=30,
                help="Target leases expiring within this many days"
            )
        elif campaign_type == 'recent_sale':
            days_ahead = st.slider(
                "Sales in last (days)",
                min_value=30,
                max_value=180,
                value=90,
                step=30,
                help="Target sales from title deed data in last N days"
            )
        else:
            days_ahead = 90
        
        if campaign_type == 'cold_owner':
            portfolio_only = st.checkbox(
                "Portfolio investors only (2+ units)",
                value=False,
                help="Send only to owners with multiple properties"
            )
            min_units = 3
        elif campaign_type == 'portfolio_owner':
            portfolio_only = False
            min_units = st.slider(
                "Min units per owner",
                min_value=3,
                max_value=10,
                value=3,
                step=1,
                help="Only message owners with at least this many units"
            )
        else:
            portfolio_only = False
            min_units = 3
        
        limit = st.number_input(
            "Limit (optional)",
            min_value=1,
            max_value=500,
            value=None,
            help="Cap queue size for testing"
        )
        
        dry_run = st.checkbox("Dry run (preview only, no messages sent)", value=False, key="wa_dry_run")
        override_limit = st.checkbox("Override limit (skip ramp-up, use full daily cap)", value=False, key="wa_override")
        
        # Single / custom message (e.g. one question to all)
        use_custom_message = st.checkbox(
            "Send one message to all (ignore templates)",
            value=False,
            key="wa_custom_message_mode",
            help="Use when you want to send a single message to everyone in the queue (e.g. 'Do you allow subletting?')"
        )
        custom_message_text = ""
        if use_custom_message:
            custom_message_text = st.text_area(
                "Message to send to every contact",
                value="",
                height=120,
                placeholder="e.g. Do you allow subletting?",
                key="wa_custom_message_text"
            )
        
        # Message templates editor
        from whatsapp_bot.message_templates import get_editable_templates, get_active_template_sets, save_custom_templates
        with st.expander("Message templates (edit and save to use when starting campaign)"):
            st.caption("Placeholders: {name}, {building}, {unit}, {bedrooms}. For portfolio_owner: {name}, {unit_count}, {buildings}.")
            all_templates = get_editable_templates()
            active_sets = get_active_template_sets()
            keys_for_type = (
                ['landlord_lease_expiry'] if campaign_type == 'landlord_lease_expiry' else
                ['cold_owner_single', 'cold_owner_portfolio'] if campaign_type == 'cold_owner' else
                ['recent_sale'] if campaign_type == 'recent_sale' else
                ['portfolio_owner'] if campaign_type == 'portfolio_owner' else
                ['active_seller'] if campaign_type == 'active_seller' else
                ['active_renter']
            )
            if 'wa_extra_template_slots' not in st.session_state:
                st.session_state['wa_extra_template_slots'] = {}
            if 'wa_deleted_template_indices' not in st.session_state:
                st.session_state['wa_deleted_template_indices'] = {}
            edited = dict(all_templates)
            for key in keys_for_type:
                st.subheader(key.replace('_', ' ').title())
                extra = st.session_state['wa_extra_template_slots'].get(key, 0)
                variants = list(all_templates.get(key, [])) + [""] * extra
                deleted_set = st.session_state['wa_deleted_template_indices'].get(key, set())
                new_variants = []  # list of (text, enabled)
                # Determine which variant texts are currently active (saved active subset)
                saved_active = active_sets.get(key, None)  # None means no saved selection → all active
                for i, t in enumerate(variants):
                    if i in deleted_set:
                        continue
                    # Default enabled: True if no saved active set, or if this variant text is in it
                    default_enabled = True if saved_active is None else (t in saved_active)
                    col_check, col_text, col_del = st.columns([1, 10, 1])
                    with col_check:
                        st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
                        enabled = st.checkbox(
                            "Use",
                            value=st.session_state.get(f"tmpl_enabled_{campaign_type}_{key}_{i}", default_enabled),
                            key=f"tmpl_enabled_{campaign_type}_{key}_{i}",
                            help="Include this variant in the random send pool"
                        )
                    with col_text:
                        val = st.text_area(f"Variant {i + 1}", value=t or "", height=120, key=f"tmpl_{campaign_type}_{key}_{i}")
                    with col_del:
                        st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
                        if st.button("Del", key=f"del_variant_{campaign_type}_{key}_{i}", help="Delete this variant"):
                            deleted_set.add(i)
                            st.session_state['wa_deleted_template_indices'][key] = deleted_set
                            st.rerun()
                    new_variants.append((val, enabled))
                # All non-empty variants saved (never lost); active subset saved separately
                all_variants_nonempty = [v for v, _ in new_variants if v.strip()]
                active_variants = [v for v, en in new_variants if en and v.strip()]
                edited[key] = all_variants_nonempty
                edited[f"{key}_active"] = active_variants
                col_add, col_info = st.columns([2, 8])
                with col_add:
                    if st.button("Add variant", key=f"add_variant_{campaign_type}_{key}"):
                        st.session_state['wa_extra_template_slots'][key] = st.session_state['wa_extra_template_slots'].get(key, 0) + 1
                        st.rerun()
                with col_info:
                    total = len(all_variants_nonempty)
                    active_count = len(active_variants)
                    if total > 0:
                        if active_count < total:
                            st.caption(f"{active_count} of {total} variants active for sending.")
                        else:
                            st.caption(f"All {total} variants active for sending.")
            if st.button("Save templates", key="save_templates_btn"):
                if save_custom_templates(edited):
                    st.session_state['wa_extra_template_slots'] = {}
                    st.session_state['wa_deleted_template_indices'] = {}
                    st.success("Templates saved. They will be used when you run the campaign.")
                    st.rerun()
                else:
                    st.error("Failed to save templates.")
        
        st.divider()
        
        # Preview button
        col_preview, col_send = st.columns(2)
        
        with col_preview:
            if st.button(" Preview Queue", type="secondary", use_container_width=True):
                st.session_state['preview_queue'] = True
        
        with col_send:
            if st.button(" Start Campaign", type="primary", use_container_width=True):
                root = Path(__file__).resolve().parent
                cmd = [
                    sys.executable,
                    str(root / "whatsapp_bot" / "run_campaign.py"),
                    "--type", campaign_type,
                    "--days", str(days_ahead),
                ]
                if building_filter:
                    cmd.extend(["--building", building_filter])
                if bedrooms_filter != "All":
                    cmd.extend(["--bedrooms", bedrooms_filter])
                if area_filter and area_filter != "All":
                    cmd.extend(["--area", area_filter])
                if portfolio_only:
                    cmd.append("--portfolio-only")
                if campaign_type == "portfolio_owner" and min_units != 3:
                    cmd.extend(["--min-units", str(min_units)])
                if limit:
                    cmd.extend(["--limit", str(limit)])
                if dry_run:
                    cmd.append("--dry-run")
                if override_limit:
                    cmd.append("--override-limit")
                if use_custom_message and custom_message_text and custom_message_text.strip():
                    custom_msg_file = root / "whatsapp_bot" / "custom_message.txt"
                    custom_msg_file.write_text(custom_message_text.strip(), encoding="utf-8")
                    cmd.extend(["--custom-message-file", "custom_message.txt"])
                flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                cwd_wa = str(root / "whatsapp_bot")
                if sys.platform == "win32":
                    # Keep console open so user can see errors if the script exits
                    subprocess.Popen(
                        ["cmd", "/k", sys.executable] + cmd[1:],
                        cwd=cwd_wa,
                        creationflags=flags,
                    )
                else:
                    subprocess.Popen(cmd, cwd=cwd_wa, creationflags=flags)
                if dry_run:
                    st.success("Dry-run started — watch the new window for the preview.")
                else:
                    st.success("Campaign started — watch the new window for progress.")
        
        with st.expander(" After a restriction"):
            st.caption("If WhatsApp restricted you from new chats, click below to record the date. Cooldown (lower caps + doubled delays for 2 days) will apply for 7 days when you run campaigns again.")
            if st.button("Record restriction date", key="mark_restricted_btn"):
                r = subprocess.run(
                    [sys.executable, "whatsapp_bot/run_campaign.py", "--mark-restricted"],
                    capture_output=True,
                    text=True,
                    cwd=Path(__file__).resolve().parent,
                    timeout=10,
                )
                if r.returncode == 0:
                    st.success("Restriction date recorded. Cooldown will apply for the next 7 days.")
                else:
                    st.error(f"Failed: {r.stderr or r.stdout or 'Unknown error'}")
        
        # Preview
        if st.session_state.get('preview_queue', False):
            st.markdown("---")
            st.markdown("### Queue Preview")
            
            with st.spinner("Building queue..."):
                # Import here to avoid circular imports at module load
                sys.path.insert(0, str(Path(__file__).resolve().parent / 'whatsapp_bot'))
                from whatsapp_bot.campaign_manager import (
                    build_landlord_lease_expiry_queue, build_cold_owner_queue,
                    build_recent_sale_queue, build_portfolio_owner_queue,
                    build_active_seller_queue, build_active_renter_queue,
                    apply_dedup_to_queue, generate_messages_for_queue, shuffle_queue
                )
                
                area_arg = (area_filter if (area_filter and area_filter != 'All') else None)
                # Build queue
                if campaign_type == 'landlord_lease_expiry':
                    queue = build_landlord_lease_expiry_queue(
                        days_ahead=days_ahead,
                        building_filter=building_filter if building_filter else None,
                        bedrooms_filter=bedrooms_filter if bedrooms_filter != 'All' else None,
                        area_filter=area_arg
                    )
                elif campaign_type == 'recent_sale':
                    queue = build_recent_sale_queue(
                        since_days=days_ahead,
                        building_filter=building_filter if building_filter else None,
                        limit=limit if limit else None,
                        area_filter=area_arg
                    )
                elif campaign_type == 'portfolio_owner':
                    queue = build_portfolio_owner_queue(
                        min_units=min_units,
                        building_filter=building_filter if building_filter else None,
                        bedrooms_filter=bedrooms_filter if bedrooms_filter != 'All' else None,
                        limit=limit if limit else None,
                        area_filter=area_arg
                    )
                elif campaign_type == 'active_seller':
                    queue = build_active_seller_queue(
                        building_filter=building_filter if building_filter else None,
                        limit=limit if limit else None,
                        area_filter=area_arg
                    )
                elif campaign_type == 'active_renter':
                    queue = build_active_renter_queue(
                        building_filter=building_filter if building_filter else None,
                        limit=limit if limit else None,
                        area_filter=area_arg
                    )
                else:
                    queue = build_cold_owner_queue(
                        building_filter=building_filter if building_filter else None,
                        bedrooms_filter=bedrooms_filter if bedrooms_filter != 'All' else None,
                        portfolio_only=portfolio_only,
                        limit=limit if limit else None,
                        area_filter=area_arg
                    )
                
                # Apply dedup
                queue = apply_dedup_to_queue(queue, days_window=30)
                
                # Generate messages (or single custom message)
                if use_custom_message and custom_message_text and custom_message_text.strip():
                    msg = custom_message_text.strip()
                    for item in queue:
                        item['message'] = msg
                        item['template_type'] = 'custom'
                else:
                    queue = generate_messages_for_queue(queue)
                
                if not queue:
                    st.warning("Queue is empty after filters and dedup.")
                else:
                    st.success(f"**{len(queue)} messages ready to send**")
                    if use_custom_message and custom_message_text and custom_message_text.strip():
                        st.info("Single message mode: every contact will receive the same text below.")
                    # Show sample messages
                    preview_count = min(5, len(queue))
                    for i, item in enumerate(queue[:preview_count], 1):
                        with st.expander(f"[{i}] {item['owner_name']} — {item['building']} Unit {item['unit']}"):
                            st.text(item['message'])
                            st.caption(f"Phone: {format_phone_for_whatsapp(item['phone'])} | Template: {item['template_type']}")
                    
                    if len(queue) > preview_count:
                        st.info(f"... and {len(queue) - preview_count} more messages")
            
            st.session_state['preview_queue'] = False
    
    # =========================================================================
    # TAB 2: STATISTICS
    # =========================================================================
    with tab2:
        st.markdown("### Send Statistics")
        
        # Today
        stats_today = get_send_stats(days=1)
        reply_today = get_reply_stats(days=1)
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Sent Today", stats_today['sent'])
        col2.metric("Failed", stats_today['failed'])
        col3.metric("Not on WhatsApp", stats_today['not_on_whatsapp'])
        col4.metric("Replies", reply_today['replied'])
        col5.metric("Total", stats_today['total'])
        
        st.divider()
        
        # Last 7 days
        stats_week = get_send_stats(days=7)
        reply_week = get_reply_stats(days=7)
        st.markdown("**Last 7 Days**")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Sent", stats_week['sent'])
        col2.metric("Failed", stats_week['failed'])
        col3.metric("Not on WhatsApp", stats_week['not_on_whatsapp'])
        col4.metric("Replies", reply_week['replied'])
        col5.metric("Total", stats_week['total'])
        
        st.divider()
        
        # All time
        stats_all = get_send_stats(days=None)
        reply_all = get_reply_stats(days=None)
        st.markdown("**All Time**")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Sent", stats_all['sent'])
        col2.metric("Failed", stats_all['failed'])
        col3.metric("Not on WhatsApp", stats_all['not_on_whatsapp'])
        col4.metric("Replies", reply_all['replied'])
        col5.metric("Total", stats_all['total'])
        
        st.caption("Replies are best-effort (detected via WhatsApp Web). Use \"Check for replies\" to scan sent chats.")
        if st.button("Check for replies", help="Open WhatsApp Web and scan recent sent chats for incoming messages. Requires Chrome with WhatsApp already open."):
            import asyncio
            try:
                with st.spinner("Connecting to WhatsApp and checking chats..."):
                    async def run_reply_check():
                        playwright, browser, page = await connect_to_whatsapp()
                        entries = get_sent_entries_for_reply_check(days=90, limit=50)
                        result = await check_replies_for_sent_messages(page, entries, record_reply)
                        await browser.close()
                        return result
                    result = asyncio.run(run_reply_check())
                st.success(f"Checked {result['checked']} chats, found {result['replied']} with replies.")
                if result.get('errors'):
                    st.warning("Some errors: " + "; ".join(result['errors'][:3]))
                st.rerun()
            except Exception as e:
                st.error(f"Reply check failed: {e}. Ensure Chrome is running with WhatsApp Web (e.g. start_whatsapp_chrome.ps1).")
        
        with st.expander("Restrictions and limits"):
            st.markdown(
                "**24h restriction:** WhatsApp may restrict \"new chats\" for ~24 hours. This is enforced by WhatsApp; "
                "there is no workaround in this app. Wait out the period. The built-in rate limiter (daily cap, ramp-up) "
                "helps reduce the chance of being flagged. After a restriction, keep volume low and stay under the daily cap."
            )
    
    # =========================================================================
    # TAB 3: MESSAGE LOG
    # =========================================================================
    with tab3:
        st.markdown("### Recent Messages")
        
        log_limit = st.slider("Show last N messages", min_value=10, max_value=500, value=50, step=10)
        
        messages = get_recent_messages(limit=log_limit)
        
        if not messages:
            st.info("No messages sent yet.")
        else:
            # Convert to DataFrame
            log_df = pd.DataFrame(messages)
            
            # Format for display
            if 'timestamp' in log_df.columns:
                log_df['timestamp'] = pd.to_datetime(log_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Truncate message for display
            if 'message' in log_df.columns:
                log_df['message_preview'] = log_df['message'].str[:60] + '...'
            
            display_cols = [
                'timestamp', 'owner_name', 'building', 'unit', 
                'phone', 'template_type', 'status', 'message_preview'
            ]
            display_cols = [c for c in display_cols if c in log_df.columns]
            
            st.dataframe(
                log_df[display_cols],
                use_container_width=True,
                hide_index=True,
                height=600
            )
            
            # Export button
            csv = log_df.to_csv(index=False, encoding='utf-8')
            st.download_button(
                "↓ Download Full Log CSV",
                data=csv,
                file_name=f"whatsapp_log_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# PF SCRAPER PAGE (PropertyFinder + Replit permit scraper)
# ═══════════════════════════════════════════════════════════════════════════════

def render_pf_scraper_page():
    """Render PropertyFinder + Replit permit scraper page with Chrome launcher, run controls, leads viewer."""
    apply_global_styles()
    root = Path(__file__).resolve().parent
    scraped_data = root / "scraped_data"
    pf_leads_csv = scraped_data / "propertyfinder_scraped_leads.csv"
    pf_progress_json = scraped_data / "pf_scraping_progress.json"

    header_col1, header_col2, header_col3 = st.columns([4, 1.5, 1])
    with header_col1:
        st.title("PropertyFinder Scraper")
        st.caption("Scrape DLD permits from PropertyFinder and look up landlord details via Replit app")
    with header_col2:
        if st.button("Open Chrome", type="primary", use_container_width=True,
                     help="Launch Chrome with PropertyFinder + Replit tabs (debug port 9222)"):
            ps1 = root / "propertyfinder_scraper" / "start_pf_chrome.ps1"
            if ps1.exists():
                subprocess.Popen(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                    cwd=str(root),
                )
                st.success("Chrome is opening. Log in to Replit and set your PropertyFinder search.")
            else:
                st.error("start_pf_chrome.ps1 not found.")
    with header_col3:
        if st.button("Lead Search", use_container_width=True):
            st.session_state.current_page = "lead_search"
            st.rerun()

    st.divider()
    tab1, tab2, tab3 = st.tabs(["Run Scraper", "Scraped Leads", "Progress"])

    with tab1:
        st.markdown("### Run Scraper")
        max_pages = st.slider("Max pages", min_value=1, max_value=20, value=5,
                              help="Max search result pages to process")
        max_listings = st.slider("Max listings", min_value=10, max_value=200, value=50,
                                 help="Max listings to process")
        resume = st.checkbox("Resume from last progress", value=False, key="pf_resume")
        col_start, col_reset = st.columns(2)
        with col_start:
            if st.button("Start Scraper", type="primary", use_container_width=True, key="pf_start"):
                cmd = [
                    sys.executable,
                    str(root / "propertyfinder_scraper" / "scraper.py"),
                    "--max-pages", str(max_pages),
                    "--max-listings", str(max_listings),
                ]
                if resume:
                    cmd.append("--resume")
                flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                cwd_pf = str(root / "propertyfinder_scraper")
                # Launch from project root so script path and log paths match
                cwd_root = str(root)
                full_cmd = ["cmd", "/k", sys.executable] + cmd[1:] if sys.platform == "win32" else cmd
                try:
                    (root / ".cursor").mkdir(parents=True, exist_ok=True)
                    with open(root / ".cursor" / "streamlit_launch.log", "a", encoding="utf-8") as f:
                        f.write(json.dumps({"cwd": cwd_root, "full_cmd": full_cmd, "scraper_path": cmd[1]}) + "\n")
                except Exception:
                    pass
                if sys.platform == "win32":
                    subprocess.Popen(
                        ["cmd", "/k", sys.executable] + cmd[1:],
                        cwd=cwd_root,
                        creationflags=flags,
                    )
                else:
                    subprocess.Popen(cmd, cwd=cwd_root, creationflags=flags)
                st.success("Scraper started in a new window. Press Enter there when ready.")
        with col_reset:
            if st.button("Reset Progress", use_container_width=True, key="pf_reset"):
                if pf_progress_json.exists():
                    try:
                        pf_progress_json.unlink()
                        st.success("Progress reset.")
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("No progress file to reset.")

    with tab2:
        st.markdown("### Scraped Leads")
        if pf_leads_csv.exists():
            try:
                try:
                    leads_df = pd.read_csv(pf_leads_csv, encoding="utf-8", low_memory=False, on_bad_lines="skip")
                except TypeError:
                    leads_df = pd.read_csv(pf_leads_csv, encoding="utf-8", low_memory=False, engine="python")
                st.caption(f"{len(leads_df)} rows")
                st.dataframe(leads_df, use_container_width=True, height=400)
                st.download_button(
                    "Download CSV",
                    data=leads_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"propertyfinder_scraped_leads_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="pf_download",
                )
            except Exception as e:
                st.error(str(e))
            if 'pf_clear_confirm' not in st.session_state:
                st.session_state['pf_clear_confirm'] = False
            if st.button("Clear Leads", key="pf_clear"):
                st.session_state['pf_clear_confirm'] = True
            if st.session_state.get('pf_clear_confirm'):
                row_count = len(pd.read_csv(pf_leads_csv)) if pf_leads_csv.exists() else 0
                st.warning(f"⚠ This will permanently delete **{row_count} rows**. A backup will be saved first.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✓ Yes, clear leads", key="pf_clear_yes", type="primary"):
                        try:
                            from datetime import datetime as _dt
                            backup_path = pf_leads_csv.with_suffix(f".backup_{_dt.now().strftime('%Y%m%d_%H%M%S')}.csv")
                            import shutil
                            shutil.copy2(pf_leads_csv, backup_path)
                            headers = "unit_number,building_name,zone,size_sqm,land_no,owner_name,phone,property_value,room_type,permit_type,listing_url,listing_price,listing_type,furnished,scraped_at\n"
                            pf_leads_csv.write_text(headers, encoding="utf-8")
                            st.session_state['pf_clear_confirm'] = False
                            st.success(f"Leads cleared. Backup saved as {backup_path.name}")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with col_no:
                    if st.button("✕ Cancel", key="pf_clear_no"):
                        st.session_state['pf_clear_confirm'] = False
                        st.rerun()
        else:
            st.info("No scraped leads file yet. Run the scraper first.")

    with tab3:
        st.markdown("### Progress")
        if pf_progress_json.exists():
            try:
                data = json.loads(pf_progress_json.read_text(encoding="utf-8"))
                st.metric("Total saved", data.get("total_saved", 0))
                st.metric("URLs processed", len(data.get("processed_urls", [])))
                st.caption(f"Last updated: {data.get('last_updated', '—')}")
            except Exception as e:
                st.error(str(e))
        else:
            st.info("No progress file yet.")


# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTY MONITOR SCRAPER PAGE (Rental + Unit Number scrapers)
# ═══════════════════════════════════════════════════════════════════════════════

def render_property_monitor_page():
    """Render Property Monitor scrapers page: rental scraper and unit number scraper."""
    apply_global_styles()
    root = Path(__file__).resolve().parent
    scraped_data = root / "scraped_data"
    rental_csv = scraped_data / "palm_jumeirah_rentals.csv"
    rental_progress = scraped_data / "rental_scraping_progress.json"
    unit_csv = scraped_data / "unit_numbers_palm_jumeirah.csv"
    unit_progress = scraped_data / "scraping_progress.json"

    header_col1, header_col2, header_col3 = st.columns([4, 1.5, 1])
    with header_col1:
        st.title("Property Monitor Scrapers")
        st.caption("Rental (Ejari) and unit number scrapers — use Chrome on port 9222")
    with header_col2:
        if st.button("Open Chrome", type="primary", use_container_width=True, key="pm_open_chrome",
                     help="Launch Chrome with remote debugging (port 9222) for Property Monitor"):
            cmd = [
                sys.executable, "-c",
                "import sys; sys.path.insert(0, '.'); from property_research_agent.rental_scraper import launch_chrome_with_debugging; launch_chrome_with_debugging()",
            ]
            try:
                subprocess.Popen(cmd, cwd=str(root))
                st.success("Chrome is opening. Log in to Property Monitor and set your filters.")
            except Exception as e:
                st.error(str(e))
    with header_col3:
        if st.button("Lead Search", use_container_width=True, key="pm_lead_search"):
            st.session_state.current_page = "lead_search"
            st.rerun()

    st.warning("Only one Chrome instance can use port 9222 at a time. Close Chrome between different scraper runs if needed.")
    st.divider()

    with st.expander(" Instructions", expanded=False):
        st.markdown("""
1. **Open Chrome** (button above) — logs in and passes Cloudflare stay in this session.
2. **Property Monitor:** Go to Rentals (or your search), set location (e.g. Palm Jumeirah), date range, per page = 250.
3. **Run** the scraper you need (Rental or Unit Number). A new console window opens; press **Enter** there when ready.
4. Scraped data appears below and is used by Lease Expiry and HLM.
        """)

    # ── Rental Scraper ───────────────────────────────────────────────────────
    with st.expander(" Rental Scraper (Ejari)", expanded=True):
        st.caption("Output: palm_jumeirah_rentals.csv (or palm_jumeirah_rentals_shoreline.csv with Shoreline only)")
        shoreline = st.checkbox("Shoreline only", value=False, key="pm_rental_shoreline",
                                help="Set Property Monitor filter to Shoreline Apartments; output goes to palm_jumeirah_rentals_shoreline.csv")
        test_mode = st.checkbox("Test (2 pages only)", value=False, key="pm_rental_test")
        col_start, col_reset = st.columns(2)
        with col_start:
            if st.button("Start Rental Scraper", type="primary", use_container_width=True, key="pm_rental_start"):
                cmd = [sys.executable, str(root / "property_research_agent" / "rental_scraper.py")]
                if shoreline:
                    cmd.append("--shoreline-only")
                if test_mode:
                    cmd.append("--test")
                flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                full_cmd = (["cmd", "/k", sys.executable] + cmd[1:]) if sys.platform == "win32" else cmd
                try:
                    subprocess.Popen(full_cmd, cwd=str(root), creationflags=flags)
                    st.success("Rental scraper started in a new window. Press Enter there when ready.")
                except Exception as e:
                    st.error(str(e))
        with col_reset:
            if st.button("Reset Rental Progress", use_container_width=True, key="pm_rental_reset"):
                if rental_progress.exists():
                    try:
                        rental_progress.unlink()
                        st.success("Rental progress reset.")
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("No rental progress file to reset.")
        if rental_csv.exists():
            try:
                mtime = datetime.fromtimestamp(rental_csv.stat().st_mtime)
                st.caption(f"Last updated: {mtime.strftime('%Y-%m-%d %H:%M')}")
                df = pd.read_csv(rental_csv, encoding="utf-8", low_memory=False)
                st.dataframe(df.head(500), use_container_width=True, height=300)
                st.download_button("Download Rental CSV", data=rental_csv.read_text(encoding="utf-8"),
                                  file_name=f"palm_jumeirah_rentals_{datetime.now().strftime('%Y%m%d')}.csv",
                                  mime="text/csv", key="pm_rental_dl")
            except Exception as e:
                st.error(str(e))
        else:
            st.info("No rental CSV yet. Run the rental scraper first.")

    # ── Unit Number Scraper ───────────────────────────────────────────────────
    with st.expander(" Unit Number Scraper", expanded=True):
        st.caption("Output: unit_numbers_palm_jumeirah.csv")
        col_start, col_reset = st.columns(2)
        with col_start:
            if st.button("Start Unit Scraper", type="primary", use_container_width=True, key="pm_unit_start"):
                cmd = [sys.executable, str(root / "property_research_agent" / "unit_number_scraper.py")]
                flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
                full_cmd = (["cmd", "/k", sys.executable] + cmd[1:]) if sys.platform == "win32" else cmd
                try:
                    subprocess.Popen(full_cmd, cwd=str(root), creationflags=flags)
                    st.success("Unit scraper started in a new window. Press Enter there when ready.")
                except Exception as e:
                    st.error(str(e))
        with col_reset:
            if st.button("Reset Unit Progress", use_container_width=True, key="pm_unit_reset"):
                if unit_progress.exists():
                    try:
                        unit_progress.unlink()
                        st.success("Unit progress reset.")
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("No unit progress file to reset.")
        if unit_csv.exists():
            try:
                mtime = datetime.fromtimestamp(unit_csv.stat().st_mtime)
                st.caption(f"Last updated: {mtime.strftime('%Y-%m-%d %H:%M')}")
                df = pd.read_csv(unit_csv, encoding="utf-8", low_memory=False)
                st.dataframe(df.head(500), use_container_width=True, height=300)
                st.download_button("Download Unit CSV", data=unit_csv.read_text(encoding="utf-8"),
                                  file_name=f"unit_numbers_palm_jumeirah_{datetime.now().strftime('%Y%m%d')}.csv",
                                  mime="text/csv", key="pm_unit_dl")
            except Exception as e:
                st.error(str(e))
        else:
            st.info("No unit CSV yet. Run the unit scraper first.")


# ═══════════════════════════════════════════════════════════════════════════════
# AI CHAT PAGE (ChatGPT-Style)
# ═══════════════════════════════════════════════════════════════════════════════

def render_ai_chat_page():
    """Render full-page ChatGPT-style AI interface."""
    apply_global_styles()
    apply_ai_page_styles()
    
    # Load data for AI
    with st.spinner("Loading data..."):
        df, _ = load_data(_pf_mtime=_pf_csv_mtime(), _pq_mtime=_parquet_mtime())
        reference_df = get_reference_data()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SIDEBAR - Chat History (Left side, like ChatGPT)
    # ═══════════════════════════════════════════════════════════════════════════
    
    with st.sidebar:
        st.markdown("##  Chats")
        
        # Back button
        if st.button("← Back to Lead Search", use_container_width=True):
            st.session_state.current_page = 'lead_search'
            st.rerun()
        
        # Query usage indicator
        if 'query_count_today' in st.session_state:
            remaining = 100 - st.session_state.query_count_today
            st.caption(f" Queries today: {st.session_state.query_count_today}/100")
            if remaining < 20:
                st.caption(f"⚠ {remaining} queries remaining")
        
        st.divider()
        
        # New Chat button
        if st.button("+ New Chat", use_container_width=True, type="primary"):
            new_chat_id = cm.create_new_chat("New Chat")
            st.session_state.current_chat_id = new_chat_id
            st.rerun()
        
        st.divider()
        
        # List all chats
        all_chats = cm.get_all_chats()
        
        if all_chats:
            for chat in all_chats:
                is_active = (chat['id'] == st.session_state.current_chat_id)
                
                col1, col2, col3 = st.columns([5, 1, 1])
                
                with col1:
                    name = chat['name'][:22] + "..." if len(chat['name']) > 22 else chat['name']
                    icon = "🟢" if is_active else "⚪"
                    btn_type = "primary" if is_active else "secondary"
                    
                    if st.button(f"{icon} {name}", key=f"chat_{chat['id']}", 
                               use_container_width=True, type=btn_type):
                        st.session_state.current_chat_id = chat['id']
                        st.rerun()
                
                with col2:
                    if st.button("Rename", key=f"rename_{chat['id']}", help="Rename"):
                        st.session_state[f'renaming_{chat["id"]}'] = True
                        st.rerun()
                
                with col3:
                    if st.button("Del", key=f"delete_{chat['id']}", help="Delete"):
                        cm.delete_chat(chat['id'])
                        remaining = cm.get_all_chats()
                        if remaining:
                            st.session_state.current_chat_id = remaining[0]['id']
                        else:
                            st.session_state.current_chat_id = cm.create_new_chat("General Inquiry")
                        st.rerun()
                
                # Rename dialog
                if st.session_state.get(f'renaming_{chat["id"]}', False):
                    new_name = st.text_input("New name:", value=chat['name'], 
                                            key=f"rename_input_{chat['id']}")
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save", key=f"save_{chat['id']}"):
                            cm.rename_chat(chat['id'], new_name)
                            st.session_state[f'renaming_{chat["id"]}'] = False
                            st.rerun()
                    with col_cancel:
                        if st.button("Cancel", key=f"cancel_{chat['id']}"):
                            st.session_state[f'renaming_{chat["id"]}'] = False
                            st.rerun()
                
                st.caption(f" {chat['message_count']} msgs")
                st.divider()
        else:
            st.info("No chats yet")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN CHAT AREA (Center)
    # ═══════════════════════════════════════════════════════════════════════════
    
    current_chat = cm.load_chat(st.session_state.current_chat_id)
    
    if not current_chat:
        st.session_state.current_chat_id = cm.create_new_chat("General Inquiry")
        current_chat = cm.load_chat(st.session_state.current_chat_id)
        st.rerun()
    
    # Header
    header_col1, header_col2, header_col3 = st.columns([5, 1, 1])
    
    with header_col1:
        st.title(f" {current_chat['name']}")
        st.caption("AI-powered property intelligence • Claude Sonnet 4")
    
    with header_col2:
        exported = cm.export_chat_as_text(st.session_state.current_chat_id)
        if exported:
            st.download_button("↓ Export", data=exported,
                             file_name=f"{current_chat['name']}.txt",
                             mime="text/plain", use_container_width=True)
    
    with header_col3:
        if st.button(" Clear", key="clear_chat", use_container_width=True):
            cm.clear_chat_messages(st.session_state.current_chat_id)
            st.rerun()
    
    st.divider()
    
    # Chat area in keyed container so Streamlit can tear it down when leaving the page
    with st.container(key="ai_chat_container"):
        # Messages
        messages = cm.get_chat_messages(st.session_state.current_chat_id)
        
        if not messages:
            # Welcome message
            st.markdown("""
            ### Welcome to HLM - Palm Jumeirah Intelligence
            
            **Example queries:**
            
            | Type | Example |
            |------|---------|
            | Pricing | "Average price for 2-beds in Oceana" |
            | With contacts | "Last 10 Fairmont sales where you know the owner" |
            | Market | "Recent sales in Seven Palm" |
            | Investors | "Find portfolio investors in Marina Residences" |
            | Owner lookup | "Find everything about [owner name]" |
            | Call list | "Give me contacts for Shoreline 5" |
            
            **Data:** 18,250+ title deed transactions with unit numbers | 28,000+ owner contacts | Cross-referencing enabled
            """)
        else:
            for msg in messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        # Chat input (keyed so it unmounts when not on AI page)
        user_query = st.chat_input("Ask about properties, pricing, owners, or market trends...", key="hlm_chat_input")
    
    if user_query:
        cm.add_message_to_chat(st.session_state.current_chat_id, "user", user_query)
        
        with st.chat_message("user"):
            st.markdown(user_query)
        
        # Rate limiting
        import time
        if 'last_query_time' not in st.session_state:
            st.session_state.last_query_time = 0
        if 'query_count_today' not in st.session_state:
            st.session_state.query_count_today = 0
            st.session_state.query_count_reset_date = datetime.now().date()
        if datetime.now().date() != st.session_state.query_count_reset_date:
            st.session_state.query_count_today = 0
            st.session_state.query_count_reset_date = datetime.now().date()
        current_time = time.time()
        time_since_last = current_time - st.session_state.last_query_time
        COOLDOWN_SECONDS = 2
        if time_since_last < COOLDOWN_SECONDS:
            wait_time = COOLDOWN_SECONDS - time_since_last
            with st.chat_message("assistant"):
                st.warning(f"⏳ Please wait {int(wait_time + 1)} seconds before sending another query...")
            st.stop()
        DAILY_LIMIT = 100
        if st.session_state.query_count_today >= DAILY_LIMIT:
            with st.chat_message("assistant"):
                st.error(f" Daily query limit reached ({DAILY_LIMIT} queries). Resets at midnight.")
                st.info("This limit prevents excessive API usage. Contact admin to increase.")
            st.stop()
        st.session_state.last_query_time = current_time
        st.session_state.query_count_today += 1
        
        with st.chat_message("assistant"):
            with st.spinner(" Analyzing..."):
                chat_history = cm.get_chat_messages(st.session_state.current_chat_id)
                response = query_leads_with_ai(user_query, df, reference_df, chat_history)
                st.markdown(response)
                cm.add_message_to_chat(st.session_state.current_chat_id, "assistant", response)
        
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# LISTING MATCHER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def _load_matcher_leads():
    """Load leads_master (Parquet preferred) for the matching engine (cached 10 min)."""
    try:
        from listing_matcher.matcher import load_leads_df
        return load_leads_df()
    except Exception:
        return pd.DataFrame()


def _confidence_badge(conf: float) -> str:
    if conf >= 0.9:
        return "🟢"
    if conf >= 0.6:
        return "🟡"
    return "🔴"


def _clean_beds_from_dld(beds_str: str) -> str | None:
    """Convert DLD bedroom format to matcher format.
    '2 B/R' -> '2', 'Studio' -> 'Studio', 'Penthouse' -> 'PH'
    """
    if not beds_str:
        return None
    s = beds_str.strip()
    if "studio" in s.lower():
        return "Studio"
    if "penthouse" in s.lower() or s.lower() == "ph":
        return "PH"
    m = re.search(r"(\d+)", s)
    if m:
        return m.group(1)
    return s


def _get_shoreline_display_name(building_name: str) -> str:
    """Al Hallawi -> Al Hallawi (Shoreline 10)"""
    try:
        from building_intelligence import SHORELINE_TOWER_MAPPING
        for tower_name, (number, _aliases) in SHORELINE_TOWER_MAPPING.items():
            if tower_name.lower() == building_name.lower():
                return f"{building_name} (Shoreline {number})"
    except ImportError:
        pass
    return building_name


def _render_match_card(m: dict, idx: int):
    conf = m["confidence"]
    badge = _confidence_badge(conf)
    match_label = {
        "exact_unit":  "Exact Unit",
        "exact_size":  "Size Match",
        "beds_range":  "Beds + Size Range",
    }.get(m.get("match_type", ""), m.get("match_type", ""))

    with st.container(border=True):
        col_info, col_actions = st.columns([4, 1])
        with col_info:
            size_str = f"{m['size_sqft']:.0f} sqft" if m.get('size_sqft') else '—'
            st.markdown(
                f"**{badge} {conf*100:.0f}% confidence** — {match_label}  \n"
                f"**Unit:** {m['unit'] or '—'} &nbsp;|&nbsp; **Building:** {m['building']}  \n"
                f"**Owner:** {m['owner_name'] or 'Unknown'}  \n"
                f"**Phone:** `{m['phone_display'] or 'Not in database'}`  \n"
                f"**Size:** {size_str} &nbsp;|&nbsp; "
                f"**Beds:** {m['beds'] or '—'}  \n"
                f"**Last Tx:** {m['transaction_date'] or '—'} &nbsp;|&nbsp; "
                f"**Value:** {m['transaction_value'] or '—'}  \n"
                f"**Source:** {m['source_file'] or '—'}"
            )
        with col_actions:
            phone_raw = m.get("phone", "")
            if phone_raw:
                wa_number = phone_raw.lstrip("+")
                st.link_button(" WhatsApp", f"https://wa.me/{wa_number}", use_container_width=True)
                if st.button(" Copy", key=f"copy_match_{idx}", use_container_width=True):
                    st.session_state[f"_copy_match_{idx}"] = (
                        f"{m['owner_name']} | {m['building']} {m['unit']} | {phone_raw}"
                    )
                if st.session_state.get(f"_copy_match_{idx}"):
                    st.code(st.session_state[f"_copy_match_{idx}"])
            else:
                st.caption("No phone")

            if st.button(" Queue WA", key=f"queue_wa_{idx}", use_container_width=True,
                         help="Add to WhatsApp campaign queue"):
                st.session_state["_wa_queue_pending"] = m
                st.toast(f"Queued: {m['owner_name']} ({m['building']} {m['unit']})", icon="✓")


def render_listing_matcher_page():
    """ Listing Matcher — match portal listings to owners in the lead database."""
    apply_global_styles()

    st.title(" Listing Matcher")
    st.caption("Match Bayut / PropertyFinder listings to owners in your database — no third-party lookup fees.")

    if st.button("← Back", key="matcher_back"):
        st.session_state.current_page = "lead_search"
        st.rerun()

    st.divider()

    # ── Load data ──────────────────────────────────────────────────────────────
    with st.spinner("Loading lead database…"):
        leads_df = _load_matcher_leads()

    if leads_df.empty:
        st.error(
            "Lead database not found at `lead_database/leads_master.csv`. "
            "Run `python consolidate_data.py` first."
        )
        return

    from listing_matcher.matcher import match_listing, analyze_coverage, normalize_beds

    # ── Coverage stats in sidebar ─────────────────────────────────────────────
    with st.sidebar:
        st.subheader(" Database Coverage")
        try:
            cov = analyze_coverage(leads_df)
            st.metric("Total unique units", f"{cov['total_units']:,}")
            st.metric("Units with phone", f"{cov['with_phone']:,} ({cov['phone_pct']}%)")
            st.metric("Units with size", f"{cov['with_size']:,} ({cov['size_pct']}%)")
            st.caption(f"Total records: {len(leads_df):,}")
        except Exception:
            st.caption(f"Records: {len(leads_df):,}")

        st.divider()
        conf_threshold = st.slider(
            "Min confidence to show",
            min_value=0, max_value=100, value=40, step=5,
            help="Filter out low-confidence matches",
            key="matcher_conf_threshold",
        )

    # ── Session state for Permit Lookup ──────────────────────────────────────
    if "last_dld_result" not in st.session_state:
        st.session_state.last_dld_result = None
    if "last_owner_matches" not in st.session_state:
        st.session_state.last_owner_matches = None
    if "lookup_history" not in st.session_state:
        st.session_state.lookup_history = []

    tab_permit, tab_manual, tab_batch, tab_coverage = st.tabs(
        [" Permit Lookup", " Manual Lookup", " Batch CSV", " Coverage Stats"]
    )

    # ════════════════════════════════════════════════════════════════════════════
    # TAB 0: PERMIT LOOKUP (primary workflow)
    # ════════════════════════════════════════════════════════════════════════════
    with tab_permit:
        st.subheader(" Permit Lookup")
        st.caption(
            "Paste a Madmoun GUID or Trakheesi URL — get verified property details "
            "from the DLD and the owner's phone number from your lead database. ~20 seconds."
        )

        guid_input_permit = st.text_input(
            "Paste Madmoun GUID, Trakheesi URL, or Bayut listing URL:",
            placeholder="gc2hzdo7t8plgx47pfisx1h5mhuf3wfsbw3kujydscuhchrrn",
            key="permit_lookup_input",
        )
        st.caption(
            "Find the GUID on any Bayut / PropertyFinder listing — tap the "
            "Trakheesi / Madmoun QR code or validation link."
        )

        col_btn, col_retry = st.columns([3, 1])
        with col_btn:
            do_permit_lookup = st.button(
                " Find Owner", type="primary", use_container_width=True, key="permit_lookup_btn"
            )
        with col_retry:
            do_retry = st.button(
                "↺ Retry", use_container_width=True, key="permit_retry_btn",
                help="Re-run the last lookup",
            )

        st.divider()

        # ── Execute lookup ────────────────────────────────────────────────────
        _should_run = False
        _raw_input = ""

        if do_permit_lookup and guid_input_permit.strip():
            _should_run = True
            _raw_input = guid_input_permit.strip()
        elif do_retry and st.session_state.last_dld_result:
            _should_run = True
            _raw_input = st.session_state.last_dld_result.get("guid", "")

        if do_permit_lookup and not guid_input_permit.strip():
            st.error(
                "Could not extract a valid GUID from your input. Please paste:\n"
                "- A Madmoun GUID (long alphanumeric string)\n"
                "- A Trakheesi validation URL\n"
                "- A Bayut listing URL with Madmoun QR link"
            )

        if _should_run and _raw_input:
            from scraper.dld_validator import validate_listing as _pv_validate, extract_guid_from_url as _pv_extract

            guid = _pv_extract(_raw_input) or _raw_input.strip()

            if not guid or len(guid) < 10:
                st.error(
                    "Could not extract a valid GUID from your input. Please paste:\n"
                    "- A Madmoun GUID (long alphanumeric string)\n"
                    "- A Trakheesi validation URL\n"
                    "- A Bayut listing URL with Madmoun QR link"
                )
            else:
                dld_result = None
                with st.status("Resolving listing via DLD...", expanded=True) as _pstatus:
                    st.write("⏳ Opening browser & executing reCAPTCHA (~5-10 seconds)...")
                    dld_result = _pv_validate(guid)
                    if dld_result["success"]:
                        st.write("✓ Property details received from DLD")
                        _pstatus.update(label="✓ Property resolved", state="complete")
                    else:
                        st.write(f"✕ {dld_result['error']}")
                        _pstatus.update(label="✕ Lookup failed", state="error")

                st.session_state.last_dld_result = dld_result
                st.session_state.last_owner_matches = None

                if dld_result and dld_result["success"]:
                    beds_clean = _clean_beds_from_dld(dld_result["beds"])
                    listing_for_matcher = {
                        "building_name": dld_result["building"],
                        "size_sqft": dld_result["size_sqft"] if dld_result["size_sqft"] else None,
                        "bedrooms": beds_clean,
                    }
                    try:
                        _perm_leads = _load_matcher_leads()
                        if not _perm_leads.empty:
                            _perm_matches = match_listing(listing_for_matcher, _perm_leads)
                            min_c = conf_threshold / 100.0
                            _perm_matches = [r for r in _perm_matches if r["confidence"] >= min_c]
                            st.session_state.last_owner_matches = _perm_matches
                        else:
                            st.session_state.last_owner_matches = []
                    except Exception as _me:
                        st.session_state.last_owner_matches = []
                        st.error(f"Owner lookup error: {_me}")

                    # Add to history
                    from datetime import datetime as _dt
                    top_match = (st.session_state.last_owner_matches or [None])[0]
                    st.session_state.lookup_history.append({
                        "time": _dt.now().strftime("%H:%M:%S"),
                        "guid": guid[:20] + "...",
                        "building": dld_result["building"],
                        "beds": dld_result["beds"],
                        "owner": top_match["owner_name"] if top_match else "No match",
                        "phone": top_match.get("phone_display", "N/A") if top_match else "N/A",
                    })

        # ── Display stored result ─────────────────────────────────────────────
        dld_res = st.session_state.last_dld_result

        if dld_res and dld_res.get("success"):
            # ── Property card ─────────────────────────────────────────────────
            display_building = _get_shoreline_display_name(dld_res["building"])
            start_d = dld_res["permit_start"][:10] if dld_res["permit_start"] else "N/A"
            end_d = dld_res["permit_end"][:10] if dld_res["permit_end"] else "N/A"

            with st.container(border=True):
                st.markdown("####  PROPERTY")
                c1, c2 = st.columns(2)
                c1.markdown(
                    f"**Building:** {display_building}  \n"
                    f"**Zone:** {dld_res['zone']}  \n"
                    f"**Size:** {dld_res['size_sqm']} sqm / {dld_res['size_sqft']:,.0f} sqft  \n"
                    f"**Bedrooms:** {dld_res['beds'] or '—'}  \n"
                )
                c2.markdown(
                    f"**Type:** {dld_res['permit_type']} | AED {dld_res['value']:,.0f}  \n"
                    f"**Agency:** {dld_res['agency']}  \n"
                    f"**Permit:** {dld_res['permit_number']} | Valid until {end_d}  \n"
                    f"**Status:** {dld_res['permit_status']}  \n"
                )

            if dld_res["zone"] and "palm jumeirah" not in dld_res["zone"].lower():
                st.info(
                    f"Note: This property is in **{dld_res['zone']}**, not Palm Jumeirah. "
                    "Lead database coverage may be limited for this area."
                )

            with st.expander(" Full permit details", expanded=False):
                st.markdown(
                    f"**Building (AR):** {dld_res['building_ar']}  \n"
                    f"**DLD Listing #:** {dld_res['listing_number']}  \n"
                    f"**License #:** {dld_res['license_number']}  \n"
                    f"**Floor:** {dld_res['floor'] or 'N/A'}  \n"
                    f"**Valid:** {start_d} → {end_d}  \n"
                    f"**GUID:** `{dld_res['guid']}`"
                )

            st.divider()

            # ── Owner matches ─────────────────────────────────────────────────
            matches = st.session_state.last_owner_matches or []

            if matches:
                st.markdown("####  OWNER (from lead database)")
                for _i, _m in enumerate(matches):
                    _render_match_card(_m, idx=8000 + _i)
            else:
                st.warning("Property found but no matching owner in your lead database.")
                st.info(
                    "This means the owner's contact info isn't in your 18.7K lead files. "
                    "You can still use the property details (building, size, beds) to search "
                    "manually on the **Manual Lookup** tab."
                )

        elif dld_res and not dld_res.get("success"):
            st.error(f"DLD lookup failed: {dld_res['error']}")
            st.info(
                "Try again — the browser automation can occasionally fail. "
                "If persistent, the GUID may be invalid or expired."
            )

        # ── Lookup history ────────────────────────────────────────────────────
        with st.expander(f" Lookup History ({len(st.session_state.lookup_history)} lookups)"):
            if st.session_state.lookup_history:
                st.dataframe(
                    pd.DataFrame(st.session_state.lookup_history),
                    use_container_width=True,
                )
            else:
                st.info("No lookups yet")

    # ════════════════════════════════════════════════════════════════════════════
    # TAB 1: MANUAL LOOKUP
    # ════════════════════════════════════════════════════════════════════════════
    with tab_manual:
        st.subheader("Find owner for a specific listing")

        col_form, col_results = st.columns([1, 1], gap="large")

        with col_form:
            with st.form("matcher_form"):
                # Building: text input with autocomplete-like helper
                all_buildings = sorted(
                    str(b) for b in leads_df["Building Name"].dropna().unique()
                ) if "Building Name" in leads_df.columns else []
                building_input = st.text_input(
                    "Building name",
                    placeholder="e.g. Shoreline 10, Al Hallawi, Ellington Beach House",
                    key="matcher_building",
                )
                beds_input = st.selectbox(
                    "Bedrooms",
                    options=["(any)", "Studio", "1", "2", "3", "4", "5", "PH"],
                    key="matcher_beds",
                )
                size_input = st.number_input(
                    "Size (sqft)",
                    min_value=0.0, value=0.0, step=1.0,
                    help="Leave 0 to skip size matching",
                    key="matcher_size",
                )
                unit_input = st.text_input(
                    "Unit number (optional)",
                    placeholder="e.g. 1101, S-607, PH06",
                    key="matcher_unit",
                )
                url_input = st.text_input(
                    "Listing URL (optional — for reference only)",
                    placeholder="https://www.bayut.com/…",
                    key="matcher_url",
                )
                submitted = st.form_submit_button(" Find Owner", type="primary", use_container_width=True)

        with col_results:
            if submitted and building_input.strip():
                listing = {
                    "building_name": building_input.strip(),
                    "unit_number":   unit_input.strip() or None,
                    "size_sqft":     float(size_input) if size_input and size_input > 0 else None,
                    "bedrooms":      beds_input if beds_input != "(any)" else None,
                    "listing_url":   url_input.strip() or None,
                }

                with st.spinner("Matching…"):
                    results = match_listing(listing, leads_df)

                # Filter by confidence threshold
                min_conf = conf_threshold / 100.0
                results = [r for r in results if r["confidence"] >= min_conf]

                if not results:
                    st.warning(
                        "No matches found. Try:\n"
                        "- Lowering the confidence threshold in the sidebar\n"
                        "- Checking the building name (portal names differ from DLD names)\n"
                        "- Adding a size or unit number"
                    )
                else:
                    st.success(f"**{len(results)} match{'es' if len(results) != 1 else ''} found**")
                    for i, m in enumerate(results):
                        _render_match_card(m, i)
            elif submitted:
                st.info("Enter a building name to search.")
            else:
                st.info("Fill in the form and click **Find Owner** to search.")

                # Show building suggestions while idle
                if all_buildings:
                    with st.expander("Browse buildings in database", expanded=False):
                        filter_text = st.text_input("Filter buildings", key="bld_filter_manual")
                        shown = [b for b in all_buildings if filter_text.lower() in b.lower()] if filter_text else all_buildings[:50]
                        for b in shown[:60]:
                            st.caption(b)

    # ════════════════════════════════════════════════════════════════════════════
    # TAB 2: BATCH CSV UPLOAD
    # ════════════════════════════════════════════════════════════════════════════
    with tab_batch:
        st.subheader("Match a CSV of listings")
        st.caption(
            "Upload a CSV exported from Bayut / PF or typed manually. "
            "Required column: `building`. Optional: `beds`, `size_sqft`, `unit_number`, `price`, `url`."
        )

        uploaded = st.file_uploader(
            "Upload listings CSV",
            type=["csv", "tsv", "txt"],
            key="matcher_batch_upload",
        )

        if uploaded:
            try:
                raw = uploaded.read().decode("utf-8", errors="replace")
                # Auto-detect delimiter
                import csv as _csv
                dialect = _csv.Sniffer().sniff(raw[:2048], delimiters=",;\t|")
                import io
                batch_df = pd.read_csv(io.StringIO(raw), sep=dialect.delimiter, dtype=str)
            except Exception as e:
                st.error(f"Could not read CSV: {e}")
                batch_df = pd.DataFrame()

            if not batch_df.empty:
                st.write(f"**{len(batch_df)} listings loaded** — preview:")
                st.dataframe(batch_df.head(5), use_container_width=True)

                # Column mapping
                cols = ["(none)"] + list(batch_df.columns)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    col_building = st.selectbox("Building column", cols, index=next((i for i, c in enumerate(cols) if "building" in c.lower()), 0), key="batch_col_building")
                with c2:
                    col_beds = st.selectbox("Beds column", cols, index=next((i for i, c in enumerate(cols) if "bed" in c.lower()), 0), key="batch_col_beds")
                with c3:
                    col_size = st.selectbox("Size (sqft) column", cols, index=next((i for i, c in enumerate(cols) if "size" in c.lower()), 0), key="batch_col_size")
                with c4:
                    col_unit = st.selectbox("Unit number column", cols, index=next((i for i, c in enumerate(cols) if "unit" in c.lower()), 0), key="batch_col_unit")

                if col_building == "(none)":
                    st.warning("Select the building column to proceed.")
                else:
                    if st.button(" Match All", type="primary", key="batch_match_btn"):
                        min_conf = conf_threshold / 100.0
                        output_rows = []
                        progress = st.progress(0)
                        total = len(batch_df)

                        for i, row in batch_df.iterrows():
                            bld = str(row.get(col_building, "") or "").strip()
                            if not bld:
                                continue
                            listing = {
                                "building_name": bld,
                                "size_sqft":   (
                                    float(str(row[col_size]).replace(",", "").strip())
                                    if col_size != "(none)" and pd.notna(row.get(col_size))
                                    else None
                                ),
                                "bedrooms":    str(row[col_beds]).strip() if col_beds != "(none)" and pd.notna(row.get(col_beds)) else None,
                                "unit_number": str(row[col_unit]).strip() if col_unit != "(none)" and pd.notna(row.get(col_unit)) else None,
                            }
                            try:
                                matches = match_listing(listing, leads_df)
                                matches = [m for m in matches if m["confidence"] >= min_conf]
                            except Exception:
                                matches = []

                            if matches:
                                best = matches[0]
                                output_rows.append({
                                    **{c: row.get(c, "") for c in batch_df.columns},
                                    "match_building":    best["building"],
                                    "match_unit":        best["unit"],
                                    "match_owner":       best["owner_name"],
                                    "match_phone":       best["phone_display"],
                                    "match_confidence":  f"{best['confidence']*100:.0f}%",
                                    "match_type":        best["match_type"],
                                    "match_source":      best["source_file"],
                                    "match_date":        best["transaction_date"],
                                })
                            else:
                                output_rows.append({
                                    **{c: row.get(c, "") for c in batch_df.columns},
                                    "match_building": "", "match_unit": "",
                                    "match_owner": "NOT FOUND", "match_phone": "",
                                    "match_confidence": "0%", "match_type": "", "match_source": "", "match_date": "",
                                })
                            progress.progress(min(1.0, (i + 1) / total))

                        results_df = pd.DataFrame(output_rows)
                        matched_count = len(results_df[results_df["match_owner"] != "NOT FOUND"])
                        st.success(
                            f"**{matched_count} / {len(results_df)} listings matched "
                            f"({matched_count / max(len(results_df), 1) * 100:.0f}%)**"
                        )
                        st.dataframe(results_df, use_container_width=True)

                        csv_out = results_df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "↓ Download Results CSV",
                            data=csv_out,
                            file_name="listing_match_results.csv",
                            mime="text/csv",
                            type="primary",
                        )

    # TAB 3: COVERAGE STATS
    # ════════════════════════════════════════════════════════════════════════════
    with tab_coverage:
        st.subheader("Database coverage analysis")
        try:
            cov = analyze_coverage(leads_df)
            c1, c2, c3 = st.columns(3)
            c1.metric("Unique units", f"{cov['total_units']:,}")
            c2.metric("With phone", f"{cov['with_phone']:,} ({cov['phone_pct']}%)")
            c3.metric("With size", f"{cov['with_size']:,} ({cov['size_pct']}%)")

            st.subheader("Per-building breakdown (top 30)")
            bstats = cov["building_stats"].reset_index()
            bstats.columns = ["Building", "Unique Units", "Total Records"]
            st.dataframe(bstats, use_container_width=True, height=500)
        except Exception as e:
            st.error(f"Coverage analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT MATCH PAGE — "Find owners for my client"
# ═══════════════════════════════════════════════════════════════════════════════

def render_client_match_page():
    """Find owners to call based on a buyer/tenant's requirements."""
    apply_global_styles()

    col_back, col_title = st.columns([1, 9])
    with col_back:
        if st.button("← Back", key="cm_back"):
            st.session_state.current_page = "lead_search"
            st.rerun()
    with col_title:
        st.title(" Find Owners for My Client")
        st.caption("Enter your client's requirements — get a ranked list of owners to call")

    # ── Load data ─────────────────────────────────────────────────────────────
    lead_df, _ = load_data()
    registry   = load_registry_financial()
    bayut_df   = load_bayut_listings()

    # Build Bayut active listing lookup: building_key → list of {bedrooms, price, url, listing_type}
    bayut_lookup = {}  # {building_key: [{beds, price, url, ltype}]}
    if not bayut_df.empty:
        for _, bl in bayut_df.iterrows():
            bk = str(bl.get("building_name", "")).strip().lower().replace(" ", "").replace("-", "")
            if not bk:
                continue
            if bk not in bayut_lookup:
                bayut_lookup[bk] = []
            bayut_lookup[bk].append({
                "beds":  str(int(bl["bedrooms"])) if pd.notna(bl.get("bedrooms")) else None,
                "price": float(bl["price_aed"]) if pd.notna(bl.get("price_aed")) else None,
                "url":   str(bl.get("listing_url", "")),
                "ltype": str(bl.get("listing_type", "")).lower(),
            })

    # ── Sidebar — client requirements ─────────────────────────────────────────
    with st.sidebar:
        st.header(" Client Requirements")

        txn_type = st.radio("Transaction type", ["Sale", "Rent"], horizontal=True, key="cm_txn")

        bed_opts = ["Any", "Studio", "1", "2", "3", "4", "5+"]
        beds_sel = st.selectbox("Bedrooms", bed_opts, index=3, key="cm_beds")

        buildings_list = sorted(lead_df["building_name"].dropna().unique().tolist())
        building_sel = st.multiselect("Building (leave blank = all Palm)", buildings_list, key="cm_building")

        sea_view_only = st.checkbox("Sea view preferred", value=False, key="cm_sea_view")

        st.divider()
        if txn_type == "Sale":
            st.caption("Budget — Sale Price (AED)")
            budget_min = st.number_input("Min (AED)", value=1_000_000, step=500_000, key="cm_bmin")
            budget_max = st.number_input("Max (AED)", value=5_000_000, step=500_000, key="cm_bmax")
        else:
            st.caption("Budget — Annual Rent (AED)")
            budget_min = st.number_input("Min (AED/yr)", value=50_000, step=10_000, key="cm_bmin")
            budget_max = st.number_input("Max (AED/yr)", value=250_000, step=10_000, key="cm_bmax")

        st.divider()
        search_clicked = st.button(" Find Owners", type="primary", use_container_width=True, key="cm_search")

    if not search_clicked:
        st.info("Set your client's requirements in the sidebar and click **Find Owners**.")
        return

    # ── Filter leads ──────────────────────────────────────────────────────────
    results = lead_df.copy()

    # Building filter
    if building_sel:
        results = results[results["building_name"].isin(building_sel)]

    # Bedroom filter
    if beds_sel != "Any":
        if beds_sel == "5+":
            results = results[results["bedrooms"].apply(
                lambda b: str(b).strip() not in ("", "nan") and
                          any(str(b).strip().startswith(str(x)) for x in range(5, 20))
                if pd.notna(b) else False
            )]
        elif beds_sel == "Studio":
            results = results[results["bedrooms"].astype(str).str.lower().str.contains("studio")]
        else:
            results = results[results["bedrooms"].astype(str).str.strip() == beds_sel]

    if results.empty:
        st.warning("No leads match these criteria. Try relaxing the filters.")
        return

    # ── Enrich with registry financial data + scoring ─────────────────────────
    scored = []
    for _, row in results.iterrows():
        bkey = str(row.get("building_name", "")).strip().lower().replace(" ", "").replace("-", "")
        ukey = str(row.get("unit_number", "")).strip().upper().replace(" ", "").replace("-", "")
        reg  = registry.get(f"{bkey}|{ukey}", {})

        view          = reg.get("view") or str(row.get("view", "")) or None
        confidence    = reg.get("confidence", "MEDIUM")
        last_sale_px  = reg.get("last_sale_price")
        last_sale_dt  = reg.get("last_sale_date")
        last_rent     = reg.get("last_annual_rent")
        rental_count  = reg.get("rental_count", 0)

        # Check Bayut active listings for this building+beds
        bayut_listings = bayut_lookup.get(bkey, [])
        beds_str = str(row.get("bedrooms", "")).strip()
        active_listing = next(
            (bl for bl in bayut_listings
             if bl["ltype"] == txn_type.lower() and (bl["beds"] == beds_str or not bl["beds"])),
            None
        )

        # Sea view filter (skip if no view data and filter is strict)
        if sea_view_only and view and "sea" not in view.lower():
            continue

        # Budget filter (only when we have price data)
        if txn_type == "Sale" and last_sale_px:
            if not (budget_min * 0.7 <= last_sale_px <= budget_max * 1.3):
                continue
        elif txn_type == "Rent" and last_rent:
            if not (budget_min * 0.7 <= last_rent <= budget_max * 1.3):
                continue
        if active_listing and active_listing.get("price"):
            px = active_listing["price"]
            if not (budget_min * 0.7 <= px <= budget_max * 1.3):
                continue

        # ── Scoring ───────────────────────────────────────────────────────────
        score = 0
        badges = []

        if active_listing:
            score += 50
            price_str = f"AED {int(active_listing['price']):,}" if active_listing.get("price") else ""
            badges.append(f" Listed on Bayut {price_str}")

        if rental_count > 0:
            score += 25
            badges.append(f" Investor ({rental_count} rental contracts)")

        if confidence == "HIGH":
            score += 15
            badges.append("✓ Confirmed data")

        # Recent buyer (within ~4 years)
        if last_sale_dt:
            try:
                yr = int(str(last_sale_dt)[:4])
                if yr >= 2021:
                    score += 10
                    badges.append(f" Bought {yr}")
            except Exception:
                pass

        if view and "sea" in view.lower():
            score += 5
            badges.append(f" {view}")

        scored.append({
            "score":          score,
            "badges":         " · ".join(badges),
            "owner_name":     str(row.get("owner_name", "") or ""),
            "phone":          str(row.get("phone", "") or ""),
            "building_name":  str(row.get("building_name", "") or ""),
            "unit_number":    str(row.get("unit_number", "") or ""),
            "bedrooms":       str(row.get("bedrooms", "") or ""),
            "size_sqft":      row.get("size_sqft"),
            "view":           view or "",
            "last_sale_price":last_sale_px,
            "last_sale_date": last_sale_dt,
            "last_annual_rent":last_rent,
            "bayut_url":      active_listing.get("url", "") if active_listing else "",
            "_lead_row":      row,
        })

    if not scored:
        st.warning("No leads match these criteria after applying registry filters.")
        return

    scored.sort(key=lambda x: x["score"], reverse=True)

    # ── Results header ────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    active_count   = sum(1 for s in scored if "" in s["badges"])
    investor_count = sum(1 for s in scored if "" in s["badges"])
    m1.metric("Owners to call", f"{len(scored):,}")
    m2.metric(" Active listings", f"{active_count}")
    m3.metric(" Investors", f"{investor_count}")
    m4.metric("Beds filter", beds_sel)

    st.divider()
    st.subheader(f" Ranked call list — {txn_type} · {beds_sel}BR · {'Sea view' if sea_view_only else 'Any view'}")

    # ── Results table ─────────────────────────────────────────────────────────
    for i, s in enumerate(scored[:200]):
        rank_label = f"#{i+1}"
        with st.container():
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

            with c1:
                name = s["owner_name"] or "Unknown"
                bldg = s["building_name"]
                unit = s["unit_number"]
                beds = s["bedrooms"]
                size = f" · {int(s['size_sqft']):,} sqft" if s.get("size_sqft") else ""
                st.markdown(f"**{rank_label}. {name}**")
                st.caption(f"{bldg}, Unit {unit} · {beds}BR{size}")

            with c2:
                phone = s["phone"]
                if phone and phone not in ("nan", ""):
                    st.markdown(f" `{phone}`")
                if s["bayut_url"]:
                    st.markdown(f"[View on Bayut →]({s['bayut_url']})")

            with c3:
                if s["last_sale_price"]:
                    st.caption(f"Last sold: AED {int(s['last_sale_price']):,}")
                    if s["last_sale_date"]:
                        st.caption(f"Date: {str(s['last_sale_date'])[:10]}")
                if s["last_annual_rent"]:
                    st.caption(f"Last rent: AED {int(s['last_annual_rent']):,}/yr")

            with c4:
                if s["badges"]:
                    for badge in s["badges"].split(" · "):
                        st.caption(badge)

            # Quick action buttons
            btn1, btn2 = st.columns(2)
            with btn1:
                if st.button(" Profile", key=f"cm_profile_{i}", use_container_width=True):
                    row = s["_lead_row"]
                    st.session_state.selected_client = {
                        "owner_name":   str(row.get("owner_name", "") or ""),
                        "building_name":str(row.get("building_name", "") or ""),
                        "unit_number":  str(row.get("unit_number", "") or ""),
                        "phone":        str(row.get("phone", "") or ""),
                        "bedrooms":     row.get("bedrooms"),
                        "size_sqft":    row.get("size_sqft"),
                        "size_sqm":     row.get("size_sqm"),
                        "date":         str(row.get("date", "") or ""),
                    }
                    st.session_state.profile_return_page = "client_match"
                    st.session_state.current_page = "client_profile"
                    st.rerun()
            with btn2:
                if st.button(" Log Call", key=f"cm_call_{i}", use_container_width=True):
                    st.session_state[f"cm_log_call_{i}"] = True
                    st.rerun()

            if st.session_state.get(f"cm_log_call_{i}"):
                row = s["_lead_row"]
                with st.expander(" Log call", expanded=True):
                    outcome = st.radio("Outcome", ["voicemail", "no_answer", "not_interested", "interested", "callback"],
                                       format_func=lambda x: x.replace("_", " ").title(),
                                       key=f"cm_outcome_{i}", horizontal=True)
                    notes = st.text_input("Notes", key=f"cm_notes_{i}")
                    s_col, c_col = st.columns(2)
                    with s_col:
                        if st.button("Save", key=f"cm_save_{i}"):
                            sel_name = str(row.get("owner_name", "") or "")
                            sel_bldg = str(row.get("building_name", "") or "")
                            sel_unit = str(row.get("unit_number", "") or "")
                            client_id = cdm.make_client_id(sel_name, sel_bldg, sel_unit)
                            cdm.log_call(client_id, sel_name, sel_bldg, sel_unit,
                                         str(row.get("phone", "") or ""), outcome, notes)
                            st.session_state[f"cm_log_call_{i}"] = False
                            st.success("Saved")
                            st.rerun()
                    with c_col:
                        if st.button("Cancel", key=f"cm_cancel_{i}"):
                            st.session_state[f"cm_log_call_{i}"] = False
                            st.rerun()

            st.divider()

    if len(scored) > 200:
        st.caption(f"Showing top 200 of {len(scored):,} matches. Refine filters to narrow down.")


# ═══════════════════════════════════════════════════════════════════════════════
# BAYUT ACTIVE LISTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_bayut_listings_page():
    """Browse active Bayut listings for Palm Jumeirah — identify motivated sellers/landlords."""
    apply_global_styles()

    col_back, col_title = st.columns([1, 8])
    with col_back:
        if st.button("← Back", key="bayut_back"):
            st.session_state.current_page = "lead_search"
            st.rerun()
    with col_title:
        st.title(" Active Bayut Listings — Palm Jumeirah")
        st.caption("Motivated sellers and landlords currently listing on Bayut — prime outreach targets")

    df = load_bayut_listings()

    if df.empty:
        st.warning("No Bayut listing data found.")
        st.info("Run the scraper first:\n```\npython bayut_scraper/run_palm_listings.py\n```")
        return

    # ── Sidebar filters ───────────────────────────────────────────────────────
    with st.sidebar:
        st.header(" Filters")

        ltype_options = ["All"] + sorted(df["listing_type"].dropna().str.upper().unique().tolist())
        ltype_sel = st.selectbox("Listing type", ltype_options)

        building_options = ["All"] + sorted(df["building_name"].dropna().unique().tolist())
        building_sel = st.selectbox("Building", building_options)

        beds_options = ["All"] + sorted([str(int(b)) for b in df["bedrooms"].dropna().unique()])
        beds_sel = st.selectbox("Bedrooms", beds_options)

        if df["price_aed"].notna().any():
            min_p = int(df["price_aed"].min())
            max_p = int(df["price_aed"].max())
            if min_p < max_p:
                price_range = st.slider("Price (AED)", min_p, max_p, (min_p, max_p), step=50_000)
            else:
                price_range = (min_p, max_p)
        else:
            price_range = (0, 999_999_999)

        st.divider()
        st.caption(f"Total listings: **{len(df):,}**")
        st.caption(f"Buildings covered: **{df['building_name'].nunique()}**")
        if "scraped_at" in df.columns:
            latest = df["scraped_at"].max()
            st.caption(f"Last scraped: **{str(latest)[:10]}**")

        st.divider()
        st.markdown("**↺ Refresh Listings**")
        st.caption("Checks pages 1–3 for new listings. Chrome must be running on port 9222.")
        refresh_type = st.radio("Type", ["Both", "Sale only", "Rent only"], horizontal=True, key="refresh_type")
        if st.button("Check for new listings", key="bayut_refresh_btn", use_container_width=True):
            type_map = {"Both": ["sale", "rent"], "Sale only": ["sale"], "Rent only": ["rent"]}
            types_to_scrape = type_map[refresh_type]
            import subprocess, sys
            cmd = [sys.executable, "bayut_scraper/run_palm_listings.py",
                   "--type", "both" if len(types_to_scrape) == 2 else types_to_scrape[0],
                   "--max-pages", "3"]
            with st.spinner("Scanning pages 1–3 for new listings…"):
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                    output = result.stdout or ""
                    new_lines = [l for l in output.splitlines() if "[OK]" in l or "[STOP]" in l or "new listings saved" in l]
                    if new_lines:
                        st.success("\n".join(new_lines[-5:]))
                    else:
                        st.info("Scan complete — no new output to show")
                    if result.returncode != 0 and result.stderr:
                        st.warning(result.stderr[:300])
                    load_bayut_listings.clear()
                    st.rerun()
                except subprocess.TimeoutExpired:
                    st.error("Scraper timed out after 3 minutes. Chrome may not be running.")
                except Exception as e:
                    st.error(f"Error running scraper: {e}")

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = df.copy()
    if ltype_sel != "All":
        filtered = filtered[filtered["listing_type"].str.upper() == ltype_sel]
    if building_sel != "All":
        filtered = filtered[filtered["building_name"] == building_sel]
    if beds_sel != "All":
        filtered = filtered[filtered["bedrooms"].apply(
            lambda b: str(int(b)) == beds_sel if pd.notna(b) else False
        )]
    if "price_aed" in filtered.columns:
        filtered = filtered[
            filtered["price_aed"].isna() |
            ((filtered["price_aed"] >= price_range[0]) & (filtered["price_aed"] <= price_range[1]))
        ]

    st.caption(f"Showing **{len(filtered)}** listings")

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Listings", f"{len(filtered):,}")
    m2.metric("Buildings", f"{filtered['building_name'].nunique()}")
    sale_count = (filtered["listing_type"].str.lower() == "sale").sum() if "listing_type" in filtered.columns else 0
    rent_count = (filtered["listing_type"].str.lower() == "rent").sum() if "listing_type" in filtered.columns else 0
    m3.metric("For Sale", f"{sale_count:,}")
    m4.metric("For Rent", f"{rent_count:,}")

    st.divider()

    # ── Per-building summary ──────────────────────────────────────────────────
    st.subheader(" By Building")
    building_summary = (
        filtered.groupby("building_name")
        .agg(
            Listings=("building_name", "count"),
            Avg_Beds=("bedrooms", "mean"),
            Avg_Size=("size_sqft", "mean"),
            Avg_Price=("price_aed", "mean"),
            Types=("listing_type", lambda x: "/".join(sorted(x.str.upper().unique()))),
        )
        .reset_index()
        .rename(columns={"building_name": "Building"})
        .sort_values("Listings", ascending=False)
    )
    building_summary["Avg_Beds"] = building_summary["Avg_Beds"].round(1)
    building_summary["Avg_Size"] = building_summary["Avg_Size"].round(0).astype("Int64")
    building_summary["Avg_Price"] = building_summary["Avg_Price"].round(0).astype("Int64")
    st.dataframe(building_summary, use_container_width=True, height=300)

    st.divider()

    # ── Full listing table ────────────────────────────────────────────────────
    st.subheader(" All Listings")

    display_cols = ["listing_type", "building_name", "bedrooms", "bathrooms",
                    "size_sqft", "price_aed", "view", "listing_title", "listing_url", "scraped_at"]
    display_cols = [c for c in display_cols if c in filtered.columns]
    display = filtered[display_cols].copy()

    # Format columns
    if "bedrooms" in display.columns:
        display["bedrooms"] = display["bedrooms"].apply(lambda x: str(int(x)) if pd.notna(x) else "")
    if "bathrooms" in display.columns:
        display["bathrooms"] = display["bathrooms"].apply(lambda x: str(int(x)) if pd.notna(x) else "")
    if "size_sqft" in display.columns:
        display["size_sqft"] = display["size_sqft"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    if "price_aed" in display.columns:
        display["price_aed"] = display["price_aed"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    if "listing_type" in display.columns:
        display["listing_type"] = display["listing_type"].str.upper()
    if "scraped_at" in display.columns:
        display["scraped_at"] = display["scraped_at"].astype(str).str[:10]

    display = display.rename(columns={
        "listing_type": "Type", "building_name": "Building",
        "bedrooms": "Beds", "bathrooms": "Baths",
        "size_sqft": "Size (sqft)", "price_aed": "Price (AED)",
        "view": "View", "listing_title": "Title",
        "listing_url": "Bayut URL", "scraped_at": "Date Scraped",
    })

    st.dataframe(
        display,
        use_container_width=True,
        height=500,
        column_config={
            "Bayut URL": st.column_config.LinkColumn("Bayut URL", display_text="Open →"),
        },
    )

    # ── Cross-reference with lead database ───────────────────────────────────
    st.divider()
    st.subheader(" Cross-reference with Lead Database")
    st.caption("Find owners in your database who are actively listing on Bayut")

    if building_sel != "All":
        lead_df, _ = load_data()
        bkey = building_sel.lower().replace(" ", "").replace("-", "")
        lead_building_key = (
            lead_df["building_name"].fillna("").str.lower()
            .str.replace(r"[\s\-]", "", regex=True)
        )
        building_leads = lead_df[lead_building_key == bkey]
        # Filter out non-residential units (parking bays, storage rooms < 300 sqft)
        size_col = pd.to_numeric(building_leads.get("size_sqft", pd.Series(dtype=float)), errors="coerce")
        non_res_mask = size_col.notna() & (size_col < 300)
        non_res_count = non_res_mask.sum()
        building_leads = building_leads[~non_res_mask]
        if building_leads.empty:
            st.info(f"No leads found in database for **{building_sel}**")
        else:
            caption_parts = [f"**{len(building_leads):,} leads** in database for {building_sel}"]
            if non_res_count > 0:
                caption_parts.append(f"({non_res_count} non-residential units <300 sqft hidden)")
            st.success(" — ".join(caption_parts))
            if beds_sel != "All":
                numeric_beds = pd.to_numeric(building_leads["bedrooms"], errors="coerce").round().astype("Int64")
                building_leads = building_leads[numeric_beds == int(beds_sel)]
                st.caption(f"Filtered to {beds_sel}BR: {len(building_leads):,} leads")

            show_cols = [c for c in ["owner_name", "unit_number", "bedrooms", "size_sqft", "phone", "bedroom_confidence"]
                         if c in building_leads.columns]
            st.dataframe(building_leads[show_cols].head(100), use_container_width=True, height=300)
    else:
        st.info("Select a specific building in the sidebar to see matching leads from your database.")


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_health_check_page():
    """System health check and diagnostics."""
    apply_global_styles()
    
    st.title(" System Health Check")
    st.caption("Verify all components are configured correctly")
    
    st.divider()
    
    # Check 1: Data Files
    st.subheader(" Data Files")
    col1, col2 = st.columns(2)
    
    with col1:
        lead_file = Path("lead_database/leads_master.csv")
        if lead_file.exists():
            size_mb = lead_file.stat().st_size / 1024 / 1024
            st.success("✓ Lead Database")
            st.caption(f" {size_mb:.1f} MB")
            try:
                lead_df = pd.read_csv(lead_file)
                st.caption(f" {len(lead_df):,} records")
                if 'Building Name' in lead_df.columns:
                    st.caption(f" {lead_df['Building Name'].nunique()} buildings")
                elif 'building_name' in lead_df.columns:
                    st.caption(f" {lead_df['building_name'].nunique()} buildings")
            except Exception:
                st.warning(" (Could not read file)")
        else:
            st.error("✕ Lead Database Missing")
            st.caption(" Run: python consolidate_data.py")
    
    with col2:
        ref_file = Path("Master reference datasets/reference_master.csv")
        if ref_file.exists():
            size_mb = ref_file.stat().st_size / 1024 / 1024
            st.success("✓ Reference Data")
            st.caption(f" {size_mb:.1f} MB")
            try:
                ref_df = pd.read_csv(ref_file)
                st.caption(f" {len(ref_df):,} transactions")
            except Exception:
                st.warning(" (Could not read file)")
        else:
            st.error("✕ Reference Data Missing")
    
    st.divider()
    
    # Check 2: API Configuration
    st.subheader(" API Configuration")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        st.success("✓ Anthropic API Key Configured")
        st.caption(f" Key: {api_key[:20]}...{api_key[-4:]}")
        if st.button("Test API Connection"):
            with st.spinner("Testing..."):
                try:
                    test_client = anthropic.Anthropic(api_key=api_key)
                    test_response = test_client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=50,
                        messages=[{"role": "user", "content": "Say 'API test successful'"}],
                        timeout=15.0
                    )
                    st.success("✓ API Connection Successful")
                    text = test_response.content[0].text if test_response.content else ""
                    st.code(text)
                except Exception as e:
                    st.error(f"✕ API Test Failed: {e}")
    else:
        st.error("✕ Anthropic API Key Not Found")
        st.code("Set in .env file: ANTHROPIC_API_KEY=sk-ant-...")
    
    st.divider()
    
    # Check 3: Dependencies
    st.subheader(" Dependencies")
    dependencies = {
        "streamlit": "Streamlit",
        "pandas": "Pandas",
        "anthropic": "Anthropic SDK",
        "fuzzywuzzy": "FuzzyWuzzy",
        "dotenv": "Python-dotenv"
    }
    for module, name in dependencies.items():
        try:
            __import__(module)
            st.success(f"✓ {name}")
        except ImportError:
            st.error(f"✕ {name} Missing")
            st.caption(f" pip install {module}")
    
    st.divider()
    
    # Check 4: Building Intelligence
    st.subheader("Building Intelligence")
    try:
        from data_processor import BUILDING_INTELLIGENCE_AVAILABLE
        from building_intelligence import SHORELINE_TOWER_MAPPING, BUILDING_ALIASES
        if BUILDING_INTELLIGENCE_AVAILABLE:
            st.success("✓ Building Intelligence Module")
            st.caption(f" {len(SHORELINE_TOWER_MAPPING)} Shoreline towers")
            st.caption(f" {len(BUILDING_ALIASES)} building aliases")
        else:
            st.error("✕ Building Intelligence Not Available")
    except Exception as e:
        st.error("✕ Building Intelligence Not Available")
        st.caption(str(e))
    
    st.divider()
    
    # Check 5: Chat System
    st.subheader(" Chat System")
    chat_dir = Path("chat_history")
    if chat_dir.exists():
        num_chats = len(list(chat_dir.glob("*.json")))
        st.success("✓ Chat System")
        st.caption(f" {num_chats} saved chats")
    else:
        st.warning("⚠ Chat Directory Not Found")
    
    st.divider()
    
    if st.button("← Back to Lead Search", use_container_width=True, type="primary"):
        st.session_state.current_page = 'lead_search'
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APP ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main application entry point."""
    # Ensure DB tables exist (including contacts)
    try:
        init_database()
    except Exception:
        pass
    # Initialize session state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'lead_search'
    
    if 'current_chat_id' not in st.session_state:
        all_chats = cm.get_all_chats()
        if all_chats:
            st.session_state.current_chat_id = all_chats[0]['id']
        else:
            st.session_state.current_chat_id = cm.create_new_chat("General Inquiry")
    
    # Hide leftover chat UI when not on AI page (Streamlit chat can persist in DOM after navigation)
    if st.session_state.get('current_page') != 'ai_chat':
        st.markdown("""
        <style>
            [data-testid="stChatInput"] { display: none !important; }
            [data-testid="stChatMessage"] { display: none !important; }
        </style>
        """, unsafe_allow_html=True)
    
    # Route to appropriate page
    if st.session_state.current_page == 'ai_chat':
        render_ai_chat_page()
    elif st.session_state.current_page == 'client_profile':
        render_client_profile_page()
    elif st.session_state.current_page == 'contact_profile':
        render_contact_profile_page()
    elif st.session_state.current_page == 'follow_ups':
        render_follow_ups_page()
    elif st.session_state.current_page == 'call_log':
        render_call_log_page()
    elif st.session_state.current_page == 'contacts':
        render_contacts_page()
    elif st.session_state.current_page == 'lease_expiry':
        render_lease_expiry_page()
    elif st.session_state.current_page == 'whatsapp':
        render_whatsapp_page()
    elif st.session_state.current_page == 'pf_scraper':
        render_pf_scraper_page()
    elif st.session_state.current_page == 'property_monitor':
        render_property_monitor_page()
    elif st.session_state.current_page == 'health_check':
        render_health_check_page()
    elif st.session_state.current_page == 'listing_matcher':
        render_listing_matcher_page()
    elif st.session_state.current_page == 'bayut_listings':
        render_bayut_listings_page()
    elif st.session_state.current_page == 'client_match':
        render_client_match_page()
    else:
        render_lead_search_page()


if __name__ == "__main__":
    main()
