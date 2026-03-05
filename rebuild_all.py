"""
Master rebuild script — run this whenever you want to refresh all data.
Runs the full pipeline in order:
  1. Cross-match unit numbers (phone+name matching within lead database)
  2. Sync parquet -> CSV
  3. Rebuild unit registry from all 6 sources
  4. Backfill bedrooms + fix sqm->sqft sizes
  5. Final sync parquet -> CSV

Usage: python rebuild_all.py
"""
import subprocess
import sys
import time

def run(script, label):
    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')
    t = time.time()
    result = subprocess.run([sys.executable, script], capture_output=False)
    elapsed = time.time() - t
    if result.returncode != 0:
        print(f'\n[ERROR] {label} failed (exit {result.returncode})')
        sys.exit(result.returncode)
    print(f'  Done in {elapsed:.0f}s')

start = time.time()
print('\nORVA — Full Data Rebuild')
print('This will take 2-4 minutes. Do not close this window.\n')

run('fix_unit_crossmatch.py',  'Step 1/4: Cross-match unit numbers')
run('sync_parquet_to_csv.py',  'Step 2/4: Sync parquet -> CSV')
run('build_unit_registry.py',  'Step 3/4: Rebuild unit registry')
run('backfill_bedrooms.py',    'Step 4/4: Backfill bedrooms + fix sizes')

total = time.time() - start
print(f'\n{"="*60}')
print(f'  Rebuild complete in {total:.0f}s')
print(f'  Reload the app to see updated data.')
print(f'{"="*60}\n')
