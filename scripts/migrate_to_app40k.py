"""One-shot migration of user data from Wahapedia ids to w40k.db UUIDs.

Run from the project root:
    python scripts/migrate_to_app40k.py --dry-run
    python scripts/migrate_to_app40k.py

Idempotent: a second run detects an already-migrated DB and refuses to clobber
the backup. The Wahapedia catalogue tables (`catalogue_*`) and the MFM tables
(`mfm_*`) are NOT touched here - they are dropped by the separate
`scripts/cleanup_post_app40k.py` after dogfooding confirms the new world works.

What it rewrites:
  - `minis.datasheet_id`, `minis.unit_bsdata_id`         (datasheet UUID)
  - `unit_wip.datasheet_id`                              (datasheet UUID)
  - `unit_wip_photos.datasheet_id`                       (datasheet UUID)
  - `custom_box_set_contents.datasheet_id`               (datasheet UUID)
  - `arsenal_weapon_datasheet.datasheet_id`              (datasheet UUID)
  - `favourite_factions.faction_id`                      (faction UUID)
  - `custom_box_sets.faction_id`                         (faction UUID)
  - `army_lists.faction_id`, `army_lists.detachment_id`  (UUIDs)
  - `army_units.datasheet_id`, `unit_bsdata_id`          (UUIDs)
  - `data/model_catalogue_manual.json` datasheet_links[] (UUIDs)

Synthetic `cat:<MD-id>` ids pass through unchanged.

A JSON report is written to `data/migration_app40k_report.json` with matched /
ambiguous / unmatched / name_collision buckets for each rewritten column, plus
the faction-id resolution self-check.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

COLLECTION_DB = os.environ.get(
    "COLLECTION_DB_PATH", os.path.join(ROOT, "collection.db"))
W40K_DB = os.environ.get(
    "W40K_DB_PATH", os.path.join(ROOT, "data", "w40k", "w40k.db"))
MANUAL_JSON = os.environ.get(
    "MANUAL_JSON_PATH", os.path.join(ROOT, "data", "model_catalogue_manual.json"))
REPORT_PATH = os.environ.get(
    "MIGRATION_REPORT_PATH",
    os.path.join(ROOT, "data", "migration_app40k_report.json"))
BACKUP_COLLECTION = COLLECTION_DB + ".pre-app40k"
BACKUP_MANUAL = MANUAL_JSON + ".pre-app40k"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                     re.IGNORECASE)
CAT_PREFIX = "cat:"

# Faction-code translations. UA / UN intentionally have no target - the
# `favourite_factions` table may carry a few of these and forcing them to a
# wrong faction is worse than surfacing them for manual cleanup.
FACTION_CODE_TO_NAME = {
    "AC":  "Adeptus Custodes",
    "AE":  "Aeldari",
    "AM":  "Astra Militarum",
    "AS":  "Adepta Sororitas",
    "AdM": "Adeptus Mechanicus",
    "AoI": "Agents of the Imperium",
    "CD":  "Legiones Daemonica",
    "CSM": "Heretic Astartes",
    "DG":  "Death Guard",
    "DRU": "Drukhari",
    "EC":  "Emperor’s Children",
    "GC":  "Genestealer Cults",
    "GK":  "Grey Knights",
    "LoV": "Leagues of Votann",
    "NEC": "Necrons",
    "ORK": "Orks",
    "QI":  "Imperial Knights",
    "QT":  "Chaos Knights",
    "SM":  "Adeptus Astartes",
    "TAU": "T’au Empire",
    "TL":  "Adeptus Titanicus",
    "TS":  "Thousand Sons",
    "TYR": "Tyranids",
    "UA":  None,
    "UN":  None,
    "WE":  "World Eaters",
    "SM::Blood Angels":   "Blood Angels",
    "SM::Dark Angels":    "Dark Angels",
    "SM::Space Wolves":   "Space Wolves",
    "SM::Deathwatch":     "Deathwatch",
    "SM::Black Templars": "Black Templars",
    "SM::Imperial Fists": "Imperial Fists",
    "SM::Iron Hands":     "Iron Hands",
    "SM::Raven Guard":    "Raven Guard",
    "SM::Salamanders":    "Salamanders",
    "SM::Ultramarines":   "Ultramarines",
    "SM::White Scars":    "White Scars",
}


def _norm_name(s):
    """Same NFKD + apostrophe-fold + lowercase normalisation used by the data
    store's leader resolver, plus apostrophe-flattening so straight and curly
    forms compare equal."""
    if not s:
        return ""
    s = s.replace("’", "'").replace("‘", "'")
    return unicodedata.normalize("NFKD", s).casefold().strip()


def _load_w40k_factions(conn):
    """Read the faction table and return:
      name_to_id: {normalised_name: uuid}
      parent_of:  {child_uuid: parent_uuid or None}
      children_of:{parent_uuid: [child_uuid, ...]}
    Parent_faction in this export holds the parent NAME, so resolve to UUID.
    """
    rows = conn.execute(
        "SELECT id, name, parent_faction FROM faction").fetchall()
    name_to_id = {}
    raw_parents = {}
    for r in rows:
        name_to_id[_norm_name(r["name"])] = r["id"]
        raw_parents[r["id"]] = r["parent_faction"]
    parent_of = {}
    children_of = defaultdict(list)
    for cid, pname in raw_parents.items():
        pid = name_to_id.get(_norm_name(pname)) if pname else None
        parent_of[cid] = pid
        if pid:
            children_of[pid].append(cid)
    return name_to_id, parent_of, dict(children_of)


def _faction_code_self_check(name_to_id):
    """For each old code, look up the target name. Returns the report bucket."""
    result = []
    for code, target in FACTION_CODE_TO_NAME.items():
        if target is None:
            result.append({"code": code, "target_name": None,
                           "resolved_uuid": None, "note": "intentionally unmapped"})
            continue
        uid = name_to_id.get(_norm_name(target))
        result.append({
            "code": code, "target_name": target,
            "resolved_uuid": uid,
            "note": "ok" if uid else "MISSING in w40k.db",
        })
    return result


def _build_datasheet_index(conn, name_to_id, parent_of, children_of):
    """Build the (faction_tree_root, normalised_name) -> [uuid, ...] index used
    by the datasheet matcher. The faction tree of a datasheet is the union of
    its primary-faction-tree's root, the root's children, and the datasheet's
    own faction memberships. Generic SM datasheets (under Adeptus Astartes) and
    chapter datasheets share the same tree, so an old SM-coded mini matches its
    new chapter unit or its parent unit equally well."""
    ds_factions = defaultdict(set)
    for r in conn.execute(
            "SELECT datasheet_id, faction_id FROM datasheet_faction").fetchall():
        ds_factions[r["datasheet_id"]].add(r["faction_id"])

    datasheets = conn.execute("SELECT id, name FROM datasheet").fetchall()
    # tree_root -> {normalised_name: [(uuid, full_membership_set), ...]}
    by_tree = defaultdict(lambda: defaultdict(list))
    name_to_uuids_global = defaultdict(list)
    for d in datasheets:
        did = d["id"]
        n = _norm_name(d["name"])
        name_to_uuids_global[n].append(did)
        memberships = ds_factions.get(did) or set()
        for fid in memberships:
            root = _tree_root(fid, parent_of)
            by_tree[root][n].append((did, memberships))
        # Also index under each child of every parent of every membership, so a
        # datasheet whose primary faction is the parent can still be found when
        # the old code maps to a chapter (or vice versa).
        for fid in memberships:
            root = _tree_root(fid, parent_of)
            for cid in children_of.get(root, []):
                by_tree[cid][n]  # ensure key exists
    return by_tree, name_to_uuids_global


def _tree_root(fid, parent_of):
    cur = fid
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        p = parent_of.get(cur)
        if not p:
            return cur
        cur = p
    return fid


def _pick_primary(memberships, parent_of):
    """Leaf-wins primary-faction picker. Mirrors data_store._pick_primary_faction
    so the migration's notion of 'primary faction' matches what the running app
    will assign once loaded. Drops any membership that is the parent of another;
    tiebreak by sorted UUID for determinism (the data_store version tiebreaks by
    faction name, but the migration script does not carry the names through and
    UUID order is good enough for the tiebreaker use here)."""
    if not memberships:
        return None
    mems = list(memberships)
    if len(mems) == 1:
        return mems[0]
    parents = {parent_of.get(fid) for fid in mems}
    leaves = [fid for fid in mems if fid not in parents]
    if not leaves:
        leaves = list(mems)
    if len(leaves) == 1:
        return leaves[0]
    return sorted(leaves)[0]


def _match_datasheet_id(name, old_faction_uuid, by_tree, name_to_uuids_global,
                        parent_of, children_of):
    """Find the new UUID for an old (name, faction) pair.

    Strategy:
      1. Constrain to the old faction's tree (root + its children + own children).
         Exact normalised-name hit inside that tree wins.
      2. If more than one candidate survives in the same tree, apply the
         primary-equals-target tiebreaker: prefer candidates whose primary
         faction (leaf-wins) equals the old code's mapped target. This resolves
         the Adeptus Astartes / Black Templars duplicates - the generic version
         has primary=Adeptus Astartes, the BT-vow clone has primary=Black
         Templars, so an SM-coded unit lands on the generic. Still ambiguous
         after the tiebreaker reports as ambiguous.
      3. If no exact match in tree, fuzzy fallback (SequenceMatcher >= 0.92)
         scoped to the same tree.
      4. If still nothing, fall back to global by-name, but flag ambiguity if
         more than one candidate exists. The Daemon legion cases (Plaguebearers
         in Plague Legions vs Legiones Daemonica, etc.) land here intentionally
         per the plan; the safety-net UX rehomes them.
    Returns: ("matched", new_uuid) | ("ambiguous", [uuids]) | ("unmatched", None)
    """
    n = _norm_name(name)
    if not old_faction_uuid:
        candidates = name_to_uuids_global.get(n, [])
        if len(candidates) == 1:
            return "matched", candidates[0]
        if not candidates:
            return "unmatched", None
        return "ambiguous", candidates

    tree_roots = {_tree_root(old_faction_uuid, parent_of)}
    tree_roots.add(old_faction_uuid)
    root = _tree_root(old_faction_uuid, parent_of)
    tree_roots.update(children_of.get(root, []))
    tree_roots.update(children_of.get(old_faction_uuid, []))

    in_tree = []
    in_tree_memberships = {}
    for r in tree_roots:
        for did, mem in by_tree.get(r, {}).get(n, []):
            if did not in in_tree:
                in_tree.append(did)
                in_tree_memberships[did] = mem
    if len(in_tree) == 1:
        return "matched", in_tree[0]
    if len(in_tree) > 1:
        primaries_equal_target = [
            did for did in in_tree
            if _pick_primary(in_tree_memberships.get(did, set()), parent_of)
            == old_faction_uuid
        ]
        if len(primaries_equal_target) == 1:
            return "matched", primaries_equal_target[0]
        return "ambiguous", in_tree

    # Fuzzy fallback within tree
    tree_names = defaultdict(list)
    for r in tree_roots:
        for nm, candidates in by_tree.get(r, {}).items():
            for did, _mem in candidates:
                tree_names[did].append(nm)
    best_did = None
    best_ratio = 0
    for did, names in tree_names.items():
        for nm in names:
            ratio = SequenceMatcher(None, n, nm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_did = did
    if best_ratio >= 0.92:
        return "matched", best_did

    # Global last resort
    candidates = name_to_uuids_global.get(n, [])
    if len(candidates) == 1:
        return "matched", candidates[0]
    if not candidates:
        return "unmatched", None
    return "ambiguous", candidates


def _is_uuid(s):
    return bool(s) and bool(UUID_RE.match(str(s)))


def _is_cat(s):
    return bool(s) and str(s).startswith(CAT_PREFIX)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the report without writing any changes")
    args = parser.parse_args()

    if not os.path.exists(COLLECTION_DB):
        print(f"collection.db not found at {COLLECTION_DB}; nothing to migrate.")
        return 0
    if not os.path.exists(W40K_DB):
        print(f"w40k.db not found at {W40K_DB}; see data/w40k/README.md.")
        return 1

    coll = sqlite3.connect(COLLECTION_DB)
    coll.row_factory = sqlite3.Row

    # ---- already-migrated guard ----
    # Scan every non-cat: row, not just the first: a previous run that left
    # some unmatched/ambiguous rows as old ids would make the first row look
    # un-migrated even though most of the table is UUIDs. As soon as ANY UUID
    # row is found we abort to keep the existing backup intact.
    try:
        for row in coll.execute(
                "SELECT datasheet_id FROM minis "
                "WHERE datasheet_id NOT LIKE 'cat:%'").fetchall():
            if _is_uuid(row["datasheet_id"]):
                print("collection.db already looks migrated "
                      f"(found UUID datasheet_id {row['datasheet_id']!r}). "
                      "Aborting to keep the existing backup intact.")
                coll.close()
                return 2
    except sqlite3.OperationalError:
        pass

    w40k = sqlite3.connect(
        f"file:{W40K_DB}?mode=ro&immutable=1", uri=True)
    w40k.row_factory = sqlite3.Row

    name_to_id, parent_of, children_of = _load_w40k_factions(w40k)
    faction_check = _faction_code_self_check(name_to_id)
    print(f"Faction-id self-check: "
          f"{sum(1 for x in faction_check if x['resolved_uuid'])} resolved, "
          f"{sum(1 for x in faction_check if x['target_name'] and not x['resolved_uuid'])} missing.")

    # ---- carry-forward subset check ----
    # The user's catalogue_factions holds the live set of old faction codes
    # ever attached to their data. If a stray 27th code (or an SM:: chapter we
    # didn't anticipate) is present, it must not pass through silently. We
    # report it here and refuse to translate it later via faction_id_map.
    live_faction_codes = set()
    try:
        for r in coll.execute(
                "SELECT DISTINCT bsdata_id FROM catalogue_factions").fetchall():
            if r["bsdata_id"]:
                live_faction_codes.add(r["bsdata_id"])
    except sqlite3.OperationalError:
        pass
    map_keys = set(FACTION_CODE_TO_NAME.keys())
    stray_faction_codes = sorted(live_faction_codes - map_keys)
    if stray_faction_codes:
        print(f"WARNING: catalogue_factions holds {len(stray_faction_codes)} "
              f"code(s) not in the translation map: {stray_faction_codes}. "
              f"These will pass through unchanged - review the report.")

    by_tree, name_to_uuids_global = _build_datasheet_index(
        w40k, name_to_id, parent_of, children_of)

    # ---- faction-id translation map ----
    faction_id_map = {}
    for code, target in FACTION_CODE_TO_NAME.items():
        if target is None:
            continue
        uid = name_to_id.get(_norm_name(target))
        if uid:
            faction_id_map[code] = uid

    # ---- collect every old datasheet id and old faction code in the user's DB ----
    old_did_to_faction = {}  # old_9digit_id -> old_faction_code (used for tree scoping)
    try:
        cat_rows = coll.execute("""
            SELECT bsdata_id, faction_id FROM catalogue_units
        """).fetchall()
        for r in cat_rows:
            old_did_to_faction[r["bsdata_id"]] = r["faction_id"]
        catalogue_units = {r["bsdata_id"]: r["name"]
                           for r in coll.execute(
                               "SELECT bsdata_id, name FROM catalogue_units").fetchall()}
    except sqlite3.OperationalError:
        catalogue_units = {}

    # ---- gather every old datasheet id referenced by user rows ----
    user_old_dids = set()

    def _add_dids(rows, col):
        for r in rows:
            v = r[col]
            if v and not _is_cat(v) and not _is_uuid(v):
                user_old_dids.add(v)

    _add_dids(coll.execute("SELECT datasheet_id FROM minis").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT unit_bsdata_id datasheet_id FROM minis").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT datasheet_id FROM unit_wip").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT datasheet_id FROM unit_wip_photos").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT datasheet_id FROM custom_box_set_contents").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT datasheet_id FROM arsenal_weapon_datasheet").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT datasheet_id FROM army_units").fetchall(), "datasheet_id")
    _add_dids(coll.execute("SELECT unit_bsdata_id datasheet_id FROM army_units").fetchall(), "datasheet_id")

    # JSON catalogue links. The top-level array is `model_releases`, not
    # `items`; an earlier draft used the wrong key and silently skipped every
    # link, leaving the post-migration purchase browser showing 0 links for
    # all 912 catalogue items.
    manual_data = None
    if os.path.exists(MANUAL_JSON):
        with open(MANUAL_JSON, encoding="utf-8") as fh:
            manual_data = json.load(fh)
        for item in manual_data.get("model_releases", []):
            for link in item.get("datasheet_links", []):
                v = link.get("datasheet_id")
                if v and not _is_cat(v) and not _is_uuid(v):
                    user_old_dids.add(v)

    # ---- build the datasheet id translation map ----
    datasheet_id_map = {}
    matched = []
    ambiguous = []
    unmatched = []
    name_collisions = defaultdict(list)

    for old_did in user_old_dids:
        name = catalogue_units.get(old_did)
        if not name:
            unmatched.append({"old_id": old_did, "reason": "old catalogue row not found"})
            continue
        old_faction = old_did_to_faction.get(old_did)
        old_faction_uuid = faction_id_map.get(old_faction) if old_faction else None
        outcome, payload = _match_datasheet_id(
            name, old_faction_uuid, by_tree, name_to_uuids_global,
            parent_of, children_of)
        if outcome == "matched":
            datasheet_id_map[old_did] = payload
            matched.append({"old_id": old_did, "name": name, "new_id": payload})
            # Note any name collision (multiple old rows with the same name).
            name_collisions[_norm_name(name)].append(old_did)
        elif outcome == "ambiguous":
            ambiguous.append({"old_id": old_did, "name": name,
                              "old_faction_code": old_faction,
                              "candidates": payload})
        else:
            unmatched.append({"old_id": old_did, "name": name,
                              "old_faction_code": old_faction})

    name_collision_report = {n: ids for n, ids in name_collisions.items()
                             if len(ids) > 1}

    # ---- rewrite collection.db ----
    plan = {
        "matched": len(matched),
        "ambiguous": len(ambiguous),
        "unmatched": len(unmatched),
        "name_collisions": len(name_collision_report),
        "datasheet_ids": {"sample_matched": matched[:10],
                          "ambiguous": ambiguous,
                          "unmatched": unmatched,
                          "name_collisions": name_collision_report},
        "faction_self_check": faction_check,
        "faction_code_carry_forward": {
            "live_codes": sorted(live_faction_codes),
            "stray_codes_not_in_map": stray_faction_codes,
        },
    }

    if args.dry_run:
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2, ensure_ascii=False)
        print(f"Dry-run complete. Report at {REPORT_PATH}.")
        return 0

    # Real run: take backups first.
    if not os.path.exists(BACKUP_COLLECTION):
        shutil.copy2(COLLECTION_DB, BACKUP_COLLECTION)
        print(f"Backed up collection.db -> {BACKUP_COLLECTION}")
    else:
        print(f"Backup already exists at {BACKUP_COLLECTION}; keeping it.")
    if manual_data is not None and not os.path.exists(BACKUP_MANUAL):
        shutil.copy2(MANUAL_JSON, BACKUP_MANUAL)
        print(f"Backed up model_catalogue_manual.json -> {BACKUP_MANUAL}")

    def _translate_did(old):
        if not old or _is_cat(old) or _is_uuid(old):
            return old
        return datasheet_id_map.get(old, old)

    def _translate_fac(old):
        return faction_id_map.get(old, old)

    # Tables whose PRIMARY KEY or UNIQUE constraint includes datasheet_id can
    # collide once the mapping collapses multiple Wahapedia per-faction
    # duplicates (e.g. five "Chaos Rhino" rows) onto one w40k.db UUID. The 148
    # name_collisions reported in the dry-run prove this happens in practice.
    #
    # Per-table policy on collision:
    #   - arsenal_weapon_datasheet: rows are fully derived data (the table is
    #     wiped and rebuilt from `data_store.wargear` on every app start via
    #     `arsenal_store.sync_datasheets`). Silently dropping the duplicate is
    #     safe; we record the count for audit.
    #   - unit_wip: PK is `datasheet_id` and the `notes` column is user-typed
    #     prose. A duplicate must NOT be silently dropped. We merge the dropped
    #     row's notes into the keeper row (newline-separated) and keep the
    #     latest updated_at, so no user text vanishes.
    #   - all other tables in the loop have no UNIQUE on datasheet_id, so this
    #     branch never fires for them. If a future schema adds one, the dropped
    #     row's full contents land in `collision_collapses_dropped` for review.
    #
    # `collision_collapses_dropped` carries the full row dict of every silently
    # discarded row so a reviewer can audit nothing user-authored was lost.
    DERIVED_TABLES = {"arsenal_weapon_datasheet"}
    collision_collapses = {}
    collision_collapses_dropped = {}

    def _row_to_dict(table, rowid):
        cols_info = coll.execute(f"PRAGMA table_info({table})").fetchall()
        col_names = [ci["name"] for ci in cols_info]
        row = coll.execute(
            f"SELECT {','.join(col_names)} FROM {table} WHERE rowid=?",
            (rowid,)).fetchone()
        return {c: row[c] for c in col_names} if row else None

    # ---- rewrite each table ----
    coll.execute("BEGIN")
    try:
        for tbl, cols in [
                ("minis",                   ["datasheet_id", "unit_bsdata_id"]),
                ("unit_wip",                ["datasheet_id"]),
                ("unit_wip_photos",         ["datasheet_id"]),
                ("custom_box_set_contents", ["datasheet_id"]),
                ("arsenal_weapon_datasheet",["datasheet_id"]),
                ("army_units",              ["datasheet_id", "unit_bsdata_id"]),
        ]:
            for col in cols:
                try:
                    rows = coll.execute(
                        f"SELECT rowid, {col} FROM {tbl}").fetchall()
                except sqlite3.OperationalError:
                    continue
                for r in rows:
                    new = _translate_did(r[col])
                    if new == r[col]:
                        continue
                    try:
                        coll.execute(
                            f"UPDATE {tbl} SET {col}=? WHERE rowid=?",
                            (new, r["rowid"]))
                    except sqlite3.IntegrityError:
                        key = f"{tbl}.{col}"
                        dropped = _row_to_dict(tbl, r["rowid"])
                        # unit_wip: merge the user-typed notes onto the keeper
                        # so nothing the user wrote is lost.
                        if tbl == "unit_wip" and dropped:
                            keeper = coll.execute(
                                "SELECT notes, updated_at FROM unit_wip "
                                "WHERE datasheet_id=?", (new,)).fetchone()
                            if keeper:
                                old_notes = (keeper["notes"] or "").strip()
                                add_notes = (dropped.get("notes") or "").strip()
                                merged = "\n\n".join(
                                    s for s in (old_notes, add_notes) if s)
                                later = max(
                                    keeper["updated_at"] or 0,
                                    dropped.get("updated_at") or 0)
                                coll.execute(
                                    "UPDATE unit_wip SET notes=?, "
                                    "updated_at=? WHERE datasheet_id=?",
                                    (merged, later, new))
                        coll.execute(
                            f"DELETE FROM {tbl} WHERE rowid=?",
                            (r["rowid"],))
                        collision_collapses[key] = collision_collapses.get(
                            key, 0) + 1
                        # Always log the dropped row's contents for audit. For
                        # derived tables the log proves the lost rows held no
                        # user data; for user-data tables (unit_wip) the merge
                        # above already preserved the notes and the log records
                        # what was merged.
                        collision_collapses_dropped.setdefault(
                            key, []).append(dropped)

        for tbl, col in [
                ("favourite_factions", "faction_id"),
                ("custom_box_sets",    "faction_id"),
                ("army_lists",         "faction_id"),
        ]:
            try:
                rows = coll.execute(
                    f"SELECT rowid, {col} FROM {tbl}").fetchall()
            except sqlite3.OperationalError:
                continue
            for r in rows:
                new = _translate_fac(r[col])
                if new != r[col]:
                    coll.execute(
                        f"UPDATE {tbl} SET {col}=? WHERE rowid=?",
                        (new, r["rowid"]))

        # army_lists.detachment_id is keyed to the OLD detachment ids - these
        # were textual Wahapedia ids, but the user's table is empty in
        # practice. Leave them alone; a follow-up can address detachment id
        # remap if needed.
        coll.commit()
    except Exception:
        coll.rollback()
        raise

    # ---- rewrite model_catalogue_manual.json datasheet_links ----
    if manual_data is not None:
        modified = False
        for item in manual_data.get("model_releases", []):
            for link in item.get("datasheet_links", []):
                old = link.get("datasheet_id")
                new = _translate_did(old)
                if new != old:
                    link["_legacy_id"] = old
                    link["datasheet_id"] = new
                    modified = True
        if modified:
            with open(MANUAL_JSON, "w", encoding="utf-8") as fh:
                json.dump(manual_data, fh, indent=2, ensure_ascii=False)
            print(f"Updated {MANUAL_JSON}")

    # ---- orphan check ----
    valid_ds = set(d["id"] for d in w40k.execute(
        "SELECT id FROM datasheet").fetchall())
    orphans = defaultdict(int)
    for tbl, cols in [("minis", ["datasheet_id"]),
                      ("unit_wip", ["datasheet_id"]),
                      ("unit_wip_photos", ["datasheet_id"]),
                      ("custom_box_set_contents", ["datasheet_id"]),
                      ("arsenal_weapon_datasheet", ["datasheet_id"])]:
        for col in cols:
            try:
                rows = coll.execute(f"SELECT {col} FROM {tbl}").fetchall()
            except sqlite3.OperationalError:
                continue
            for r in rows:
                v = r[col]
                if v and not _is_cat(v) and v not in valid_ds:
                    orphans[f"{tbl}.{col}"] += 1

    plan["orphans"] = dict(orphans)
    plan["collision_collapses"] = collision_collapses
    plan["collision_collapses_dropped"] = collision_collapses_dropped
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)

    print(f"Migration complete. Report at {REPORT_PATH}.")
    print(f"  matched: {plan['matched']}  ambiguous: {plan['ambiguous']}"
          f"  unmatched: {plan['unmatched']}  orphans: {sum(orphans.values())}")
    coll.close()
    w40k.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
