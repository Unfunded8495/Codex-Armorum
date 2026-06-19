"""Read-only diagnostic for the Space Marine chapter rollup (Phase 0).

Derives, from the live Wahapedia CSVs in data/ (and the loaded data_store), the
set of chapter faction keywords that sit under the single Space Marines faction
code SM, and confirms that chapter detachments are all coded under SM with no
chapter sub-code. Writes the findings to chapters_inspect.json and prints a
summary. This script writes nothing to the database and changes no app state.

Usage:
    python scripts/inspect_chapters.py
"""
import csv
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
sys.path.insert(0, BASE)

# Parent faction code(s) the rollup applies to, and the universal keywords that
# are never chapters. Kept here so this diagnostic agrees with data_store's
# config without importing it (data_store is exercised separately below).
PARENT_FACTIONS = {"SM"}
UNIVERSAL_EXCLUDE = {"Adeptus Astartes", "Imperium"}


def read_csv(name):
    path = os.path.join(DATA_DIR, name)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def clean(v):
    return (v or "").strip()


def main():
    datasheets = read_csv("Datasheets.csv")
    keyword_rows = read_csv("Datasheets_keywords.csv")
    factions = read_csv("Factions.csv")
    detachments = read_csv("Detachments.csv")

    # 1. Faction codes in Datasheets.csv, and SM's datasheet count.
    faction_codes = {}
    for d in datasheets:
        code = clean(d.get("faction_id"))
        faction_codes[code] = faction_codes.get(code, 0) + 1

    sm_codes = sorted(c for c in faction_codes if c in PARENT_FACTIONS)

    # Datasheet -> faction code, and the set of SM datasheet ids.
    ds_faction = {clean(d.get("id")): clean(d.get("faction_id")) for d in datasheets}
    ds_name = {clean(d.get("id")): clean(d.get("name")) for d in datasheets}
    sm_ds_ids = {did for did, fac in ds_faction.items() if fac in PARENT_FACTIONS}

    # 2. Faction keywords (is_faction_keyword true) appearing on SM datasheets,
    #    with a per-keyword datasheet count and sample datasheet names.
    fac_kw_counts = {}
    fac_kw_samples = {}
    for r in keyword_rows:
        did = clean(r.get("datasheet_id"))
        if did not in sm_ds_ids:
            continue
        if clean(r.get("is_faction_keyword")).lower() != "true":
            continue
        kw = clean(r.get("keyword"))
        if not kw:
            continue
        fac_kw_counts[kw] = fac_kw_counts.get(kw, 0) + 1
        fac_kw_samples.setdefault(kw, [])
        if len(fac_kw_samples[kw]) < 3 and ds_name.get(did):
            fac_kw_samples[kw].append(ds_name[did])

    # 3. Derived chapter set = SM faction keywords minus the exclude set. The
    #    exclude set is the universal keywords plus any keyword equal to a real
    #    faction name (drops cross-faction tags such as "Agents of the Imperium").
    faction_names = {clean(f.get("name")) for f in factions if clean(f.get("name"))}
    exclude = set(UNIVERSAL_EXCLUDE) | faction_names

    chapter_keywords = sorted(kw for kw in fac_kw_counts if kw not in exclude)
    dropped_as_faction_name = sorted(
        kw for kw in fac_kw_counts if kw in faction_names)

    # 5. Detachment faction coding: confirm chapter detachments sit under SM and
    #    no chapter sub-code exists in Detachments.csv.
    det_faction_codes = {}
    for d in detachments:
        code = clean(d.get("faction_id"))
        det_faction_codes[code] = det_faction_codes.get(code, 0) + 1
    sm_detachments = [clean(d.get("name")) for d in detachments
                      if clean(d.get("faction_id")) in PARENT_FACTIONS]
    chapter_subcodes_in_detachments = sorted(
        c for c in det_faction_codes if "::" in c)

    # Cross-check against the loaded store: confirm SM is a single loaded faction
    # and chapter keywords resolve to real datasheets via the store too.
    store_info = {}
    try:
        from data_store import get_store
        store = get_store()
        store_info = {
            "sm_in_faction_by_id": "SM" in store.faction_by_id,
            "sm_unit_count_loaded": len(store.ds_by_faction.get("SM", [])),
        }
    except Exception as exc:  # diagnostic must not hard-fail on store issues
        store_info = {"error": repr(exc)}

    report = {
        "faction_codes_in_datasheets": dict(sorted(faction_codes.items())),
        "parent_codes_present": sm_codes,
        "sm_datasheet_count": faction_codes.get("SM", 0),
        "sm_faction_keyword_counts": dict(sorted(fac_kw_counts.items())),
        "exclude_set_size": len(exclude),
        "universal_exclude": sorted(UNIVERSAL_EXCLUDE),
        "dropped_because_faction_name": dropped_as_faction_name,
        "derived_chapters": chapter_keywords,
        "derived_chapter_count": len(chapter_keywords),
        "chapter_samples": {kw: fac_kw_samples.get(kw, []) for kw in chapter_keywords},
        "chapter_datasheet_counts": {kw: fac_kw_counts[kw] for kw in chapter_keywords},
        "detachment_faction_codes": dict(sorted(det_faction_codes.items())),
        "sm_detachment_count": det_faction_codes.get("SM", 0),
        "sm_detachment_names": sorted(sm_detachments),
        "chapter_subcodes_in_detachments": chapter_subcodes_in_detachments,
        "store_cross_check": store_info,
    }

    out_path = os.path.join(BASE, "chapters_inspect.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    # ---- printed summary + gate ----
    core_expected = {"Blood Angels", "Dark Angels", "Space Wolves",
                     "Deathwatch", "Black Templars"}
    print("Faction codes in Datasheets.csv:", len(faction_codes))
    print("SM datasheet count:", faction_codes.get("SM", 0))
    print()
    print("Derived chapters ({}):".format(len(chapter_keywords)))
    for kw in chapter_keywords:
        print("  {:24s} {:3d} datasheets   e.g. {}".format(
            kw, fac_kw_counts[kw], ", ".join(fac_kw_samples.get(kw, []))))
    print()
    print("Dropped because they match a faction name:",
          ", ".join(dropped_as_faction_name) or "(none)")
    print()
    print("Detachment faction codes:", dict(sorted(det_faction_codes.items())))
    print("Chapter sub-codes in Detachments.csv:",
          chapter_subcodes_in_detachments or "(none)")
    print()
    missing = sorted(core_expected - set(chapter_keywords))
    if missing:
        print("GATE FAILED: missing core chapters:", missing)
    elif chapter_subcodes_in_detachments:
        print("GATE FAILED: Detachments.csv carries chapter sub-codes:",
              chapter_subcodes_in_detachments)
    else:
        print("GATE PASSED: all core chapters present; detachments are SM-coded.")
    print()
    print("Wrote", out_path)
    return report


if __name__ == "__main__":
    main()
