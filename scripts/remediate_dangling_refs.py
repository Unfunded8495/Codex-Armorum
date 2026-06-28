"""Backward remediation of the dangling rules references the w40k migration left.

Runs the registry-driven cleanup the verifier's --report worklist describes, so
check (A) reaches literal zero. Defaults to a dry run; pass --apply to mutate.
Backs up collection.db and the two JSON catalogues on the first apply and never
overwrites a backup, so a re-run is safe.

Policy by class (registry authority/nullable drives it, not a uniform null):

  collection.db, name-bridgeable  re-key the column to the current w40k UUID via
                                  legacy_datasheet_names.json (the user's WIP
                                  prose / painting state is the data; the id is
                                  just its key).
  collection.db, irreducible      move the whole row to quarantined_refs and
                                  remove it from the live table. NOT NULL / PK
                                  columns cannot be nulled in place, so the row
                                  is preserved in quarantine rather than deleted
                                  into nothing.
  photos.datasheet_id             DROP COLUMN (destructive, hence deferred here
                                  and not in db.py init_db). Write-only column.

  manual.json dead datasheet_link:
    recoverable (name matches a current datasheet, e.g. Vyper -> Vyper):
                                  fix the raw link to the current UUID + faction.
    covered (record still renders via another live link or a winning resolution):
                                  blank datasheet_id to "" (keep datasheet_name).
    genuinely absent (no current 10th-ed datasheet):
                                  blank datasheet_id to "", then for the
                                  unambiguous removed/Legends units add a sticky
                                  no_current_datasheet resolution (a future
                                  auto-import would otherwise re-link and
                                  re-break an empty link list). The ambiguous
                                  "gone vs renamed" characters are emitted to a
                                  needs-review tail and NOT auto-marked.

  resolutions.json dead datasheet_id:
                                  drop it from the resolution's datasheet_ids.

A JSON report is written to data/remediation_report.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import catalogue_id_locations as R  # noqa: E402
import catalogue_links as cl  # noqa: E402

DATA_DIR = os.path.join(BASE, "data")
COLLECTION_DB = os.environ.get("COLLECTION_DB_PATH", os.path.join(BASE, "collection.db"))
MANUAL_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
RES_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
LEGACY_NAMES = os.path.join(BASE, "archive", "data", "legacy_datasheet_names.json")
REPORT_PATH = os.path.join(DATA_DIR, "remediation_report.json")

# Named units whose dead link is "gone vs renamed" ambiguous: do NOT auto-mark
# no_current_datasheet (that would hide a rename); surface for manual review.
AMBIGUOUS_ABSENT = {
    "Minka Lesk", "Ferren Areios", "Sergeant Harker", "Da Red Gobbo",
    "Ufthak Blackhawk",
}


def _norm(s: str) -> str:
    """Fuzzy name key: lowercase, alnum-collapse, singularise trailing s, drop a
    trailing Squad/Team (catalogue 'Vypers' -> w40k 'Vyper')."""
    s = str(s or "").lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in s.split()]
    while words and words[-1] in ("squad", "team"):
        words.pop()
    return " ".join(words)


def _root(fid, store):
    """Walk to the faction tree root (faction_parent returns self at the top)."""
    seen = set()
    while fid and fid not in seen:
        seen.add(fid)
        parent = store.faction_parent(fid)
        if parent == fid:
            return fid
        fid = parent
    return fid


def _family_keys(fid, store):
    """A faction's army family, as the lowercased {name, common_name} of its tree
    root. Asuryani's root carries common_name 'Aeldari', so an 'Aeldari'-factioned
    catalogue record and an 'Asuryani' datasheet share a family even though they
    are sibling roots."""
    fac = store.faction_by_id.get(_root(fid, store), {})
    return {v.strip().lower() for v in (fac.get("name"), fac.get("common_name")) if v}


def _load(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def _write_json(path, doc):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
def remediate_manual(report, store, valid_ds, w40k_by_norm, *, apply):
    doc = _load(MANUAL_PATH, {"model_releases": []})
    resolutions = {r.get("catalogue_model_id"): r
                   for r in _load(RES_PATH, {"resolutions": []}).get("resolutions", [])}

    recovered, cruft_blanked, absent_blanked = [], [], []
    to_mark, needs_review = [], []

    def is_dead(did):
        return (did and did not in valid_ds
                and not R.is_cat_id(did) and not R.is_md_id(did))

    for rec in doc.get("model_releases", []):
        cid = rec.get("id")
        links = rec.get("datasheet_links", []) or []
        dead = [l for l in links if is_dead(l.get("datasheet_id"))]
        if not dead:
            continue
        eff = cl.effective_link_ids(rec, resolutions.get(cid, {}))
        eff_valid = any(d in valid_ds for d in eff)

        if eff_valid:
            for l in dead:
                l["_legacy_id"] = l.get("_legacy_id") or l["datasheet_id"]
                l["datasheet_id"] = ""
            cruft_blanked.append({"id": cid, "name": rec.get("name"), "links": len(dead)})
            continue

        # sole-link record: recover only when EXACTLY ONE current datasheet of
        # the same name lives in this record's faction TREE (same root). Tree
        # root, not one-level parent, so an Aeldari record matches its Asuryani
        # Vyper datasheet; "exactly one" so an ambiguous multi-faction name (a
        # bare "Venerable Dreadnought" across chapters) is left for review, not
        # linked to an arbitrary one.
        rec_fam = _family_keys(rec.get("faction_id", ""), store)
        hits, seen_ids = [], set()
        for c in [rec.get("name", "")] + [l.get("datasheet_name", "") for l in dead]:
            for d in w40k_by_norm.get(_norm(c), []):
                if d["id"] in seen_ids:
                    continue
                if not rec_fam or (_family_keys(d["faction_id"], store) & rec_fam):
                    hits.append(d)
                    seen_ids.add(d["id"])
        if len(hits) == 1:
            # Pin via a link_datasheet resolution so the recovery renders even if
            # a stale no_current_datasheet / emptied link resolution was
            # shadowing the raw link; the dead raw links are then blanked.
            for l in dead:
                l["_legacy_id"] = l.get("_legacy_id") or l["datasheet_id"]
                l["datasheet_id"] = ""
            recovered.append({"id": cid, "name": rec.get("name"),
                              "to": hits[0]["name"], "pin": hits[0]["id"]})
            continue

        # genuinely absent
        for l in dead:
            l["_legacy_id"] = l.get("_legacy_id") or l["datasheet_id"]
            l["datasheet_id"] = ""
        absent_blanked.append({"id": cid, "name": rec.get("name")})
        if rec.get("name") in AMBIGUOUS_ABSENT:
            needs_review.append({"id": cid, "name": rec.get("name")})
        else:
            to_mark.append({"id": cid, "name": rec.get("name")})

    # Add sticky no_current_datasheet resolutions for the unambiguous absent.
    res_doc = _load(RES_PATH, {"resolutions": []})
    res_list = res_doc.get("resolutions", [])
    res_by_id = {r.get("catalogue_model_id"): r for r in res_list}
    for item in to_mark:
        existing = res_by_id.get(item["id"])
        marker = {
            "catalogue_model_id": item["id"],
            "action": "no_current_datasheet",
            "catalogue_type": (existing or {}).get("catalogue_type", ""),
            "datasheet_ids": [],
            "notes": "No current 10th-edition datasheet (remediation auto-mark).",
            "updated_at": time.time(),
        }
        if existing:
            existing.update(marker)
        else:
            res_list.append(marker)
    # Pin recovered records to their current datasheet, replacing any stale
    # no_current_datasheet / emptied link resolution that would shadow the link.
    for item in recovered:
        existing = res_by_id.get(item["id"])
        pin = {
            "catalogue_model_id": item["id"],
            "action": "link_datasheet",
            "catalogue_type": (existing or {}).get("catalogue_type", ""),
            "datasheet_ids": [item["pin"]],
            "notes": "Re-linked to current datasheet (remediation).",
            "updated_at": time.time(),
        }
        if existing:
            existing.update(pin)
        else:
            res_list.append(pin)
    res_list.sort(key=lambda r: r.get("catalogue_model_id", ""))
    res_doc["resolutions"] = res_list

    report["manual_json"] = {
        "recovered": recovered,
        "cruft_blanked": len(cruft_blanked),
        "absent_blanked": len(absent_blanked),
        "no_current_marked": len(to_mark),
        "needs_review": needs_review,
    }
    if apply:
        _write_json(MANUAL_PATH, doc)
        _write_json(RES_PATH, res_doc)


def remediate_resolutions(report, valid_ds, *, apply):
    doc = _load(RES_PATH, {"resolutions": []})
    dropped = []
    for r in doc.get("resolutions", []):
        if r.get("action") not in ("link_datasheet", "link_multiple_datasheets"):
            continue
        ids = r.get("datasheet_ids") or []
        kept = [d for d in ids
                if d in valid_ds or R.is_cat_id(d) or R.is_md_id(d)]
        if len(kept) != len(ids):
            dropped.append({"id": r.get("catalogue_model_id"),
                            "dropped": [d for d in ids if d not in kept]})
            r["datasheet_ids"] = kept
    report["resolutions_json"] = {"dead_ids_dropped": dropped}
    if apply and dropped:
        _write_json(RES_PATH, doc)


# ---------------------------------------------------------------------------
def _legacy_map():
    return _load(LEGACY_NAMES, {}).get("datasheet_names", {})


def _bridge(dead_id, legacy, w40k_by_norm):
    # Collection rows carry no faction to scope by, so take the first current
    # datasheet of that name (the collection page rehomes via the catalogue).
    name = legacy.get(dead_id)
    if not name:
        return None, None
    cands = w40k_by_norm.get(_norm(name), [])
    return (cands[0]["id"] if cands else None), name


def _quarantine(conn, location, table, rowid, dead_id, recovered_name, reason):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    row = conn.execute(f"SELECT {','.join(cols)} FROM {table} WHERE rowid=?", (rowid,)).fetchone()
    payload = {c: row[i] for i, c in enumerate(cols)}
    conn.execute(
        "INSERT INTO quarantined_refs(id, source_location, dead_id, recovered_name, "
        "row_json, reason, quarantined_at) VALUES(?,?,?,?,?,?,?)",
        (uuid.uuid4().hex, location, dead_id, recovered_name or "",
         json.dumps(payload, ensure_ascii=False), reason, time.time()))


def remediate_collection(report, valid_ds, legacy, w40k_by_norm, *, apply):
    conn = sqlite3.connect(COLLECTION_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS quarantined_refs(
        id TEXT PRIMARY KEY, source_location TEXT NOT NULL, dead_id TEXT NOT NULL,
        recovered_name TEXT DEFAULT '', row_json TEXT NOT NULL, reason TEXT DEFAULT '',
        quarantined_at REAL NOT NULL)""")

    stats = {"bridged": 0, "quarantined": 0, "nulled": 0, "photos_column_dropped": False,
             "detail": []}

    def dead(did):
        return (did and did not in valid_ds
                and not R.is_cat_id(did) and not R.is_md_id(did))

    conn.execute("BEGIN")
    try:
        # -- minis: datasheet_id is NOT NULL, unit_bsdata_id is nullable --------
        for rowid, dsid, ubid in conn.execute(
                "SELECT rowid, datasheet_id, unit_bsdata_id FROM minis").fetchall():
            if dead(dsid):
                new, name = _bridge(dsid, legacy, w40k_by_norm)
                if new:
                    nb, _ = _bridge(ubid, legacy, w40k_by_norm) if dead(ubid) else (ubid, None)
                    conn.execute("UPDATE minis SET datasheet_id=?, unit_bsdata_id=? WHERE rowid=?",
                                 (new, nb or new, rowid))
                    stats["bridged"] += 1
                else:
                    _quarantine(conn, "minis.datasheet_id", "minis", rowid, dsid, name,
                                "no current datasheet, no name bridge")
                    conn.execute("DELETE FROM photos WHERE mini_id=("
                                 "SELECT id FROM minis WHERE rowid=?)", (rowid,))
                    conn.execute("DELETE FROM minis WHERE rowid=?", (rowid,))
                    stats["quarantined"] += 1
            elif dead(ubid):
                nb, _ = _bridge(ubid, legacy, w40k_by_norm)
                conn.execute("UPDATE minis SET unit_bsdata_id=? WHERE rowid=?", (nb, rowid))
                stats["bridged" if nb else "nulled"] += 1

        # -- unit_wip: datasheet_id is the PK ----------------------------------
        for rowid, dsid in conn.execute(
                "SELECT rowid, datasheet_id FROM unit_wip").fetchall():
            if not dead(dsid):
                continue
            new, name = _bridge(dsid, legacy, w40k_by_norm)
            if new:
                keeper = conn.execute("SELECT notes, updated_at FROM unit_wip "
                                      "WHERE datasheet_id=?", (new,)).fetchone()
                if keeper:  # merge notes onto the existing keeper, drop this row
                    old = conn.execute("SELECT notes, updated_at FROM unit_wip WHERE rowid=?",
                                       (rowid,)).fetchone()
                    merged = "\n\n".join(s for s in ((keeper[0] or "").strip(),
                                                     (old[0] or "").strip()) if s)
                    conn.execute("UPDATE unit_wip SET notes=?, updated_at=? WHERE datasheet_id=?",
                                 (merged, max(keeper[1] or 0, old[1] or 0), new))
                    conn.execute("DELETE FROM unit_wip WHERE rowid=?", (rowid,))
                else:
                    conn.execute("UPDATE unit_wip SET datasheet_id=? WHERE rowid=?", (new, rowid))
                stats["bridged"] += 1
            else:
                _quarantine(conn, "unit_wip.datasheet_id", "unit_wip", rowid, dsid, name,
                            "no current datasheet, no name bridge")
                conn.execute("DELETE FROM unit_wip WHERE rowid=?", (rowid,))
                stats["quarantined"] += 1

        # -- unit_wip_photos, custom_box_set_contents: NOT NULL, not PK --------
        for table in ("unit_wip_photos", "custom_box_set_contents"):
            for rowid, dsid in conn.execute(
                    f"SELECT rowid, datasheet_id FROM {table}").fetchall():
                if not dead(dsid):
                    continue
                new, name = _bridge(dsid, legacy, w40k_by_norm)
                if new:
                    conn.execute(f"UPDATE {table} SET datasheet_id=? WHERE rowid=?", (new, rowid))
                    stats["bridged"] += 1
                else:
                    _quarantine(conn, f"{table}.datasheet_id", table, rowid, dsid, name,
                                "no current datasheet, no name bridge")
                    conn.execute(f"DELETE FROM {table} WHERE rowid=?", (rowid,))
                    stats["quarantined"] += 1

        # -- photos.datasheet_id: retire the write-only column -----------------
        cols = [r[1] for r in conn.execute("PRAGMA table_info(photos)")]
        if "datasheet_id" in cols:
            conn.execute("ALTER TABLE photos DROP COLUMN datasheet_id")
            stats["photos_column_dropped"] = True

        if apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        report["collection_db"] = stats
        conn.close()


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Mutate the data. Without it, dry-run (report only).")
    args = parser.parse_args()

    from data_store import get_store
    store = get_store()
    valid_ds = set(store.ds_by_id)
    w40k_by_norm = {}
    for d in store.datasheets:
        w40k_by_norm.setdefault(_norm(d["name"]), []).append(d)
    legacy = _legacy_map()

    if args.apply:
        for src, suffix in ((COLLECTION_DB, ".pre-remediate"),
                            (MANUAL_PATH, ".pre-remediate"),
                            (RES_PATH, ".pre-remediate")):
            dst = src + suffix
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"Backed up {os.path.basename(src)} -> {os.path.basename(dst)}")

    report = {"mode": "apply" if args.apply else "dry-run", "at": time.time()}
    remediate_manual(report, store, valid_ds, w40k_by_norm, apply=args.apply)
    remediate_resolutions(report, valid_ds, apply=args.apply)
    remediate_collection(report, valid_ds, legacy, w40k_by_norm, apply=args.apply)

    _write_json(REPORT_PATH, report)

    m, c = report["manual_json"], report["collection_db"]
    print(f"\n--- Remediation {report['mode']} ---")
    print(f"manual.json:   recovered={len(m['recovered'])} cruft_blanked={m['cruft_blanked']} "
          f"absent_blanked={m['absent_blanked']} no_current_marked={m['no_current_marked']} "
          f"needs_review={len(m['needs_review'])}")
    print(f"resolutions:   dead_ids_dropped={len(report['resolutions_json']['dead_ids_dropped'])}")
    print(f"collection.db: bridged={c['bridged']} quarantined={c['quarantined']} "
          f"nulled={c['nulled']} photos_column_dropped={c['photos_column_dropped']}")
    if m["recovered"]:
        print("  recovered:", ", ".join(f"{r['name']}->{r['to']}" for r in m["recovered"]))
    if m["needs_review"]:
        print("  needs review (gone vs renamed):",
              ", ".join(r["name"] for r in m["needs_review"]))
    print(f"\nReport -> {REPORT_PATH}")
    if not args.apply:
        print("Dry-run: no changes written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
