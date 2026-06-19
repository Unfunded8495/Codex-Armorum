"""Populate the catalogue_* SQLite tables from the Wahapedia CSV export.

This replaces the old BSData XML importer. The four catalogue tables
(catalogue_factions, catalogue_units, catalogue_weapons,
catalogue_unit_weapons) are dropped and repopulated on every run, keyed by
native Wahapedia ids:

  catalogue_factions.bsdata_id  = Wahapedia faction code (e.g. "CSM")
  catalogue_units.bsdata_id     = Wahapedia datasheet id (9-digit, e.g. "000002570")
  catalogue_weapons.bsdata_id   = synthetic "<datasheet_id>:<line>:<line_in_wargear>"

The column names bsdata_id / unit_bsdata_id are kept as a deliberate legacy
misnomer so the rest of the app's query sites do not need touching. They now
hold Wahapedia ids.

The JSON column shapes emitted here match the contract that data_store.py and
the datasheet frontend consume (see scripts/capture_baseline.py output):

  stats_json      single model -> dict, multi-profile -> list, none -> null
  abilities_json  {core, faction, datasheet, special, invuln_save, transport, damaged}
  keywords_json   list of strings, faction keywords prefixed "Faction: "
  composition_json      list of {name}
  wargear_options_json  list of {description}
  points_tiers_json     list of {cost, description} when multi-tier, else null

Refresh procedure: run scripts/fetch_wahapedia.py then this importer.

Usage:
    python wahapedia_importer.py
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
DB_PATH = os.path.join(BASE, "collection.db")

# Wahapedia battlefield-role names mapped onto the singular forms data_store's
# ROLE_ORDER sorts by.
ROLE_MAP = {
    "Characters":           "Character",
    "Character":            "Character",
    "Battleline":           "Battleline",
    "Dedicated Transports": "Transport",
    "Transport":            "Transport",
    "Fortifications":       "Fortification",
    "Fortification":        "Fortification",
    "Other":                "Other",
    "":                     "Other",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def read_csv(name):
    """Read a pipe-delimited Wahapedia CSV into a list of dict rows."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing required CSV: {path}")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def group_by(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[(r.get(key) or "").strip()].append(r)
    return out


_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text):
    """Remove HTML tags and collapse whitespace, preserving ASCII hyphens so
    squad-size ranges like '4-9' stay parseable downstream."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean(v):
    return (v or "").strip()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_abilities_index(abilities_rows):
    """Map ability_id -> list of (faction_id, name, description) so rows in
    Datasheets_abilities.csv that carry only an ability_id can be resolved.
    Abilities.csv ids are not unique (shared across factions)."""
    idx = defaultdict(list)
    for r in abilities_rows:
        idx[_clean(r.get("id"))].append(
            (_clean(r.get("faction_id")), _clean(r.get("name")), r.get("description") or "")
        )
    return idx


def resolve_ability(ability_idx, ability_id, faction_id):
    entries = ability_idx.get(ability_id)
    if not entries:
        return "", ""
    for fac, name, desc in entries:
        if fac == faction_id:
            return name, desc
    fac, name, desc = entries[0]
    return name, desc


def build_models(models_rows):
    """datasheet_id -> stats_json value (dict for single profile, list for
    multi-profile, None when there are no model rows)."""
    by_ds = group_by(models_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: int(_clean(r.get("line")) or 0))
        profiles = []
        for r in rows:
            profiles.append({
                "name":      _clean(r.get("name")),
                "M":         _clean(r.get("M")),
                "T":         _clean(r.get("T")),
                "SV":        _clean(r.get("Sv")),
                "W":         _clean(r.get("W")),
                "LD":        _clean(r.get("Ld")),
                "OC":        _clean(r.get("OC")),
                "base_size": _clean(r.get("base_size")),
            })
        if not profiles:
            out[did] = None
        elif len(profiles) == 1:
            out[did] = profiles[0]
        else:
            out[did] = profiles
    return out


def build_invuln(models_rows):
    """datasheet_id -> bare invuln value (e.g. '4') from the first model that
    carries a real invulnerable save. '-' and blank mean none."""
    by_ds = group_by(models_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        for r in sorted(rows, key=lambda r: int(_clean(r.get("line")) or 0)):
            inv = _clean(r.get("inv_sv"))
            if inv and inv != "-":
                out[did] = inv
                break
    return out


def build_abilities(ds_row, ds_abilities, ability_idx, invuln):
    """Assemble the abilities_json dict for one datasheet."""
    faction_id = _clean(ds_row.get("faction_id"))
    buckets = {"core": [], "faction": [], "datasheet": []}
    seen = {"core": set(), "faction": set(), "datasheet": set()}

    for r in sorted(ds_abilities, key=lambda r: int(_clean(r.get("line")) or 0)):
        atype = _clean(r.get("type"))
        name = _clean(r.get("name"))
        desc = r.get("description") or ""
        ability_id = _clean(r.get("ability_id"))
        if ability_id and (not name or not desc):
            rname, rdesc = resolve_ability(ability_idx, ability_id, faction_id)
            name = name or rname
            desc = desc or rdesc
        if not name and not desc:
            continue
        if atype == "Core":
            bucket = "core"
        elif atype == "Faction":
            bucket = "faction"
        else:
            # Datasheet, Wargear, Wargear profile, Primarch and any column-suffix
            # variants all surface in the datasheet abilities block.
            bucket = "datasheet"
        key = name.lower()
        if key in seen[bucket]:
            continue
        seen[bucket].add(key)
        buckets[bucket].append({"name": name, "description": desc})

    did = _clean(ds_row.get("id"))
    damaged_w = _clean(ds_row.get("damaged_w"))
    damaged_desc = ds_row.get("damaged_description") or ""
    damaged = None
    if damaged_w or damaged_desc.strip():
        damaged = {
            "name": f"Damaged: {damaged_w} Wounds Remaining" if damaged_w else "Damaged",
            "threshold": damaged_w,
            "description": damaged_desc,
        }

    return {
        "core":        buckets["core"],
        "faction":     buckets["faction"],
        "datasheet":   buckets["datasheet"],
        "special":     [],
        "invuln_save": invuln.get(did),
        "transport":   _clean(ds_row.get("transport")) or None,
        "damaged":     damaged,
    }


def build_keywords(keyword_rows):
    """datasheet_id -> ordered, de-duplicated keyword list; faction keywords
    prefixed 'Faction: '."""
    by_ds = group_by(keyword_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        seen = set()
        kws = []
        for r in rows:
            kw = _clean(r.get("keyword"))
            if not kw:
                continue
            is_fac = _clean(r.get("is_faction_keyword")).lower() == "true"
            label = f"Faction: {kw}" if is_fac else kw
            if label in seen:
                continue
            seen.add(label)
            kws.append(label)
        out[did] = kws
    return out


def build_composition(comp_rows):
    by_ds = group_by(comp_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: int(_clean(r.get("line")) or 0))
        lines = []
        for r in rows:
            text = strip_tags(r.get("description") or "")
            if text:
                lines.append({"name": text})
        if lines:
            out[did] = lines
    return out


def build_options(option_rows):
    by_ds = group_by(option_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: int(_clean(r.get("line")) or 0))
        opts = []
        for r in rows:
            desc = (r.get("description") or "").strip()
            if desc:
                opts.append({"description": desc})
        if opts:
            out[did] = opts
    return out


def build_costs(cost_rows):
    """datasheet_id -> (points, points_tiers_json). Single tier -> (int, None);
    multi-tier -> (cheapest, [{cost, description}]); none -> (None, None)."""
    by_ds = group_by(cost_rows, "datasheet_id")
    out = {}
    for did, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: int(_clean(r.get("line")) or 0))
        tiers = []
        for r in rows:
            raw = _clean(r.get("cost"))
            try:
                cost = int(raw)
            except (TypeError, ValueError):
                continue
            tiers.append({"cost": cost, "description": _clean(r.get("description"))})
        if not tiers:
            out[did] = (None, None)
        elif len(tiers) == 1:
            out[did] = (tiers[0]["cost"], None)
        else:
            cheapest = min(t["cost"] for t in tiers)
            out[did] = (cheapest, tiers)
    return out


def build_leaders(leader_rows, valid_ids):
    """leader datasheet_id -> list of attached datasheet ids it can lead."""
    out = defaultdict(list)
    for r in leader_rows:
        lid = _clean(r.get("leader_id"))
        aid = _clean(r.get("attached_id"))
        if lid and aid and aid in valid_ids and aid not in out[lid]:
            out[lid].append(aid)
    return out


def build_weapons(wargear_rows):
    """Return (weapons, unit_weapons).

    weapons: list of dicts ready for catalogue_weapons.
    unit_weapons: list of (unit_id, weapon_id) pairs.
    """
    weapons = []
    unit_weapons = []
    for r in wargear_rows:
        did = _clean(r.get("datasheet_id"))
        if not did:
            continue
        line = _clean(r.get("line"))
        line_in = _clean(r.get("line_in_wargear"))
        wid = f"{did}:{line}:{line_in}"
        wtype = _clean(r.get("type"))
        rng = _clean(r.get("range"))
        is_melee = wtype.lower() == "melee" or rng.lower() == "melee"
        # The Wahapedia "description" column holds the weapon's bracketed
        # keywords (e.g. "ignores cover, torrent"), not prose.
        weapons.append({
            "bsdata_id":   wid,
            "name":        _clean(r.get("name")),
            "weapon_type": "melee" if is_melee else "ranged",
            "range":       rng,
            "attacks":     _clean(r.get("A")),
            "skill":       _clean(r.get("BS_WS")),
            "strength":    _clean(r.get("S")),
            "ap":          _clean(r.get("AP")),
            "damage":      _clean(r.get("D")),
            "keywords":    (r.get("description") or "").strip(),
            "description": "",
            "datasheet_id": did,
        })
        unit_weapons.append((did, wid))
    return weapons, unit_weapons


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_schema(conn):
    """Create the catalogue tables if missing and add the Wahapedia-era columns
    (legend, link, virtual on units; description on weapons)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS catalogue_factions (
        bsdata_id   TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        cat_file    TEXT NOT NULL,
        imported_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS catalogue_units (
        bsdata_id       TEXT PRIMARY KEY,
        faction_id      TEXT NOT NULL,
        name            TEXT NOT NULL,
        role            TEXT,
        points          INTEGER,
        stats_json      TEXT,
        abilities_json  TEXT,
        keywords_json   TEXT,
        imported_at     TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS catalogue_weapons (
        bsdata_id    TEXT PRIMARY KEY,
        faction_id   TEXT NOT NULL,
        name         TEXT NOT NULL,
        weapon_type  TEXT NOT NULL,
        range        TEXT,
        attacks      TEXT,
        skill        TEXT,
        strength     TEXT,
        ap           TEXT,
        damage       TEXT,
        keywords     TEXT,
        imported_at  TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS catalogue_unit_weapons (
        unit_id    TEXT NOT NULL,
        weapon_id  TEXT NOT NULL,
        PRIMARY KEY (unit_id, weapon_id)
    )""")

    for stmt in (
        "ALTER TABLE catalogue_units ADD COLUMN composition_json TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN wargear_options_json TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN loadout TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN leader_targets_json TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN points_tiers_json TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN legend TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN link TEXT",
        "ALTER TABLE catalogue_units ADD COLUMN virtual INTEGER DEFAULT 0",
        "ALTER TABLE catalogue_weapons ADD COLUMN description TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists


def clear_tables(conn):
    # Child-first so the (now FK-free) catalogue tables clear cleanly either way.
    for t in ("catalogue_unit_weapons", "catalogue_weapons",
              "catalogue_units", "catalogue_factions"):
        conn.execute(f"DELETE FROM {t}")


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def run():
    print("Reading CSVs from", DATA_DIR)
    factions = read_csv("Factions.csv")
    datasheets = read_csv("Datasheets.csv")
    models_rows = read_csv("Datasheets_models.csv")
    wargear_rows = read_csv("Datasheets_wargear.csv")
    option_rows = read_csv("Datasheets_options.csv")
    comp_rows = read_csv("Datasheets_unit_composition.csv")
    cost_rows = read_csv("Datasheets_models_cost.csv")
    keyword_rows = read_csv("Datasheets_keywords.csv")
    ds_ability_rows = read_csv("Datasheets_abilities.csv")
    leader_rows = read_csv("Datasheets_leader.csv")
    abilities_rows = read_csv("Abilities.csv")

    valid_faction_codes = {_clean(f.get("id")) for f in factions}
    valid_ds_ids = {_clean(d.get("id")) for d in datasheets if _clean(d.get("id"))}

    # Pre-build per-datasheet indexes.
    models_by_ds = build_models(models_rows)
    invuln_by_ds = build_invuln(models_rows)
    keywords_by_ds = build_keywords(keyword_rows)
    comp_by_ds = build_composition(comp_rows)
    options_by_ds = build_options(option_rows)
    costs_by_ds = build_costs(cost_rows)
    leaders_by_ds = build_leaders(leader_rows, valid_ds_ids)
    ds_abilities_by_ds = group_by(ds_ability_rows, "datasheet_id")
    ability_idx = build_abilities_index(abilities_rows)

    weapons, unit_weapons = build_weapons(wargear_rows)
    # faction_id for each weapon = parent datasheet faction code.
    ds_faction = {_clean(d.get("id")): _clean(d.get("faction_id")) for d in datasheets}
    for w in weapons:
        w["faction_id"] = ds_faction.get(w["datasheet_id"], "")

    now = _now()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        ensure_schema(conn)
        clear_tables(conn)

        # Factions
        for f in factions:
            code = _clean(f.get("id"))
            name = _clean(f.get("name"))
            if not code or not name:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO catalogue_factions"
                " (bsdata_id, name, cat_file, imported_at) VALUES (?,?,?,?)",
                (code, name, "Wahapedia", now),
            )

        # Units
        unit_count = 0
        for d in datasheets:
            did = _clean(d.get("id"))
            if not did:
                continue
            faction_id = _clean(d.get("faction_id"))
            role = ROLE_MAP.get(_clean(d.get("role")), _clean(d.get("role")) or "Other")
            points, tiers = costs_by_ds.get(did, (None, None))
            abilities = build_abilities(
                d, ds_abilities_by_ds.get(did, []), ability_idx, invuln_by_ds)
            stats = models_by_ds.get(did)
            kws = keywords_by_ds.get(did, [])
            composition = comp_by_ds.get(did)
            options = options_by_ds.get(did)
            leader_targets = leaders_by_ds.get(did)
            virtual = 1 if _clean(d.get("virtual")).lower() == "true" else 0

            conn.execute(
                """INSERT OR REPLACE INTO catalogue_units
                   (bsdata_id, faction_id, name, role, points,
                    stats_json, abilities_json, keywords_json, imported_at,
                    composition_json, wargear_options_json, loadout,
                    leader_targets_json, points_tiers_json, legend, link, virtual)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    did, faction_id, _clean(d.get("name")), role, points,
                    json.dumps(stats) if stats is not None else None,
                    json.dumps(abilities),
                    json.dumps(kws) if kws else None,
                    now,
                    json.dumps(composition) if composition else None,
                    json.dumps(options) if options else None,
                    d.get("loadout") or None,
                    json.dumps(leader_targets) if leader_targets else None,
                    json.dumps(tiers) if tiers else None,
                    _clean(d.get("legend")) or None,
                    _clean(d.get("link")) or None,
                    virtual,
                ),
            )
            unit_count += 1

        # Weapons
        for w in weapons:
            conn.execute(
                """INSERT OR REPLACE INTO catalogue_weapons
                   (bsdata_id, faction_id, name, weapon_type, range, attacks,
                    skill, strength, ap, damage, keywords, imported_at, description)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    w["bsdata_id"], w["faction_id"], w["name"], w["weapon_type"],
                    w["range"], w["attacks"], w["skill"], w["strength"], w["ap"],
                    w["damage"], w["keywords"], now, w["description"],
                ),
            )

        # Unit-weapon links (weapon ids are unique per datasheet line already).
        seen_links = set()
        for unit_id, weapon_id in unit_weapons:
            if (unit_id, weapon_id) in seen_links:
                continue
            seen_links.add((unit_id, weapon_id))
            conn.execute(
                "INSERT OR IGNORE INTO catalogue_unit_weapons (unit_id, weapon_id)"
                " VALUES (?,?)",
                (unit_id, weapon_id),
            )

        conn.commit()
    finally:
        conn.close()

    # Summary
    conn = sqlite3.connect(DB_PATH)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("catalogue_factions", "catalogue_units",
                        "catalogue_weapons", "catalogue_unit_weapons")}
    conn.close()
    print("Import complete:")
    for k, v in counts.items():
        print(f"  {k:26s} {v}")
    return counts


if __name__ == "__main__":
    try:
        run()
    except FileNotFoundError as exc:
        print("ERROR:", exc)
        print("Run scripts/fetch_wahapedia.py first.")
        sys.exit(1)
