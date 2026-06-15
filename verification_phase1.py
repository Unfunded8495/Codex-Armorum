import sqlite3
conn = sqlite3.connect('collection.db')

tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print('All tables:', [t[0] for t in tables])
print()

for t in ['catalogue_factions', 'catalogue_units', 'catalogue_weapons', 'catalogue_unit_weapons']:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(t, [c[1] for c in cols])

print()
for t in ['minis', 'army_units', 'arsenal_weapon']:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(t, [c[1] for c in cols])

conn.close()
