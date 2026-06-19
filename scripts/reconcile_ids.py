"""Phase 4 of the Wahapedia migration: one-time id reconciliation.

Runs inside a single transaction against collection.db with before/after counts:

  1. Remap the small set of minis whose datasheet_id is a legacy BSData GUID
     (rather than a Wahapedia id) onto the matching Wahapedia datasheet, by name
     and old faction. Photos, WIP notes and box contents that reference the same
     GUID are moved with it.
  2. Backfill minis.unit_bsdata_id = datasheet_id so every collection query
     resolves against the Wahapedia id space.
  3. Remap faction references in favourite_factions and custom_box_sets that
     still hold BSData faction GUIDs onto Wahapedia faction codes (by name,
     using the pre-wahapedia backup).
  4. Assert army_units is empty.

Requires collection.db.pre-wahapedia (the pre-migration backup) to look up the
old faction and unit names. Run AFTER wahapedia_importer.py.

Usage:
    python scripts/reconcile_ids.py
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import data_store  # noqa: E402

DB_PATH = os.path.join(ROOT, "collection.db")
BACKUP_PATH = os.path.join(ROOT, "collection.db.pre-wahapedia")


def norm(s):
    return (s or "").replace("’", "'").replace("‘", "'").strip().lower()


def is_guid(s):
    """A legacy BSData id looks like 'c8da-e875-58f7-f6d6'; a Wahapedia id is a
    9-digit string. Treat anything containing a hyphen as a GUID."""
    return bool(s) and "-" in s


def main():
    if not os.path.exists(BACKUP_PATH):
        print("ERROR: missing", BACKUP_PATH, "(needed for old name/faction lookup)")
        sys.exit(1)

    store = data_store.DataStore()

    # New-store lookups
    waha_name_to_code = {norm(f["name"]): f["id"] for f in store.factions}
    ds_by_name = {}
    for u in store.datasheets:
        ds_by_name.setdefault(norm(u["name"]), []).append((u["id"], u["faction_id"]))

    def old_faction_name_to_code(old):
        if not old:
            return None
        leaf = old.split(" - ")[-1].strip()
        code = waha_name_to_code.get(norm(leaf))
        if code:
            return code
        if "Adeptus Astartes" in old:  # all chapters live under SM in Wahapedia
            return "SM"
        return None

    bak = sqlite3.connect(BACKUP_PATH)
    bak.row_factory = sqlite3.Row

    def old_unit(guid):
        return bak.execute(
            "SELECT u.name uname, f.name fname FROM catalogue_units u"
            " JOIN catalogue_factions f ON f.bsdata_id = u.faction_id"
            " WHERE u.bsdata_id = ?", (guid,)).fetchone()

    def old_faction(guid):
        return bak.execute(
            "SELECT name FROM catalogue_factions WHERE bsdata_id = ?",
            (guid,)).fetchone()

    def resolve_datasheet_guid(guid):
        """Return the matching Wahapedia datasheet id, or None."""
        row = old_unit(guid)
        if not row:
            return None
        candidates = ds_by_name.get(norm(row["uname"]), [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0][0]
        target_code = old_faction_name_to_code(row["fname"])
        for did, fcode in candidates:
            if fcode == target_code:
                return did
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")

    report = {"datasheet_remaps": [], "datasheet_unresolved": [],
              "faction_remaps": [], "faction_unresolved": []}

    try:
        # --- 1. Mini datasheet GUID remap ---------------------------------
        guid_dids = [r["datasheet_id"] for r in conn.execute(
            "SELECT DISTINCT datasheet_id FROM minis"
            " WHERE datasheet_id IS NOT NULL AND datasheet_id <> ''"
        ).fetchall() if is_guid(r["datasheet_id"])]

        for guid in guid_dids:
            new_id = resolve_datasheet_guid(guid)
            name = (old_unit(guid) or {})["uname"] if old_unit(guid) else guid
            n_minis = conn.execute(
                "SELECT COUNT(*) FROM minis WHERE datasheet_id=?", (guid,)).fetchone()[0]
            if not new_id:
                report["datasheet_unresolved"].append((guid, name, n_minis))
                continue
            conn.execute(
                "UPDATE minis SET datasheet_id=?, unit_bsdata_id=? WHERE datasheet_id=?",
                (new_id, new_id, guid))
            conn.execute(
                "UPDATE photos SET datasheet_id=? WHERE datasheet_id=?", (new_id, guid))
            conn.execute(
                "UPDATE unit_wip_photos SET datasheet_id=? WHERE datasheet_id=?",
                (new_id, guid))
            # unit_wip.datasheet_id is a PRIMARY KEY: only move if the target is free.
            tgt = conn.execute(
                "SELECT 1 FROM unit_wip WHERE datasheet_id=?", (new_id,)).fetchone()
            if tgt:
                conn.execute("DELETE FROM unit_wip WHERE datasheet_id=?", (guid,))
            else:
                conn.execute(
                    "UPDATE unit_wip SET datasheet_id=? WHERE datasheet_id=?",
                    (new_id, guid))
            conn.execute(
                "UPDATE custom_box_set_contents SET datasheet_id=? WHERE datasheet_id=?",
                (new_id, guid))
            report["datasheet_remaps"].append((guid, name, new_id, n_minis))

        # --- 2. Backfill unit_bsdata_id = datasheet_id --------------------
        before_null = conn.execute(
            "SELECT COUNT(*) FROM minis WHERE unit_bsdata_id IS NULL OR unit_bsdata_id=''"
        ).fetchone()[0]
        conn.execute(
            "UPDATE minis SET unit_bsdata_id = datasheet_id"
            " WHERE datasheet_id IS NOT NULL AND datasheet_id <> ''")
        after_null = conn.execute(
            "SELECT COUNT(*) FROM minis WHERE unit_bsdata_id IS NULL OR unit_bsdata_id=''"
        ).fetchone()[0]

        # --- 3. Faction id remap ------------------------------------------
        # favourite_factions: faction_id is a PRIMARY KEY, so delete GUID rows and
        # re-insert the resolved code (ignored if it already exists).
        fav_guid_rows = [dict(r) for r in conn.execute(
            "SELECT faction_id, created_at FROM favourite_factions").fetchall()
            if is_guid(r["faction_id"])]
        for r in fav_guid_rows:
            guid = r["faction_id"]
            orow = old_faction(guid)
            code = old_faction_name_to_code(orow["name"]) if orow else None
            conn.execute("DELETE FROM favourite_factions WHERE faction_id=?", (guid,))
            if code:
                conn.execute(
                    "INSERT OR IGNORE INTO favourite_factions(faction_id, created_at)"
                    " VALUES(?,?)", (code, r["created_at"]))
                report["faction_remaps"].append(("favourite_factions", guid,
                                                 orow["name"], code))
            else:
                report["faction_unresolved"].append(
                    ("favourite_factions", guid, orow["name"] if orow else "?"))

        # custom_box_sets: faction_id is not unique, plain update.
        box_guids = [r["faction_id"] for r in conn.execute(
            "SELECT DISTINCT faction_id FROM custom_box_sets").fetchall()
            if is_guid(r["faction_id"])]
        for guid in box_guids:
            orow = old_faction(guid)
            code = old_faction_name_to_code(orow["name"]) if orow else None
            n = conn.execute(
                "SELECT COUNT(*) FROM custom_box_sets WHERE faction_id=?", (guid,)
            ).fetchone()[0]
            if code:
                conn.execute(
                    "UPDATE custom_box_sets SET faction_id=? WHERE faction_id=?",
                    (code, guid))
                report["faction_remaps"].append(("custom_box_sets", guid,
                                                 orow["name"], f"{code} ({n} rows)"))
            else:
                report["faction_unresolved"].append(
                    ("custom_box_sets", guid, orow["name"] if orow else "?"))

        # --- 4. army_units must be empty ----------------------------------
        army_count = conn.execute("SELECT COUNT(*) FROM army_units").fetchone()[0]

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        bak.close()

    # --- Verification: every owned mini resolves ---------------------------
    unresolved_minis = []
    for r in conn.execute(
        "SELECT id, datasheet_id, unit_bsdata_id FROM minis").fetchall():
        ub = r["unit_bsdata_id"]
        if ub not in store.ds_by_id:
            unresolved_minis.append((r["id"], r["datasheet_id"], ub))
    conn.close()

    # --- Print report ------------------------------------------------------
    print("=" * 64)
    print("PHASE 4 RECONCILIATION REPORT")
    print("=" * 64)
    print(f"unit_bsdata_id NULL/empty: before={before_null} after={after_null}")
    print(f"\nDatasheet GUID remaps ({len(report['datasheet_remaps'])}):")
    for guid, name, new_id, n in report["datasheet_remaps"]:
        print(f"  {guid} '{name}' -> {new_id}  ({n} minis)")
    print(f"\nDatasheet GUIDs UNRESOLVED ({len(report['datasheet_unresolved'])}):")
    for guid, name, n in report["datasheet_unresolved"]:
        print(f"  {guid} '{name}'  ({n} minis) - not carried by Wahapedia")
    print(f"\nFaction remaps ({len(report['faction_remaps'])}):")
    for tbl, guid, oldname, code in report["faction_remaps"]:
        print(f"  [{tbl}] {guid} '{oldname}' -> {code}")
    if report["faction_unresolved"]:
        print(f"\nFaction UNRESOLVED ({len(report['faction_unresolved'])}):")
        for tbl, guid, oldname in report["faction_unresolved"]:
            print(f"  [{tbl}] {guid} '{oldname}'")
    print(f"\narmy_units rows: {army_count} (expected 0)")
    print(f"\nOwned minis whose unit_bsdata_id does NOT resolve: {len(unresolved_minis)}")
    for mid, did, ub in unresolved_minis:
        print(f"  mini={mid} datasheet_id={did} unit_bsdata_id={ub}")


if __name__ == "__main__":
    main()
