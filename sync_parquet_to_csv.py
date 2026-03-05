"""
Sync Unit Number (and any other enriched fields) from parquet back to CSV.
Run after any cross-matching or manual parquet edits.
"""
import pandas as pd

pq = pd.read_parquet('lead_database/leads_master.parquet')
csv = pd.read_csv('lead_database/leads_master.csv', low_memory=False)

print(f'Parquet: {len(pq):,} rows | CSV: {len(csv):,} rows')

# Match rows by position (same row order assumed — both built from same source)
# Sync Unit Number and Bedrooms from parquet to CSV
synced_unit = 0
synced_beds = 0

def is_valid(v):
    return bool(str(v or '').strip()) and str(v).strip() not in ('None', 'nan', '0', '-', 'N/A', '')

for i in range(min(len(pq), len(csv))):
    pq_unit = str(pq.at[i, 'Unit Number'] or '').strip()
    csv_unit = str(csv.at[i, 'Unit Number'] or '').strip()
    if is_valid(pq_unit) and not is_valid(csv_unit):
        csv.at[i, 'Unit Number'] = pq_unit
        synced_unit += 1

    pq_beds = str(pq.at[i, 'Bedrooms'] or '').strip()
    csv_beds = str(csv.at[i, 'Bedrooms'] or '').strip()
    if is_valid(pq_beds) and not is_valid(csv_beds):
        csv.at[i, 'Bedrooms'] = pq_beds
        synced_beds += 1

print(f'Synced Unit Number: {synced_unit:,}')
print(f'Synced Bedrooms:    {synced_beds:,}')

csv.to_csv('lead_database/leads_master.csv', index=False, encoding='utf-8')
print('CSV saved.')
