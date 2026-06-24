"""Munitorum Field Manual (MFM) points overlay.

The Wahapedia data the app imports lags behind the latest MFM points. This
module holds a parallel set of "resolved" MFM points, keyed to the same
Wahapedia datasheet and enhancement ids, and a per-faction on/off switch. When
a faction is switched on, data_store applies the MFM values at read time over
the Wahapedia base data. Default for every faction is off, so a fresh install
behaves exactly as it does today.

Nothing here mutates the catalogue_* tables, the Wahapedia CSVs, or the import
pipeline. The overlay lives entirely in its own mfm_* tables and is applied
non-destructively in memory by data_store.DataStore._apply_mfm_overrides.

Resolution is by normalised name within the resolved faction code:
  - units: MFM unit name to a catalogue_units datasheet id
  - enhancements: (faction, detachment name, enhancement name) to an
    Enhancements.csv id
Names that do not map are recorded in mfm_unmatched and simply fall back to
Wahapedia (they never show MFM values).
"""
import csv
import json
import os
import re
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "collection.db")
DATA_DIR = os.path.join(BASE, "data")
MFM_DIR = os.path.join(DATA_DIR, "mfm")
UNITS_CSV = os.path.join(MFM_DIR, "mfm_unit_points.csv")
ENH_CSV = os.path.join(MFM_DIR, "mfm_enhancements.csv")

# MFM publishes faction slugs that do not all map one-to-one onto Wahapedia
# faction codes. Space Marine chapters collapse to the single "SM" code (the
# catalogue carries one Space Marines faction), and a few slugs differ from the
# slug embedded in Factions.csv. Anything not listed here resolves through the
# Factions.csv slug map instead.
FACTION_ALIAS = {
    "black-templars": "SM", "blood-angels": "SM", "dark-angels": "SM",
    "deathwatch": "SM", "space-wolves": "SM",
    "emperors-children": "EC", "tau-empire": "TAU",
    "titan-legions": "TL", "chaos-titan-legions": "TL",
}

# The MFM uses a few slugs which differ from the faction-export links.  Keep
# one canonical MFM slug for generic parent-faction data; chapter names are
# converted to their own MFM slug at read time.
CANONICAL_SLUG_BY_CODE = {
    "SM": "space-marines", "EC": "emperors-children", "TAU": "tau-empire",
    "TL": "titan-legions",
}

# MFM batch-pricing wording to the suffix shown after the model-count line. The
# model count stays first so army.py _points_for can still parse "N model".
TIER_SUFFIX = {
    "YOUR UNIT COSTS": "",
    "YOUR 1ST TO 2ND UNITS COST": " (1st-2nd)",
    "YOUR 3RD + UNIT COSTS": " (3rd+)",
    "YOUR 1ST UNIT COSTS": " (1st)",
    "YOUR 2ND + UNIT COSTS": " (2nd+)",
    "YOUR 1ST TO 3RD UNITS COST": " (1st-3rd)",
    "YOUR 4TH + UNIT COSTS": " (4th+)",
}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(c, table):
    return c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(c, table):
    return [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]


def _norm(s):
    s = (s or "").upper().replace("&", " AND ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", s)).strip()


def _slug_to_code_map():
    """slug -> faction code, from the /factions/<slug> link in Factions.csv."""
    slug_map = {}
    path = os.path.join(DATA_DIR, "Factions.csv")
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="|"):
                m = re.search(r"/factions/([a-z0-9-]+)", row.get("link") or "")
                if m:
                    slug_map[m.group(1)] = (row.get("id") or "").strip()
    except OSError:
        pass
    return slug_map


def _resolve_code(slug, slug_map):
    """Faction code for an MFM faction slug, or None when it does not resolve."""
    return FACTION_ALIAS.get(slug) or slug_map.get(slug)


def faction_slug_for_store_id(faction_id):
    """Return the MFM source slug for a DataStore faction id.

    ``data_store`` splits Space Marine chapters into synthetic ids such as
    ``SM::Blood Angels`` after reading the catalogue.  Their points must keep
    the chapter MFM source rather than sharing the generic Space Marines row.
    """
    faction_id = (faction_id or "").strip()
    if "::" in faction_id:
        _parent, chapter = faction_id.split("::", 1)
        return re.sub(r"[^a-z0-9]+", "-", chapter.lower()).strip("-")
    if faction_id in CANONICAL_SLUG_BY_CODE:
        return CANONICAL_SLUG_BY_CODE[faction_id]
    for slug, code in _slug_to_code_map().items():
        if code == faction_id:
            return slug
    return ""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_tables(c=None):
    """Create the mfm_* tables and indexes idempotently. Pass an open
    connection to reuse it (the caller commits); otherwise one is opened and
    committed here."""
    own = c is None
    if own:
        c = _conn()
    try:
        # Earlier versions keyed resolved rows by datasheet/enhancement alone.
        # That made the final import win when (for example) Blood Angels and
        # Black Templars supplied different values for the same SM datasheet.
        # These are derived tables, so recreate the incompatible layout and
        # let auto_import_if_empty rebuild it from the source CSVs.
        unit_columns = _columns(c, "mfm_resolved_units") if _table_exists(c, "mfm_resolved_units") else []
        enh_columns = _columns(c, "mfm_resolved_enhancements") if _table_exists(c, "mfm_resolved_enhancements") else []
        state_columns = _columns(c, "mfm_faction_state") if _table_exists(c, "mfm_faction_state") else []
        legacy_enabled_codes = []
        if unit_columns and "faction_slug" not in unit_columns:
            if state_columns and "faction_code" in state_columns:
                legacy_enabled_codes = [r["faction_code"] for r in c.execute(
                    "SELECT faction_code FROM mfm_faction_state WHERE enabled=1")]
            c.execute("DROP TABLE mfm_resolved_units")
            c.execute("DROP TABLE IF EXISTS mfm_resolved_enhancements")
            c.execute("DROP TABLE IF EXISTS mfm_faction_state")
            c.execute("DELETE FROM mfm_meta")
            enh_columns = []
            state_columns = []
        if enh_columns and "faction_slug" not in enh_columns:
            c.execute("DROP TABLE mfm_resolved_enhancements")
        if state_columns and "faction_slug" not in state_columns:
            c.execute("DROP TABLE mfm_faction_state")
        c.execute("""CREATE TABLE IF NOT EXISTS mfm_meta(
            key TEXT PRIMARY KEY,
            value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS mfm_resolved_units(
            datasheet_id TEXT NOT NULL,
            faction_slug TEXT NOT NULL,
            faction_code TEXT NOT NULL,
            base_points  INTEGER,
            tiers_json   TEXT,
            PRIMARY KEY(datasheet_id, faction_slug))""")
        c.execute("""CREATE TABLE IF NOT EXISTS mfm_resolved_enhancements(
            enhancement_id TEXT NOT NULL,
            faction_slug TEXT NOT NULL,
            faction_code   TEXT NOT NULL,
            points         INTEGER,
            PRIMARY KEY(enhancement_id, faction_slug))""")
        c.execute("""CREATE TABLE IF NOT EXISTS mfm_unmatched(
            kind         TEXT,
            faction_slug TEXT,
            name         TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS mfm_faction_state(
            faction_slug TEXT PRIMARY KEY,
            enabled      INTEGER NOT NULL DEFAULT 0)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mfm_units_slug "
                  "ON mfm_resolved_units(faction_slug)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mfm_enh_slug "
                  "ON mfm_resolved_enhancements(faction_slug)")
        for code in legacy_enabled_codes:
            slug = faction_slug_for_store_id(code)
            if slug:
                c.execute(
                    "INSERT OR IGNORE INTO mfm_faction_state(faction_slug, enabled) VALUES(?,1)",
                    (slug,),
                )
        if own:
            c.commit()
    finally:
        if own:
            c.close()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _build_unit_index(c):
    """{faction_code: {norm(name): [datasheet_id, ...]}} over catalogue_units.

    The catalogue stores chapter datasheets under the parent "SM" code (the
    chapter split is a load-time view in data_store), so MFM chapter slugs that
    alias to "SM" find their datasheets here directly."""
    index = {}
    for u in c.execute("SELECT bsdata_id, faction_id, name FROM catalogue_units"):
        index.setdefault(u["faction_id"], {}).setdefault(
            _norm(u["name"]), []).append(u["bsdata_id"])
    return index


def _import_units(c, units_csv, slug_map):
    """Populate mfm_resolved_units. Returns (total_rows, matched_groups)."""
    unit_index = _build_unit_index(c)

    groups = {}
    total = 0
    version = ""
    with open(units_csv, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            if not version:
                version = (row.get("version") or "").strip()
            key = (row.get("faction") or "", row.get("unit") or "")
            groups.setdefault(key, []).append(row)

    matched = 0
    for (slug, unit), rows in groups.items():
        code = _resolve_code(slug, slug_map)
        bucket = unit_index.get(code, {}) if code else {}
        ids = bucket.get(_norm(unit), [])
        if not ids:
            c.execute("INSERT INTO mfm_unmatched(kind, faction_slug, name) "
                      "VALUES('unit',?,?)", (slug, unit))
            continue

        tiers = []
        for r in rows:
            tier = (r.get("cost_tier") or "").strip()
            models = (r.get("models") or "").strip()
            # WARGEAR OPTIONS rows (and any blank model count) are upgrade
            # add-ons, not a unit price, so they are excluded.
            if tier == "WARGEAR OPTIONS" or not models:
                continue
            try:
                mc = int(models)
                pts = int((r.get("points") or "").strip())
            except ValueError:
                continue
            desc = ("1 model" if mc == 1 else f"{mc} models") + TIER_SUFFIX.get(tier, "")
            tiers.append({"cost": pts, "description": desc})

        if not tiers:
            c.execute("INSERT INTO mfm_unmatched(kind, faction_slug, name) "
                      "VALUES('unit',?,?)", (slug, unit))
            continue

        base = min(t["cost"] for t in tiers)
        # A single tier collapses to base only, matching the Wahapedia importer
        # (wahapedia_importer.build_costs): no description for a lone price.
        tiers_json = None if len(tiers) == 1 else json.dumps(tiers)
        matched += 1
        for did in ids:
            c.execute(
                "INSERT OR REPLACE INTO mfm_resolved_units"
                "(datasheet_id, faction_slug, faction_code, base_points, tiers_json) "
                "VALUES(?,?,?,?,?)", (did, slug, code, base, tiers_json))

    return total, matched, version


def _import_enhancements(c, enh_csv, slug_map):
    """Populate mfm_resolved_enhancements. Returns (total_rows, matched)."""
    # detachment_id -> (faction_code, detachment_name)
    det_map = {}
    det_path = os.path.join(DATA_DIR, "Detachments.csv")
    try:
        with open(det_path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="|"):
                dtid = (row.get("id") or "").strip()
                if dtid:
                    det_map[dtid] = ((row.get("faction_id") or "").strip(),
                                     (row.get("name") or "").strip())
    except OSError:
        pass

    # (faction_code, norm(detachment_name), norm(enhancement_name)) -> id
    enh_index = {}
    enh_path = os.path.join(DATA_DIR, "Enhancements.csv")
    try:
        with open(enh_path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="|"):
                eid = (row.get("id") or "").strip()
                if not eid:
                    continue
                dtid = (row.get("detachment_id") or "").strip()
                fac, dname = det_map.get(
                    dtid, ((row.get("faction_id") or "").strip(),
                           (row.get("detachment") or "").strip()))
                key = (fac, _norm(dname), _norm(row.get("name") or ""))
                enh_index[key] = eid
    except OSError:
        pass

    total = 0
    matched = 0
    with open(enh_csv, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            slug = row.get("faction") or ""
            enhn = row.get("enhancement") or ""
            code = _resolve_code(slug, slug_map)
            key = (code, _norm(row.get("detachment") or ""), _norm(enhn))
            eid = enh_index.get(key) if code else None
            if not eid:
                c.execute("INSERT INTO mfm_unmatched(kind, faction_slug, name) "
                          "VALUES('enhancement',?,?)", (slug, enhn))
                continue
            try:
                pts = int((row.get("points") or "").strip())
            except ValueError:
                c.execute("INSERT INTO mfm_unmatched(kind, faction_slug, name) "
                          "VALUES('enhancement',?,?)", (slug, enhn))
                continue
            c.execute(
                "INSERT OR REPLACE INTO mfm_resolved_enhancements"
                "(enhancement_id, faction_slug, faction_code, points) VALUES(?,?,?,?)",
                (eid, slug, code, pts))
            matched += 1

    return total, matched


def import_mfm(units_csv=None, enh_csv=None):
    """Wipe and repopulate the resolved and unmatched tables plus mfm_meta from
    the MFM CSVs. mfm_faction_state is preserved so the user's toggles survive a
    re-import. Returns a small summary dict for logging and tests."""
    units_csv = units_csv or UNITS_CSV
    enh_csv = enh_csv or ENH_CSV
    slug_map = _slug_to_code_map()

    c = _conn()
    try:
        ensure_tables(c)
        c.execute("DELETE FROM mfm_resolved_units")
        c.execute("DELETE FROM mfm_resolved_enhancements")
        c.execute("DELETE FROM mfm_unmatched")
        c.execute("DELETE FROM mfm_meta")

        unit_rows, matched_units, version = _import_units(c, units_csv, slug_map)
        enh_rows, matched_enh = _import_enhancements(c, enh_csv, slug_map)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for k, v in (("version", version), ("imported_at", now),
                     ("unit_rows", str(unit_rows)), ("enh_rows", str(enh_rows))):
            c.execute("INSERT OR REPLACE INTO mfm_meta(key, value) VALUES(?,?)",
                      (k, v))
        c.commit()
    finally:
        c.close()

    return {"version": version, "imported_at": now,
            "unit_rows": unit_rows, "matched_units": matched_units,
            "enh_rows": enh_rows, "matched_enh": matched_enh}


def auto_import_if_empty():
    """Seed the resolved data on first boot, without a manual step, when the
    table is empty and both CSVs are present."""
    try:
        c = _conn()
        try:
            ensure_tables(c)
            empty = c.execute(
                "SELECT COUNT(*) n FROM mfm_resolved_units").fetchone()["n"] == 0
        finally:
            c.close()
    except Exception:
        return
    if empty and os.path.exists(UNITS_CSV) and os.path.exists(ENH_CSV):
        try:
            import_mfm()
        except (OSError, sqlite3.Error):
            # A first-run or isolated test database may not yet have the
            # Wahapedia catalogue tables. It can be imported after the
            # catalogue is available instead of preventing application startup.
            return


# ---------------------------------------------------------------------------
# Read side: applied by data_store
# ---------------------------------------------------------------------------

def enabled_overrides():
    """Return (unit_overrides, enh_overrides) for factions toggled on.

    unit_overrides: {(datasheet_id, faction_slug): (base_points, tiers_or_None)}
    enh_overrides:  {(enhancement_id, faction_slug): points}
    active_sources: {faction_code: faction_slug}

    Returns empty dicts if the tables are missing (defensive, first boot)."""
    unit_ov = {}
    enh_ov = {}
    active_sources = {}
    try:
        c = _conn()
        try:
            enabled = [r["faction_slug"] for r in c.execute(
                "SELECT faction_slug FROM mfm_faction_state WHERE enabled=1")]
            if not enabled:
                return unit_ov, enh_ov, active_sources
            marks = ",".join("?" * len(enabled))
            for r in c.execute(
                    "SELECT DISTINCT faction_code, faction_slug "
                    f"FROM mfm_resolved_units WHERE faction_slug IN ({marks}) "
                    "ORDER BY faction_code, faction_slug", enabled):
                active_sources.setdefault(r["faction_code"], r["faction_slug"])
            for r in c.execute(
                    "SELECT datasheet_id, faction_slug, base_points, tiers_json "
                    f"FROM mfm_resolved_units WHERE faction_slug IN ({marks})",
                    enabled):
                tiers = json.loads(r["tiers_json"]) if r["tiers_json"] else None
                unit_ov[(r["datasheet_id"], r["faction_slug"])] = (r["base_points"], tiers)
            for r in c.execute(
                    "SELECT enhancement_id, faction_slug, points "
                    f"FROM mfm_resolved_enhancements WHERE faction_slug IN ({marks})",
                    enabled):
                enh_ov[(r["enhancement_id"], r["faction_slug"])] = r["points"]
        finally:
            c.close()
    except Exception:
        return {}, {}, {}
    return unit_ov, enh_ov, active_sources


def meta_version():
    """The loaded MFM version tag (e.g. "v1.0"), or "" when not imported."""
    try:
        c = _conn()
        try:
            row = c.execute(
                "SELECT value FROM mfm_meta WHERE key='version'").fetchone()
            return row["value"] if row else ""
        finally:
            c.close()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Toggle and status
# ---------------------------------------------------------------------------

def set_faction(slug, enabled):
    """Select or clear one MFM source within its underlying faction.

    A single global datasheet view cannot simultaneously show conflicting
    chapter prices for the same Space Marine unit. Selecting a chapter source
    therefore turns off the other sources which resolve to that parent code.
    """
    c = _conn()
    try:
        ensure_tables(c)
        row = c.execute(
            "SELECT faction_code FROM mfm_resolved_units WHERE faction_slug=? LIMIT 1",
            (slug,),
        ).fetchone()
        if not row:
            return False
        code = row["faction_code"]
        c.execute(
            "UPDATE mfm_faction_state SET enabled=0 WHERE faction_slug IN "
            "(SELECT DISTINCT faction_slug FROM mfm_resolved_units WHERE faction_code=?)",
            (code,),
        )
        c.execute(
            "INSERT INTO mfm_faction_state(faction_slug, enabled) VALUES(?,?) "
            "ON CONFLICT(faction_slug) DO UPDATE SET enabled=excluded.enabled",
            (slug, 1 if enabled else 0))
        c.commit()
    finally:
        c.close()
    return True


def set_all(enabled):
    """Turn overlays on/off without enabling conflicting chapter sources."""
    c = _conn()
    try:
        ensure_tables(c)
        c.execute("UPDATE mfm_faction_state SET enabled=0")
        sources = {}
        for r in c.execute(
                "SELECT DISTINCT faction_code, faction_slug FROM mfm_resolved_units "
                "ORDER BY faction_code, faction_slug"):
            sources.setdefault(r["faction_code"], []).append(r["faction_slug"])
        for code, slugs in sources.items():
            preferred = faction_slug_for_store_id(code)
            slug = preferred if preferred in slugs else slugs[0]
            c.execute(
                "INSERT INTO mfm_faction_state(faction_slug, enabled) VALUES(?,?) "
                "ON CONFLICT(faction_slug) DO UPDATE SET enabled=excluded.enabled",
                (slug, 1 if enabled else 0))
        c.commit()
    finally:
        c.close()


def status():
    """Snapshot for the UI and the toggle endpoints.

    {version, imported_at, any_enabled, unmatched_units, unmatched_enh,
     factions: [{code, name, enabled, matched_units, matched_enh}]}

    factions lists MFM source slugs with at least one resolved unit."""
    c = _conn()
    try:
        ensure_tables(c)
        meta = {r["key"]: r["value"]
                for r in c.execute("SELECT key, value FROM mfm_meta")}
        unit_rows = c.execute(
            "SELECT faction_slug, faction_code, COUNT(*) n FROM mfm_resolved_units "
            "GROUP BY faction_slug, faction_code").fetchall()
        unit_counts = {r["faction_slug"]: r["n"] for r in unit_rows}
        faction_codes = {r["faction_slug"]: r["faction_code"] for r in unit_rows}
        enh_counts = {r["faction_slug"]: r["n"] for r in c.execute(
            "SELECT faction_slug, COUNT(*) n FROM mfm_resolved_enhancements "
            "GROUP BY faction_slug")}
        state = {r["faction_slug"]: bool(r["enabled"]) for r in c.execute(
            "SELECT faction_slug, enabled FROM mfm_faction_state")}
        names = {r["bsdata_id"]: r["name"] for r in c.execute(
            "SELECT bsdata_id, name FROM catalogue_factions")}
        unmatched_units = c.execute(
            "SELECT COUNT(*) n FROM mfm_unmatched WHERE kind='unit'").fetchone()["n"]
        unmatched_enh = c.execute(
            "SELECT COUNT(*) n FROM mfm_unmatched WHERE kind='enhancement'").fetchone()["n"]

        slugs = sorted(unit_counts.keys(),
                       key=lambda slug: slug.replace("-", " ").lower())
        factions = []
        any_enabled = False
        for slug in slugs:
            en = state.get(slug, False)
            any_enabled = any_enabled or en
            code = faction_codes[slug]
            name = names.get(code, slug.replace("-", " ").title())
            if slug != faction_slug_for_store_id(code):
                name = slug.replace("-", " ").title()
            factions.append({
                "code": slug,
                "name": name,
                "enabled": en,
                "matched_units": unit_counts.get(slug, 0),
                "matched_enh": enh_counts.get(slug, 0),
            })
        return {
            "version": meta.get("version", ""),
            "imported_at": meta.get("imported_at", ""),
            "any_enabled": any_enabled,
            "unmatched_units": unmatched_units,
            "unmatched_enh": unmatched_enh,
            "factions": factions,
        }
    finally:
        c.close()
