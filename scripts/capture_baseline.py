"""Phase 0 baseline capture for the Wahapedia migration.

Writes baseline.json capturing the current BSData-derived contract so that the
post-migration state can be diff-checked structurally (same keys and types, not
necessarily same counts). Run again after migration into post_migration.json
(pass an output path argument) for Phase 7.

Usage:
    python scripts/capture_baseline.py [output_path]
"""
import json
import os
import sqlite3
import sys

# Allow running from the scripts/ directory or the repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import data_store  # noqa: E402

DB_PATH = os.path.join(ROOT, "collection.db")

# Sample units captured by name. The Forge World / Legends candidate list is
# tried in order; the first that resolves is recorded.
SAMPLE_NAMES = [
    "Legionaries",
    "Chaos Lord",
    "Land Raider",
    "Termagants",
]
FORGE_WORLD_CANDIDATES = [
    "Cerastus Knight Lancer",
    "Astraeus",
    "Deredeo Dreadnought",
    "Leviathan Dreadnought",
    "Kytan Ravager",
    "Brass Scorpion of Khorne",
]

RAW_COLUMNS = [
    "stats_json", "abilities_json", "keywords_json", "composition_json",
    "wargear_options_json", "points_tiers_json", "loadout",
]


def _norm(s):
    return (s or "").replace("’", "'").replace("‘", "'").strip().lower()


def describe_shape(value, depth=0):
    """Return a compact description of a JSON value's structure (keys + types)."""
    if isinstance(value, dict):
        return {k: describe_shape(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return ["empty-list"]
        # Describe the first element as representative of the list shape.
        return ["list-of", describe_shape(value[0], depth + 1)]
    return type(value).__name__


def resolve_id_by_name(store, name):
    target = _norm(name)
    for u in store.datasheets:
        if _norm(u["name"]) == target:
            return u["id"]
    # Substring fallback (e.g. "Land Raider" matching exact base name only).
    for u in store.datasheets:
        if _norm(u["name"]) == target:
            return u["id"]
    return None


def raw_columns_for(conn, did):
    row = conn.execute(
        "SELECT " + ", ".join(RAW_COLUMNS) +
        " FROM catalogue_units WHERE bsdata_id=?", (did,)
    ).fetchone()
    if not row:
        return None
    out = {}
    for col in RAW_COLUMNS:
        val = row[col]
        if val is None:
            out[col] = {"raw": None, "shape": None}
            continue
        if col == "loadout":
            out[col] = {"raw_len": len(val), "shape": "str"}
            continue
        try:
            parsed = json.loads(val)
            out[col] = {"shape": describe_shape(parsed), "value": parsed}
        except (TypeError, ValueError):
            out[col] = {"raw": val, "shape": "unparseable"}
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "baseline.json")

    store = data_store.DataStore()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    result = {}

    # 1. Counts
    counts = {}
    for t in ("catalogue_factions", "catalogue_units", "catalogue_weapons",
              "catalogue_unit_weapons"):
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    counts["minis_total"] = conn.execute("SELECT COUNT(*) FROM minis").fetchone()[0]
    fl = store.faction_list()
    counts["faction_list_len"] = len(fl)
    result["counts"] = counts
    result["faction_list"] = [
        {"id": f["id"], "name": f["name"], "unit_count": f["unit_count"]} for f in fl
    ]

    # 2. Sample units
    samples = {}
    names = list(SAMPLE_NAMES)
    for cand in FORGE_WORLD_CANDIDATES:
        if resolve_id_by_name(store, cand):
            names.append(cand)
            break

    for name in names:
        did = resolve_id_by_name(store, name)
        if not did:
            samples[name] = {"resolved": False}
            continue
        detail = store.unit_detail(did)
        samples[name] = {
            "resolved": True,
            "id": did,
            "unit_detail_shape": describe_shape(detail),
            "unit_detail": detail,
            "raw_columns": raw_columns_for(conn, did),
        }
    result["samples"] = samples

    # 3. Detachment counts per faction
    det_counts = {}
    for fid, dets in store.detachments_by_faction.items():
        fname = store.faction_by_id.get(fid, {}).get("name", fid)
        det_counts[fid] = {"name": fname, "count": len(dets)}
    result["detachment_counts"] = det_counts
    result["detachment_total"] = sum(d["count"] for d in det_counts.values())

    # 4. Full minis unit_bsdata_id -> datasheet_id pairing
    pairing = []
    for r in conn.execute(
        "SELECT id, datasheet_id, unit_bsdata_id FROM minis ORDER BY id"
    ).fetchall():
        pairing.append({
            "id": r["id"],
            "datasheet_id": r["datasheet_id"],
            "unit_bsdata_id": r["unit_bsdata_id"],
        })
    result["minis_pairing"] = pairing

    # Faction id reference (name -> id) so Phase 4 can build a GUID->code map.
    result["faction_name_to_id"] = {f["name"]: f["id"] for f in fl}

    conn.close()

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    # Human-readable summary
    print("=" * 60)
    print("BASELINE CAPTURE SUMMARY")
    print("=" * 60)
    print("Output:", out_path)
    print("Counts:")
    for k, v in counts.items():
        print(f"  {k:28s} {v}")
    print(f"Detachment total: {result['detachment_total']} "
          f"across {len(det_counts)} factions")
    print("Sample units:")
    for name, s in samples.items():
        if not s.get("resolved"):
            print(f"  {name:28s} NOT RESOLVED")
            continue
        rc = s["raw_columns"] or {}
        stats_ok = rc.get("stats_json", {}).get("shape") not in (None, "unparseable")
        ab = rc.get("abilities_json", {}).get("shape")
        ab_ok = ab not in (None, "unparseable")
        print(f"  {name:28s} id={s['id']} stats={'Y' if stats_ok else 'N'} "
              f"abilities={'Y' if ab_ok else 'N'}")
    print(f"Minis pairing rows: {len(pairing)}")


if __name__ == "__main__":
    main()
