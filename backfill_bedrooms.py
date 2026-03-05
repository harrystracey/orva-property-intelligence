"""
Backfill bedrooms into parquet for all leads that have a unit number but no bedroom count.
Priority:
  1. Unit registry (exact building+unit match)
  2. Unit number schema (floor-based patterns per building)
  3. Size-based definitive inference
Saves result to parquet + syncs to CSV.
"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from data_processor import (
    standardize_building_name,
    infer_bedrooms_from_unit_schema,
    infer_bedrooms_from_size_definitive,
)

def is_valid(v):
    v = str(v or '').strip()
    return bool(v) and v not in ('None', 'nan', '0', '-', 'N/A', '')

# ── Load data ──────────────────────────────────────────────────────────────
pq = pd.read_parquet('lead_database/leads_master.parquet')
reg = pd.read_csv('data/unit_registry.csv')

print(f'Parquet rows: {len(pq):,}')

# ── Build registry lookup (std building + unit -> bedrooms) ────────────────
reg_with_beds = reg[reg['bedrooms'].apply(is_valid)].copy()
reg_with_beds['_bkey'] = reg_with_beds['building_name'].apply(
    lambda x: standardize_building_name(str(x)) or str(x).lower().strip()
)
reg_with_beds['_ukey'] = reg_with_beds['unit_number'].astype(str).str.strip().str.upper()
lookup = (
    reg_with_beds
    .groupby(['_bkey', '_ukey'])['bedrooms']
    .agg(lambda x: x.mode()[0])
    .to_dict()
)
print(f'Registry lookup entries: {len(lookup):,}')

# ── Find target rows ───────────────────────────────────────────────────────
target_mask = pq['Unit Number'].apply(is_valid) & ~pq['Bedrooms'].apply(is_valid)
target_idx = pq.index[target_mask].tolist()
print(f'Has unit, no bedrooms: {len(target_idx):,}')

# ── Fill ───────────────────────────────────────────────────────────────────
registry_fills = 0
schema_fills = 0
size_fills = 0
not_filled = 0

for idx in target_idx:
    row = pq.loc[idx]
    bld  = str(row['Building Name'] or '')
    unit = str(row['Unit Number'] or '').strip()
    size = row.get('Size (sqft)', None)

    bkey = standardize_building_name(bld) or bld.lower().strip()
    ukey = unit.upper()

    # Priority 1 — registry
    if (bkey, ukey) in lookup:
        pq.at[idx, 'Bedrooms'] = lookup[(bkey, ukey)]
        registry_fills += 1
        continue

    # Priority 2 — unit schema
    schema = infer_bedrooms_from_unit_schema(bld, unit)
    if schema and schema.get('bedrooms'):
        pq.at[idx, 'Bedrooms'] = str(schema['bedrooms'])
        schema_fills += 1
        continue

    # Priority 3 — size-based
    if size and is_valid(str(size)):
        try:
            sz = float(str(size).replace(',', '').split()[0])
            size_res = infer_bedrooms_from_size_definitive(sz, bld)
            if size_res and size_res.get('bedrooms'):
                pq.at[idx, 'Bedrooms'] = str(size_res['bedrooms'])
                size_fills += 1
                continue
        except (ValueError, TypeError):
            pass

    not_filled += 1

total = len(target_idx)
print(f'\nResults:')
print(f'  Registry fills:  {registry_fills:,} ({100*registry_fills/total:.0f}%)')
print(f'  Schema fills:    {schema_fills:,} ({100*schema_fills/total:.0f}%)')
print(f'  Size fills:      {size_fills:,} ({100*size_fills/total:.0f}%)')
print(f'  Not filled:      {not_filled:,} ({100*not_filled/total:.0f}%)')
print(f'  Total filled:    {registry_fills+schema_fills+size_fills:,}')

# ── Save parquet ───────────────────────────────────────────────────────────
pq.to_parquet('lead_database/leads_master.parquet', index=False)
print('\nParquet saved.')

# ── Sync bedrooms back to CSV ──────────────────────────────────────────────
csv = pd.read_csv('lead_database/leads_master.csv', low_memory=False)
synced = 0
for i in range(min(len(pq), len(csv))):
    pq_beds = str(pq.at[i, 'Bedrooms'] or '').strip()
    csv_beds = str(csv.at[i, 'Bedrooms'] or '').strip()
    if is_valid(pq_beds) and not is_valid(csv_beds):
        csv.at[i, 'Bedrooms'] = pq_beds
        synced += 1

print(f'Synced {synced:,} bedroom values to CSV.')
csv.to_csv('lead_database/leads_master.csv', index=False, encoding='utf-8')
print('CSV saved.')
