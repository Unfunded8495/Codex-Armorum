"""
Migrate model_catalogue_manual.json faction_id fields from Wahapedia short
codes (SM, TYR, etc.) to BSData GUIDs, so they match the keys in
store.faction_by_id and enable proper faction name/theme resolution.

Only faction_id is updated. faction_label (the display name on each card)
is left untouched.

Safe to re-run: already-migrated GUIDs pass through unchanged.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_PATH = os.path.join(BASE, "data", "model_catalogue_manual.json")

# Wahapedia short code -> BSData GUID (from catalogue_factions table)
MAPPING = {
    "SM":  "e0af-67df-9d63-8fb7",  # Imperium - Adeptus Astartes - Space Marines
    "AC":  "1f19-6509-d906-ca10",  # Imperium - Adeptus Custodes
    "AE":  "34a5-8c7e-f468-82d1",  # Xenos - Aeldari
    "AM":  "b0ae-12a5-c84-ea45",   # Imperium - Astra Militarum
    "AS":  "b39e-4401-8f3e-fdf7",  # Imperium - Adepta Sororitas
    "AdM": "77b9-2f66-3f9b-5cf3",  # Imperium - Adeptus Mechanicus
    "AoI": "b00-cd86-4b4c-97ba",   # Imperium - Agents of the Imperium
    "CD":  "d265-877b-e03d-30ca",  # Chaos - Chaos Daemons
    "CSM": "c8da-e875-58f7-f6d6",  # Chaos - Chaos Space Marines
    "DG":  "5108-f98-63c2-53cb",   # Chaos - Death Guard
    "DRU": "38de-521f-1ce0-44a0",  # Xenos - Drukhari
    "EC":  "03fe-a162-4c02-f07b",  # Chaos - Emperor's Children
    "GC":  "3bdf-a114-5035-c6ac",  # Xenos - Genestealer Cults
    "GK":  "50c4-3e83-fe54-97c4",  # Imperium - Grey Knights
    "LOV": "f616-3f08-ee8e-3349",  # Xenos - Leagues of Votann (capitalised typo)
    "LoV": "f616-3f08-ee8e-3349",  # Xenos - Leagues of Votann
    "NEC": "b654-a18a-ea1-3bf2",   # Xenos - Necrons
    "ORK": "a55f-b7b3-6c65-a05f",  # Xenos - Orks
    "QI":  "25dd-7aa0-6bf4-f2d5",  # Imperium - Imperial Knights
    "QT":  "46d8-abc8-ef3a-9f85",  # Chaos - Chaos Knights
    "TAU": "d81a-61dd-6d27-a3ce",  # Xenos - T'au Empire
    "TS":  "1069-10ff-3ba9-873b",  # Chaos - Thousand Sons
    "TYR": "b984-7317-81cc-20f",   # Xenos - Tyranids
    "WE":  "df9a-59b2-f464-59ad",  # Chaos - World Eaters
    "UN":  "581a-46b9-5b86-44b7",  # Unaligned Forces
}

# All known BSData GUIDs (so we can detect already-migrated records)
KNOWN_GUIDS = set(MAPPING.values())


def run(dry_run=False):
    with open(MANUAL_PATH, encoding="utf-8") as f:
        doc = json.load(f)

    releases = doc.get("model_releases", [])
    migrated = 0
    already_ok = 0
    unmapped = []

    for record in releases:
        cid = record.get("id", "?")
        fid = record.get("faction_id", "")

        if not fid:
            already_ok += 1
            continue

        if fid in KNOWN_GUIDS:
            already_ok += 1
            continue

        guid = MAPPING.get(fid)
        if guid:
            if not dry_run:
                record["faction_id"] = guid
            migrated += 1
        else:
            unmapped.append((cid, record.get("name", "?"), fid))

    print(f"Total records  : {len(releases)}")
    print(f"Migrated       : {migrated}")
    print(f"Already correct: {already_ok}")
    print(f"Unmapped codes : {len(unmapped)}")
    if unmapped:
        print("\nUnmapped (left unchanged):")
        for cid, name, fid in unmapped:
            print(f"  {cid}  {name!r}  faction_id={fid!r}")

    if not dry_run and migrated:
        with open(MANUAL_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"\nWritten to {MANUAL_PATH}")
    elif dry_run:
        print("\n(dry run — no file written)")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    run(dry_run=dry)
