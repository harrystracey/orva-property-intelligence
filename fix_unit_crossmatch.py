"""
Cross-match unit numbers: fill no-unit leads using phone+building or name+building
matches from leads that DO have unit numbers.
"""
import pandas as pd
import re

pq = pd.read_parquet('lead_database/leads_master.parquet')
print(f'Total leads: {len(pq):,}')

def clean_phone(p):
    return re.sub(r'\D', '', str(p or ''))

def is_valid_unit(u):
    u = str(u or '').strip()
    return bool(u) and u not in ('None', 'nan', '0', '-', 'N/A', '')

pq['_phone'] = pq['Phone'].apply(clean_phone)
pq['_name']  = pq['Owner Name'].fillna('').str.strip().str.lower()
pq['_bld']   = pq['Building Name'].fillna('').str.strip().str.lower()
pq['_has_unit'] = pq['Unit Number'].apply(is_valid_unit)

has_unit = pq[pq['_has_unit'] == True].copy()
no_unit_idx = pq.index[pq['_has_unit'] == False].tolist()

print(f'Has unit: {len(has_unit):,}  |  No unit: {len(no_unit_idx):,}')

# Build unambiguous lookup: (phone, bld) -> single unit number
def build_lookup(df, col1, col2):
    result = {}
    grp = df[df[col1].str.len() >= (7 if col1 == '_phone' else 4)].groupby([col1, col2])
    for key, group in grp:
        units = [u for u in group['Unit Number'].dropna().unique() if is_valid_unit(u)]
        if len(units) == 1:  # unambiguous — only one distinct unit for this key
            result[key] = units[0]
    return result

phone_lkp = build_lookup(has_unit, '_phone', '_bld')
name_lkp  = build_lookup(has_unit, '_name',  '_bld')

print(f'Phone+bld lookup: {len(phone_lkp):,} unambiguous entries')
print(f'Name+bld  lookup: {len(name_lkp):,} unambiguous entries')

# Apply
updates = {}
for idx in no_unit_idx:
    row = pq.loc[idx]
    found = None

    pk = (row['_phone'], row['_bld'])
    nk = (row['_name'],  row['_bld'])

    if len(row['_phone']) >= 7 and pk in phone_lkp:
        found = (phone_lkp[pk], 'phone')
    elif len(row['_name']) >= 4 and nk in name_lkp:
        found = (name_lkp[nk], 'name')

    if found and is_valid_unit(found[0]):
        updates[idx] = found

print(f'\nUnits to fill: {len(updates):,}')

# Show breakdown
idxs = list(updates.keys())
bld_counts = pq.loc[idxs, 'Building Name'].value_counts()
print('\nFills by building:')
print(bld_counts.head(20).to_string())

print('\nSample (first 15):')
for idx in idxs[:15]:
    unit, method = updates[idx]
    row = pq.loc[idx]
    print(f"  {row['Owner Name'][:35]:<35} | {row['Building Name'][:30]:<30} | -> {unit}  [{method}]")

# Write back
for idx, (unit, method) in updates.items():
    pq.at[idx, 'Unit Number'] = str(unit).strip()

pq.drop(columns=['_phone', '_name', '_bld', '_has_unit'], inplace=True)
pq.to_parquet('lead_database/leads_master.parquet', index=False)

remaining = sum(1 for u in pq['Unit Number'] if not is_valid_unit(u))
print(f'\nDone. Remaining no-unit leads: {remaining:,}  (was 43,222)')
print('Parquet saved.')
