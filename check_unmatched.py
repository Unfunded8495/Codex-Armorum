import sqlite3
conn = sqlite3.connect('collection.db')

# Check if unmatched unit names exist in BSData at all
check_names = [
    'Ballistus Dreadnought', 'Invictor Tactical Warsuit', 'Brutalis Dreadnought',
    'Apothecary Biologis', 'Von Ryan', 'Captain in Terminator',
]
print('=== BSData catalogue lookup for sample unmatched names ===')
for n in check_names:
    rows = conn.execute(
        'SELECT bsdata_id, name FROM catalogue_units WHERE name LIKE ? LIMIT 3', (f'%{n}%',)
    ).fetchall()
    print(f'  "{n}": {rows}')

# Check if these are type=model in BSData XML (they exist as weapons entries?)
print()
print('=== Distinct unmatched unit names in minis ===')
from data_store import get_store
store = get_store()
unmatched_minis = conn.execute(
    'SELECT DISTINCT datasheet_id FROM minis WHERE unit_bsdata_id IS NULL'
).fetchall()
name_to_did = {}
for row in unmatched_minis:
    did = row[0]
    ud = store.unit_detail(did)
    name = ud['name'] if ud else f'UNKNOWN({did})'
    name_to_did[name] = did

for name, did in sorted(name_to_did.items()):
    print(f'  {did}  {name}')

print()
print(f'Total distinct unmatched units: {len(name_to_did)}')

# Breakdown of arsenal_weapon_datasheet unmatched
print()
print('=== arsenal_weapon_datasheet coverage ===')
total_ds_ids = conn.execute('SELECT COUNT(DISTINCT datasheet_id) FROM arsenal_weapon_datasheet').fetchone()[0]
matched_ds_ids = conn.execute('SELECT COUNT(DISTINCT datasheet_id) FROM arsenal_weapon_datasheet WHERE unit_bsdata_id IS NOT NULL').fetchone()[0]
print(f'Distinct datasheet_ids covered: {matched_ds_ids}/{total_ds_ids}')
print(f'(Unmatched datasheet_ids = datasheets not in BSData catalogue)')

conn.close()
