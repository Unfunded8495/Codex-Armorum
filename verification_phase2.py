import sqlite3
conn = sqlite3.connect('collection.db')

print('Factions:', conn.execute('SELECT COUNT(*) FROM catalogue_factions').fetchone()[0])
print('Units:', conn.execute('SELECT COUNT(*) FROM catalogue_units').fetchone()[0])
print('Weapons:', conn.execute('SELECT COUNT(*) FROM catalogue_weapons').fetchone()[0])
print('Unit-weapon links:', conn.execute('SELECT COUNT(*) FROM catalogue_unit_weapons').fetchone()[0])

print('\nSpace Marines units (first 10):')
rows = conn.execute('''
    SELECT cu.name, cu.points, cu.role
    FROM catalogue_units cu
    JOIN catalogue_factions cf ON cu.faction_id = cf.bsdata_id
    WHERE cf.name LIKE '%Space Marines%'
    ORDER BY cu.name
    LIMIT 10
''').fetchall()
for r in rows:
    print(' ', r)

print('\nIntercessor Squad weapons:')
rows = conn.execute('''
    SELECT cw.name, cw.weapon_type, cw.attacks, cw.strength, cw.ap, cw.damage
    FROM catalogue_weapons cw
    JOIN catalogue_unit_weapons cuw ON cw.bsdata_id = cuw.weapon_id
    JOIN catalogue_units cu ON cuw.unit_id = cu.bsdata_id
    WHERE cu.name = 'Intercessor Squad'
''').fetchall()
for r in rows:
    print(' ', r)

print('\nIntercessor Squad stats:')
row = conn.execute(
    "SELECT stats_json, keywords_json FROM catalogue_units WHERE name = 'Intercessor Squad' LIMIT 1"
).fetchone()
if row:
    import json
    print('  stats:', json.loads(row[0]) if row[0] else None)
    print('  keywords:', json.loads(row[1]) if row[1] else None)

conn.close()
