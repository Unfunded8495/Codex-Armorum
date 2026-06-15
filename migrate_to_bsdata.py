"""One-time migration: populate *_bsdata_id columns by matching Wahapedia names
to BSData catalogue GUIDs.

Non-destructive: only writes to the new *_bsdata_id columns.
Unmatched rows are left NULL and listed in migration_report.txt.

Safe to re-run (idempotent - only processes rows where column IS NULL).
"""
import csv as _csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

# Ensure data_store (and its CSV data) is importable from the project root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import get_store

# Unicode typographic apostrophes used by BSData (U+2019 right, U+2018 left)
_RIGHT_APOS = '’'
_LEFT_APOS  = '‘'


def _normalise(name):
    """Normalise typographic apostrophes to straight quotes for matching."""
    return name.replace(_RIGHT_APOS, "'").replace(_LEFT_APOS, "'")


def normalise_name(name: str) -> str:
    """Normalise for catalogue matching: apostrophes, [Legends] suffix, lowercase."""
    name = name.replace(_RIGHT_APOS, "'").replace(_LEFT_APOS, "'")
    name = re.sub(r'\s*\[.*?\]\s*$', '', name).strip()
    return name.lower()


def _load_overrides():
    """Load bsdata_manual_overrides.json, ignoring keys starting with '_'."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'bsdata_manual_overrides.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith('_')}


def _lookup_unit_bsdata_id(conn, unit_name):
    """Return catalogue_units.bsdata_id for unit_name, or None.

    Normalises both sides: BSData uses typographic apostrophes while Wahapedia
    uses straight quotes. SQLite REPLACE() normalises the stored values;
    _normalise() normalises the query value.
    """
    normalised = _normalise(unit_name)
    row = conn.execute(
        'SELECT bsdata_id FROM catalogue_units'
        ' WHERE REPLACE(REPLACE(name, ?, ?), ?, ?) = ? COLLATE NOCASE LIMIT 1',
        (_RIGHT_APOS, "'", _LEFT_APOS, "'", normalised)
    ).fetchone()
    return row[0] if row else None


def migrate_minis(conn, store, normalised_catalogue, overrides, csv_fallback):
    rows = conn.execute(
        'SELECT id, datasheet_id FROM minis WHERE unit_bsdata_id IS NULL'
    ).fetchall()

    processed = matched = 0
    unmatched = []

    for row in rows:
        processed += 1
        did = row['datasheet_id']

        # Resolve unit name: try store first, then Datasheets.csv fallback
        unit_data = store.unit_detail(did)
        unit_name = unit_data['name'] if unit_data else csv_fallback.get(did)

        if not unit_name:
            unmatched.append(('minis', row['id'], did, 'not in data_store'))
            continue

        # 1. Check manual overrides (handles units intentionally absent from BSData)
        if unit_name in overrides:
            override_id = overrides[unit_name]
            if override_id is None:
                unmatched.append(('minis', row['id'], unit_name,
                                  'intentionally absent from BSData'))
                continue
            conn.execute('UPDATE minis SET unit_bsdata_id = ? WHERE id = ?',
                         (override_id, row['id']))
            matched += 1
            continue

        # 2. Normalised name match (handles [Legends] suffix and apostrophe variants)
        match_id = normalised_catalogue.get(normalise_name(unit_name))
        if match_id:
            conn.execute('UPDATE minis SET unit_bsdata_id = ? WHERE id = ?',
                         (match_id, row['id']))
            matched += 1
            continue

        # 3. Unmatched
        unmatched.append(('minis', row['id'], unit_name, 'no match in catalogue_units'))

    conn.commit()
    return processed, matched, unmatched


def migrate_army_units(conn, store):
    rows = conn.execute(
        'SELECT id, datasheet_id FROM army_units WHERE unit_bsdata_id IS NULL'
    ).fetchall()

    processed = matched = 0
    unmatched = []

    for row in rows:
        processed += 1
        did = row['datasheet_id']
        unit_data = store.unit_detail(did)
        if not unit_data:
            unmatched.append(('army_units', row['id'], did, 'not in data_store'))
            continue

        unit_name = unit_data['name']
        bsdata_id = _lookup_unit_bsdata_id(conn, unit_name)
        if bsdata_id:
            conn.execute(
                'UPDATE army_units SET unit_bsdata_id = ? WHERE id = ?',
                (bsdata_id, row['id'])
            )
            matched += 1
        else:
            unmatched.append(('army_units', row['id'], unit_name, 'no match in catalogue_units'))

    conn.commit()
    return processed, matched, unmatched


def migrate_arsenal_weapons(conn):
    rows = conn.execute(
        'SELECT id, name, faction_name FROM arsenal_weapon WHERE weapon_bsdata_id IS NULL'
    ).fetchall()

    processed = matched = 0
    unmatched = []

    for row in rows:
        processed += 1
        weapon_name = row['name']
        faction_name = row['faction_name'] or ''

        # Try faction-scoped match first
        match = None
        if faction_name:
            match = conn.execute('''
                SELECT DISTINCT cw.bsdata_id
                FROM catalogue_weapons cw
                JOIN catalogue_factions cf ON cw.faction_id = cf.bsdata_id
                WHERE cw.name = ? COLLATE NOCASE
                  AND cf.name LIKE ? COLLATE NOCASE
                LIMIT 1
            ''', (weapon_name, f'%{faction_name}%')).fetchone()

        # Fallback: name-only match
        if not match:
            match = conn.execute(
                'SELECT bsdata_id FROM catalogue_weapons WHERE name = ? COLLATE NOCASE LIMIT 1',
                (weapon_name,)
            ).fetchone()

        if match:
            conn.execute(
                'UPDATE arsenal_weapon SET weapon_bsdata_id = ? WHERE id = ?',
                (match[0], row['id'])
            )
            matched += 1
        else:
            unmatched.append(('arsenal_weapon', row['id'], weapon_name, 'no match in catalogue_weapons'))

    conn.commit()
    return processed, matched, unmatched


def migrate_arsenal_weapon_datasheet(conn, store):
    rows = conn.execute(
        'SELECT weapon_id, datasheet_id, raw_name FROM arsenal_weapon_datasheet WHERE unit_bsdata_id IS NULL'
    ).fetchall()

    processed = matched = 0
    unmatched = []

    for row in rows:
        processed += 1
        did = row['datasheet_id']
        unit_data = store.unit_detail(did)
        if not unit_data:
            unmatched.append(('arsenal_weapon_datasheet',
                              f"{row['weapon_id']}/{did}", did,
                              'not in data_store'))
            continue

        unit_name = unit_data['name']
        bsdata_id = _lookup_unit_bsdata_id(conn, unit_name)
        if bsdata_id:
            conn.execute(
                '''UPDATE arsenal_weapon_datasheet
                   SET unit_bsdata_id = ?
                   WHERE weapon_id = ? AND datasheet_id = ? AND raw_name = ?''',
                (bsdata_id, row['weapon_id'], did, row['raw_name'])
            )
            matched += 1
        else:
            unmatched.append(('arsenal_weapon_datasheet',
                              f"{row['weapon_id']}/{did}", unit_name,
                              'no match in catalogue_units'))

    conn.commit()
    return processed, matched, unmatched


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.environ.get('DB_PATH', os.path.join(script_dir, 'collection.db'))

    print(f'Database: {db_path}')
    print('Loading data_store (CSV)...')
    store = get_store()
    print(f'  Loaded {len(store.datasheets)} datasheets, {len(store.factions)} factions')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure the new column exists (idempotent guard in case db.py hasn't been run)
    existing = [r[1] for r in conn.execute('PRAGMA table_info(arsenal_weapon_datasheet)')]
    if 'unit_bsdata_id' not in existing:
        conn.execute('ALTER TABLE arsenal_weapon_datasheet ADD COLUMN unit_bsdata_id TEXT')
        conn.commit()
        print('  Added arsenal_weapon_datasheet.unit_bsdata_id')

    # Build normalised catalogue: strips [Legends] etc. for flexible matching
    normalised_catalogue = {
        normalise_name(row[0]): row[1]
        for row in conn.execute('SELECT name, bsdata_id FROM catalogue_units').fetchall()
    }

    # Load manual overrides
    overrides = _load_overrides()

    # Build Datasheets.csv fallback for Wahapedia IDs not resolved by data_store
    csv_fallback = {}
    ds_path = os.path.join(script_dir, 'data', 'Datasheets.csv')
    if os.path.exists(ds_path):
        with open(ds_path, encoding='utf-8-sig', newline='') as fh:
            reader = _csv.DictReader(fh, delimiter='|')
            for r in reader:
                wid  = (r.get('id') or '').strip()
                name = (r.get('name') or '').strip()
                if wid and name:
                    csv_fallback[wid] = name

    print('\nRunning migrations...')

    print('  minis...')
    m_proc, m_match, m_un = migrate_minis(conn, store, normalised_catalogue,
                                           overrides, csv_fallback)

    print('  army_units...')
    au_proc, au_match, au_un = migrate_army_units(conn, store)

    print('  arsenal_weapon...')
    aw_proc, aw_match, aw_un = migrate_arsenal_weapons(conn)

    print('  arsenal_weapon_datasheet...')
    awd_proc, awd_match, awd_un = migrate_arsenal_weapon_datasheet(conn, store)

    conn.close()

    all_unmatched = m_un + au_un + aw_un + awd_un
    timestamp = datetime.now().isoformat(timespec='seconds')

    lines = [
        '=== BSData Migration Report ===',
        f'Timestamp: {timestamp}',
        '',
        f'minis:                     {m_proc:5d} rows processed, {m_match:5d} matched, {len(m_un):5d} unmatched',
        f'army_units:                {au_proc:5d} rows processed, {au_match:5d} matched, {len(au_un):5d} unmatched',
        f'arsenal_weapon:            {aw_proc:5d} rows processed, {aw_match:5d} matched, {len(aw_un):5d} unmatched',
        f'arsenal_weapon_datasheet:  {awd_proc:5d} rows processed, {awd_match:5d} matched, {len(awd_un):5d} unmatched',
        '',
    ]

    if all_unmatched:
        lines.append('=== Unmatched rows (require manual resolution) ===')
        lines.append(f'{"Table":<30} {"Row ID":<30} {"Key":<50} Reason')
        lines.append('-' * 130)
        for table, row_id, key, reason in all_unmatched:
            lines.append(f'{table:<30} {str(row_id):<30} {key:<50} {reason}')
    else:
        lines.append('All rows matched successfully.')

    report = '\n'.join(lines)
    report_path = os.path.join(script_dir, 'migration_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report + '\n')

    # Print with safe encoding for Windows console
    safe = report.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(
        sys.stdout.encoding or 'utf-8', errors='replace')
    print('\n' + safe)
    print(f'\nReport written to {report_path}')


if __name__ == '__main__':
    main()
