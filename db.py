"""Database connection, schema initialisation, and legacy migration."""
import json
import os
import re
import sqlite3
import time
import uuid

from utils import _as_int, _as_bool

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "collection.db")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    # synchronous=NORMAL is the recommended, corruption-safe setting under WAL
    # (journal_mode is persisted in the DB header by init_db).
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(c, table):
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _columns(c, table):
    return [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]


def _unique_table_name(c, stem):
    name = stem
    i = 1
    while _table_exists(c, name):
        name = f"{stem}_{i}"
        i += 1
    return name


def _row_value(row, *names, default=""):
    keys = row.keys()
    for name in names:
        if name in keys and row[name] not in (None, ""):
            return row[name]
    return default


def _legacy_wargear(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(x)[:160] for x in value if str(x).strip()][:60]
    text = str(value).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x)[:160] for x in parsed if str(x).strip()][:60]
    except (TypeError, ValueError):
        pass
    return [p.strip()[:160] for p in re.split(r"[,;\n]+", text) if p.strip()][:60]


def _migrate_legacy_loadouts(c, legacy_photos_table):
    if not _table_exists(c, "loadouts"):
        return
    legacy = c.execute("SELECT * FROM loadouts").fetchall()
    if not legacy:
        c.execute("DROP TABLE loadouts")
        if legacy_photos_table:
            c.execute(f"DROP TABLE {legacy_photos_table}")
        return

    loadout_to_model = {}
    now = time.time()
    for r in legacy:
        did = str(_row_value(r, "datasheet_id", "unit_id", "did")).strip()
        if not did:
            continue
        label = str(_row_value(r, "label", "name", "loadout_name"))[:120].strip()
        notes = str(_row_value(r, "notes", "note"))[:2000]
        wargear = _legacy_wargear(_row_value(r, "wargear", "gear", "loadout"))
        count = max(1, min(500, _as_int(_row_value(r, "quantity", "count", "qty", "owned"), 1)))
        finished = int(_as_bool(_row_value(r, "finished", "painted", default=0)))
        created_at = _row_value(r, "created_at", "updated_at", default=now)
        try:
            created_at = float(created_at)
        except (TypeError, ValueError):
            created_at = now

        first_model_id = None
        for _ in range(count):
            mid = uuid.uuid4().hex
            if first_model_id is None:
                first_model_id = mid
            stage = "finished" if finished else "unbuilt"
            c.execute("""INSERT INTO minis(id, datasheet_id, label, wargear, notes, finished, stage, created_at)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (mid, did, label, json.dumps(wargear), notes, finished, stage, created_at))
        legacy_id = str(_row_value(r, "id", "loadout_id", default="")).strip()
        if legacy_id and first_model_id:
            loadout_to_model[legacy_id] = (first_model_id, did)

    if legacy_photos_table:
        for p in c.execute(f"SELECT * FROM {legacy_photos_table}").fetchall():
            legacy_id = str(_row_value(p, "loadout_id", "configuration_id", "config_id", "model_id")).strip()
            mapped = loadout_to_model.get(legacy_id)
            filename = str(_row_value(p, "filename", "file", "path")).strip()
            if not mapped or not filename:
                continue
            pid = str(_row_value(p, "id", default="")).strip() or uuid.uuid4().hex
            uploaded_at = _row_value(p, "uploaded_at", "created_at", default=now)
            try:
                uploaded_at = float(uploaded_at)
            except (TypeError, ValueError):
                uploaded_at = now
            caption = str(_row_value(p, "caption", default=""))[:300]
            mid, did = mapped
            c.execute("""INSERT OR IGNORE INTO photos(id, mini_id, datasheet_id, filename, caption, uploaded_at)
                         VALUES(?,?,?,?,?,?)""", (pid, mid, did, filename, caption, uploaded_at))
        c.execute(f"DROP TABLE {legacy_photos_table}")
    c.execute("DROP TABLE loadouts")


def init_db():
    with db() as c:
        # WAL persists in the DB header, so this one-time switch sticks for all
        # future connections. Set before any DML opens a transaction.
        c.execute("PRAGMA journal_mode = WAL")

        # Migration: rename models table to minis
        if _table_exists(c, "models") and not _table_exists(c, "minis"):
            c.execute("ALTER TABLE models RENAME TO minis")

        # Migration: rename model_id column to mini_id in photos
        if _table_exists(c, "photos") and "model_id" in _columns(c, "photos") \
                and "mini_id" not in _columns(c, "photos"):
            c.execute("ALTER TABLE photos RENAME COLUMN model_id TO mini_id")

        legacy_photos_table = None
        if _table_exists(c, "photos") and "mini_id" not in _columns(c, "photos"):
            legacy_photos_table = _unique_table_name(c, "photos_legacy")
            c.execute(f"ALTER TABLE photos RENAME TO {legacy_photos_table}")

        c.execute("""CREATE TABLE IF NOT EXISTS minis(
            id TEXT PRIMARY KEY,
            datasheet_id TEXT NOT NULL,
            catalogue_model_id TEXT DEFAULT NULL,
            label TEXT DEFAULT '',
            wargear TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            finished INTEGER DEFAULT 0,
            stage TEXT DEFAULT 'unbuilt',
            multikit_group TEXT DEFAULT NULL,
            created_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS photos(
            id TEXT PRIMARY KEY,
            mini_id TEXT NOT NULL,
            datasheet_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            caption TEXT DEFAULT '',
            uploaded_at REAL NOT NULL)""")

        # Unit-level "Work in Progress" notes: one free-text record per
        # datasheet, independent of any individual mini.
        c.execute("""CREATE TABLE IF NOT EXISTS unit_wip(
            datasheet_id TEXT PRIMARY KEY,
            notes TEXT DEFAULT '',
            updated_at REAL NOT NULL)""")

        # Unit-level WIP photos: shared gallery for the datasheet, separate
        # from the per-mini `photos` table (which requires a mini_id).
        c.execute("""CREATE TABLE IF NOT EXISTS unit_wip_photos(
            id TEXT PRIMARY KEY,
            datasheet_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            caption TEXT DEFAULT '',
            uploaded_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS favourite_factions(
            faction_id TEXT PRIMARY KEY,
            created_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS army_lists(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            faction_id TEXT NOT NULL,
            detachment_id TEXT DEFAULT '',
            points_limit INTEGER DEFAULT 2000,
            notes TEXT DEFAULT '',
            created_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS army_units(
            id TEXT PRIMARY KEY,
            army_list_id TEXT NOT NULL,
            datasheet_id TEXT NOT NULL,
            squad_size INTEGER NOT NULL DEFAULT 1,
            assigned_count INTEGER DEFAULT 0,
            enhancement_id TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0)""")

        c.execute("""CREATE TABLE IF NOT EXISTS purchases(
            id TEXT PRIMARY KEY,
            box_set_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            notes TEXT DEFAULT '',
            bought_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS custom_box_sets(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            faction_id TEXT DEFAULT '',
            game_system TEXT DEFAULT 'Warhammer 40,000',
            release_date TEXT DEFAULT '',
            manufacturer TEXT DEFAULT 'Games Workshop',
            status TEXT DEFAULT 'manual',
            notes TEXT DEFAULT '',
            sources TEXT DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL)""")

        c.execute("""CREATE TABLE IF NOT EXISTS custom_box_set_contents(
            box_set_id TEXT NOT NULL,
            datasheet_id TEXT NOT NULL,
            catalogue_model_id TEXT DEFAULT NULL,
            datasheet_count INTEGER NOT NULL DEFAULT 1,
            physical_miniatures INTEGER NOT NULL DEFAULT 1,
            notes TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            multikit_group TEXT DEFAULT NULL)""")

        # Migration: add multikit_group to existing tables
        if _table_exists(c, "custom_box_set_contents") and \
                "multikit_group" not in _columns(c, "custom_box_set_contents"):
            c.execute("ALTER TABLE custom_box_set_contents ADD COLUMN multikit_group TEXT DEFAULT NULL")

        # Migration: add catalogue_model_id to custom box contents for sculpt-aware box tracking
        if _table_exists(c, "custom_box_set_contents") and \
                "catalogue_model_id" not in _columns(c, "custom_box_set_contents"):
            c.execute("ALTER TABLE custom_box_set_contents ADD COLUMN catalogue_model_id TEXT DEFAULT NULL")

        # Migration: add expected_minis to custom_box_sets
        if _table_exists(c, "custom_box_sets") and \
                "expected_minis" not in _columns(c, "custom_box_sets"):
            c.execute("ALTER TABLE custom_box_sets ADD COLUMN expected_minis INTEGER DEFAULT NULL")

        # Migration: add catalogue_model_id to minis for sculpt-aware tracking
        if _table_exists(c, "minis") and \
                "catalogue_model_id" not in _columns(c, "minis"):
            c.execute("ALTER TABLE minis ADD COLUMN catalogue_model_id TEXT DEFAULT NULL")

        # Migration: add stage column (replaces finished for painting stage tracking)
        if _table_exists(c, "minis") and "stage" not in _columns(c, "minis"):
            c.execute("ALTER TABLE minis ADD COLUMN stage TEXT DEFAULT 'unbuilt'")
            if "finished" in _columns(c, "minis"):
                c.execute(
                    "UPDATE minis SET stage = CASE WHEN finished=1 THEN 'finished' ELSE 'unbuilt' END"
                )

        # Migration: add multikit_group to track unresolved multikit minis
        if _table_exists(c, "minis") and "multikit_group" not in _columns(c, "minis"):
            c.execute("ALTER TABLE minis ADD COLUMN multikit_group TEXT DEFAULT NULL")

        _migrate_legacy_loadouts(c, legacy_photos_table)

        # Wahapedia catalogue tables (populated by wahapedia_importer.py). The
        # bsdata_id / unit_bsdata_id column names are a legacy misnomer: they now
        # hold native Wahapedia ids (datasheet ids and faction codes).
        c.execute("""CREATE TABLE IF NOT EXISTS catalogue_factions (
            bsdata_id   TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            cat_file    TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS catalogue_units (
            bsdata_id       TEXT PRIMARY KEY,
            faction_id      TEXT NOT NULL REFERENCES catalogue_factions(bsdata_id),
            name            TEXT NOT NULL,
            role            TEXT,
            points          INTEGER,
            virtual         INTEGER DEFAULT 0,
            legend          TEXT,
            link            TEXT,
            stats_json      TEXT,
            abilities_json  TEXT,
            keywords_json   TEXT,
            composition_json TEXT,
            wargear_options_json TEXT,
            loadout          TEXT,
            leader_targets_json TEXT,
            points_tiers_json TEXT,
            imported_at     TEXT NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS catalogue_weapons (
            bsdata_id    TEXT PRIMARY KEY,
            faction_id   TEXT NOT NULL REFERENCES catalogue_factions(bsdata_id),
            name         TEXT NOT NULL,
            weapon_type  TEXT NOT NULL,
            range        TEXT,
            attacks      TEXT,
            skill        TEXT,
            strength     TEXT,
            ap           TEXT,
            damage       TEXT,
            keywords     TEXT,
            description  TEXT,
            imported_at  TEXT NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS catalogue_unit_weapons (
            unit_id    TEXT NOT NULL REFERENCES catalogue_units(bsdata_id),
            weapon_id  TEXT NOT NULL REFERENCES catalogue_weapons(bsdata_id),
            PRIMARY KEY (unit_id, weapon_id)
        )""")

        # Legacy id columns on existing tables (now hold Wahapedia ids)
        if "unit_bsdata_id" not in _columns(c, "minis"):
            c.execute("ALTER TABLE minis ADD COLUMN unit_bsdata_id TEXT")

        if "unit_bsdata_id" not in _columns(c, "army_units"):
            c.execute("ALTER TABLE army_units ADD COLUMN unit_bsdata_id TEXT")

        # Arsenal owns these tables and initialises them after this general
        # schema pass.  On a brand-new database they do not exist yet.
        if _table_exists(c, "arsenal_weapon") and "weapon_bsdata_id" not in _columns(c, "arsenal_weapon"):
            c.execute("ALTER TABLE arsenal_weapon ADD COLUMN weapon_bsdata_id TEXT")

        if _table_exists(c, "arsenal_weapon_datasheet") and "unit_bsdata_id" not in _columns(c, "arsenal_weapon_datasheet"):
            c.execute("ALTER TABLE arsenal_weapon_datasheet ADD COLUMN unit_bsdata_id TEXT")

        # Backfill unit_bsdata_id for any minis that have a resolvable datasheet_id
        # but NULL unit_bsdata_id. Handles minis created before Bug 1 was fixed.
        from data_store import get_store as _get_store
        try:
            _store = _get_store()
            null_rows = c.execute(
                'SELECT id, datasheet_id FROM minis WHERE unit_bsdata_id IS NULL'
            ).fetchall()
            for row in null_rows:
                unit = _store.ds_by_id.get(row['datasheet_id'])
                if unit:
                    c.execute(
                        'UPDATE minis SET unit_bsdata_id=? WHERE id=?',
                        (unit['id'], row['id'])
                    )
        except Exception:
            pass  # data_store may not be ready on first run before catalogue import

        # Keep the empty-database schema compatible with data_store as well as
        # with the importer, which may add these fields later on existing DBs.
        for stmt in [
            "ALTER TABLE catalogue_units ADD COLUMN composition_json TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN wargear_options_json TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN loadout TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN leader_targets_json TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN points_tiers_json TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN legend TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN link TEXT",
            "ALTER TABLE catalogue_units ADD COLUMN virtual INTEGER DEFAULT 0",
            "ALTER TABLE catalogue_weapons ADD COLUMN description TEXT",
        ]:
            try:
                c.execute(stmt)
            except Exception:
                pass

        # Indexes on the collection tables' frequently-filtered foreign-key
        # columns. Without these, per-request lookups full-scan the table and
        # scale linearly with the collection. (The arsenal_* tables already
        # carry their own equivalent indexes.)
        for stmt in [
            "CREATE INDEX IF NOT EXISTS idx_minis_datasheet ON minis(datasheet_id)",
            "CREATE INDEX IF NOT EXISTS idx_minis_unit_bsdata ON minis(unit_bsdata_id)",
            "CREATE INDEX IF NOT EXISTS idx_photos_mini ON photos(mini_id)",
            "CREATE INDEX IF NOT EXISTS idx_wip_photos_did ON unit_wip_photos(datasheet_id)",
            "CREATE INDEX IF NOT EXISTS idx_army_units_list ON army_units(army_list_id)",
            "CREATE INDEX IF NOT EXISTS idx_army_units_datasheet ON army_units(datasheet_id)",
            "CREATE INDEX IF NOT EXISTS idx_box_contents_box ON custom_box_set_contents(box_set_id)",
            "CREATE INDEX IF NOT EXISTS idx_purchases_box ON purchases(box_set_id)",
        ]:
            c.execute(stmt)

        # MFM points overlay tables (separate from the Wahapedia catalogue;
        # applied non-destructively at read time by data_store). Imported lazily
        # to avoid a circular import; reuses this open connection so the schema
        # is created in the same transaction.
        try:
            import mfm_store
            mfm_store.ensure_tables(c)
        except Exception:
            pass
