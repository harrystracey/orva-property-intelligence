"""
Backfill bedrooms + fix sizes into parquet for all leads with a unit number but no bedroom count.
Priority:
  1. Unit registry (exact building+unit match)
  2. Unit number schema (floor-based patterns per building)
  3. Size-based definitive inference (with sqm->sqft auto-detection)
Also corrects Size (sqft) values stored as sqm (any value < 300).
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

pq = pd.read_parquet('lead_database/leads_master.parquet')
reg = pd.read_csv('data/unit_registry.csv')
print(f'Parquet rows: {len(pq):,}')

# Fix sqm stored as sqft across ALL leads
# First convert the whole column to numeric so parquet can write it cleanly
pq['Size (sqft)'] = pd.to_numeric(pq['Size (sqft)'], errors='coerce')
sqft_col = pq['Size (sqft)']
sqm_mask = sqft_col.between(15, 300)
sqm_count = sqm_mask.sum()
if sqm_count > 0:
    pq.loc[sqm_mask, 'Size (sqft)'] = (sqft_col[sqm_mask] * 10.764).round(1)
    print(f'Corrected {sqm_count:,} sqm->sqft size values')

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

target_mask = pq['Unit Number'].apply(is_valid) & ~pq['Bedrooms'].apply(is_valid)
target_idx = pq.index[target_mask].tolist()
print(f'Has unit, no bedrooms: {len(target_idx):,}')

registry_fills = schema_fills = size_fills = not_filled = 0

for idx in target_idx:
    row = pq.loc[idx]
    bld  = str(row['Building Name'] or '')
    unit = str(row['Unit Number'] or '').strip()
    size = row.get('Size (sqft)', None)
    bkey = standardize_building_name(bld) or bld.lower().strip()
    ukey = unit.upper()

    if (bkey, ukey) in lookup:
        pq.at[idx, 'Bedrooms'] = lookup[(bkey, ukey)]
        registry_fills += 1
        continue

    schema = infer_bedrooms_from_unit_schema(bld, unit)
    if schema and schema.get('bedrooms'):
        pq.at[idx, 'Bedrooms'] = str(schema['bedrooms'])
        schema_fills += 1
        continue

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

pq.to_parquet('lead_database/leads_master.parquet', index=False)
print('\nParquet saved.')

csv = pd.read_csv('lead_database/leads_master.csv', low_memory=False)
beds_synced = size_synced = 0
for i in range(min(len(pq), len(csv))):
    pq_beds = str(pq.at[i, 'Bedrooms'] or '').strip()
    csv_beds = str(csv.at[i, 'Bedrooms'] or '').strip()
    if is_valid(pq_beds) and not is_valid(csv_beds):
        csv.at[i, 'Bedrooms'] = pq_beds
        beds_synced += 1
    pq_size = pq.at[i, 'Size (sqft)']
    csv_size = pd.to_numeric(csv.at[i, 'Size (sqft)'], errors='coerce')
    if pd.notna(pq_size) and pd.notna(csv_size) and float(csv_size) < 300:
        csv.at[i, 'Size (sqft)'] = pq_size
        size_synced += 1

print(f'Synced {beds_synced:,} bedroom values to CSV.')
print(f'Synced {size_synced:,} corrected size values to CSV.')
csv.to_csv('lead_database/leads_master.csv', index=False, encoding='utf-8')
print('CSV saved.')
