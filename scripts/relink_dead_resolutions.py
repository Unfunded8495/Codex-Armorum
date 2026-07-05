"""Recover resolution rows whose datasheet_ids the w40k translation emptied.

scripts/translate_resolution_datasheet_ids.py translated each linkable
resolution's legacy 9-digit Wahapedia ids to w40k.db UUIDs using only the
owning record's own ``_legacy_id`` audit trail. 131 rows ("fully_dead" in
archive/data/catalogue_resolution_translate_report.json) had no per-record
bridge, so their ``datasheet_ids`` were emptied in place. Because a pinned
link action *overrides* the record's raw ``datasheet_links``
(catalogue_links.effective_link_ids), those records now render with no
datasheet at all — including models the user owns.

This script resolves each dead row's ORIGINAL legacy ids (still present in
archive/data/model_catalogue_resolutions.json.pre-ds-translate) through two
bridges, in order:

  1. exact       The audit trail applied GLOBALLY: every ``_legacy_id`` ->
                 ``datasheet_id`` pair across ALL manual.json records. The
                 per-record scoping in the original translation was
                 defensive; in practice the map is conflict-free, so a hit
                 here is an id-level certainty.
  2. name-exact  legacy id -> name via collection.db ``catalogue_units``
                 (the legacy Wahapedia mirror keyed by those same 9-digit
                 ids; fallback archive/data/legacy_datasheet_names.json),
                 then normalised-name match against current w40k.db
                 datasheets. Candidates in the owning record's parent-faction
                 scope win over out-of-scope ones; the match must be unique.

A row is auto-applied only when EVERY original legacy id resolves; partial
or ambiguous rows are left untouched (still empty) and land in the report's
``needs_review`` list, tagged with whether the model is owned (referenced by
a minis row) so the worklist can be prioritised.

Outputs
-------
- Report: data/catalogue_relink_report.json (written on dry-run and apply).
- Backup: data/model_catalogue_resolutions.json.pre-relink (first apply only).

Dry-run is the default; pass --apply to rewrite the resolutions file.
Run scripts/find_datasheet_gaps.py --verify afterwards (integrity gate).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from find_datasheet_gaps import normalise  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
RES_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
MAN_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
PRE_TRANSLATE_PATH = os.path.join(
    ROOT, "archive", "data", "model_catalogue_resolutions.json.pre-ds-translate")
LEGACY_NAMES_PATH = os.path.join(ROOT, "archive", "data", "legacy_datasheet_names.json")
COLLECTION_DB = os.environ.get("COLLECTION_DB_PATH", os.path.join(ROOT, "collection.db"))
W40K_DB = os.environ.get("W40K_DB_PATH", os.path.join(DATA_DIR, "w40k", "w40k.db"))
BACKUP_PATH = RES_PATH + ".pre-relink"
REPORT_PATH = os.path.join(DATA_DIR, "catalogue_relink_report.json")

LINK_ACTIONS = ("link_datasheet", "link_multiple_datasheets")


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _global_audit_bridge(manual):
    """{legacy_id: uuid} across every record's datasheet_links audit trail.
    Conflicting pairs (same legacy id, different uuid) are dropped entirely so
    the bridge only ever answers when the answer is unambiguous."""
    out, conflicted = {}, set()
    for rec in manual.get("model_releases", []):
        for link in rec.get("datasheet_links", []):
            legacy, new = link.get("_legacy_id"), link.get("datasheet_id")
            if not (legacy and new):
                continue
            if legacy in out and out[legacy] != new:
                conflicted.add(legacy)
            out[legacy] = new
    for legacy in conflicted:
        del out[legacy]
    return out


def _legacy_name_map():
    """{legacy_id: unit name}: collection.db catalogue_units first (complete
    Wahapedia-era mirror), archived legacy_datasheet_names.json as fallback."""
    names = {}
    try:
        doc = _load_json(LEGACY_NAMES_PATH)
        names.update(doc.get("datasheet_names", {}))
    except (OSError, ValueError):
        pass
    conn = sqlite3.connect(COLLECTION_DB)
    try:
        for bsdata_id, name in conn.execute("SELECT bsdata_id, name FROM catalogue_units"):
            if bsdata_id and name:
                names[bsdata_id] = name
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return names


def _current_datasheets():
    """(valid_ids, name_index, ds_factions, faction_parent) from w40k.db."""
    conn = sqlite3.connect(f"file:{W40K_DB}?mode=ro&immutable=1", uri=True)
    try:
        ds_factions = {}
        for did, fid in conn.execute("SELECT datasheet_id, faction_id FROM datasheet_faction"):
            ds_factions.setdefault(did, []).append(fid)
        name_index, valid, names = {}, set(), {}
        for did, name in conn.execute("SELECT id, name FROM datasheet"):
            valid.add(did)
            names[did] = name
            name_index.setdefault(normalise(name), []).append(did)
        faction_parent = {fid: (parent or fid) for fid, parent
                          in conn.execute("SELECT id, parent_faction FROM faction")}
    finally:
        conn.close()
    return valid, name_index, names, ds_factions, faction_parent


def _owned_catalogue_ids():
    conn = sqlite3.connect(COLLECTION_DB)
    try:
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT catalogue_model_id FROM minis "
            "WHERE catalogue_model_id IS NOT NULL")}
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


class Resolver:
    def __init__(self):
        manual = _load_json(MAN_PATH)
        self.records = {r["id"]: r for r in manual.get("model_releases", [])}
        self.audit = _global_audit_bridge(manual)
        self.legacy_names = _legacy_name_map()
        (self.valid, self.name_index, self.ds_names,
         self.ds_factions, self.faction_parent) = _current_datasheets()

    def _scope(self, catalogue_model_id):
        fid = self.records.get(catalogue_model_id, {}).get("faction_id", "")
        return self.faction_parent.get(fid, fid)

    def resolve_one(self, legacy_id, scope):
        """-> (uuid, method, detail) with uuid None on failure."""
        if legacy_id in self.valid:  # already a current id, nothing to do
            return legacy_id, "already_current", self.ds_names[legacy_id]
        mapped = self.audit.get(legacy_id)
        if mapped and mapped in self.valid:
            return mapped, "exact", self.ds_names[mapped]
        lname = self.legacy_names.get(legacy_id)
        if not lname:
            return None, "no_legacy_name", None
        candidates = self.name_index.get(normalise(lname), [])
        in_scope = [d for d in candidates
                    if any(self.faction_parent.get(f, f) == scope
                           for f in self.ds_factions.get(d, []))]
        pick = in_scope or candidates
        if len(pick) == 1:
            return pick[0], "name_exact", f"{lname!r} -> {self.ds_names[pick[0]]!r}"
        if pick:
            return None, "ambiguous", f"{lname!r} matches " + ", ".join(
                self.ds_names[d] for d in pick)
        return None, "no_name_match", repr(lname)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Rewrite the resolutions file (default is dry-run).")
    args = parser.parse_args()

    resolutions = _load_json(RES_PATH)
    backup_rows = {r.get("catalogue_model_id"): r
                   for r in _load_json(PRE_TRANSLATE_PATH).get("resolutions", [])}
    resolver = Resolver()
    owned = _owned_catalogue_ids()

    applied, needs_review = [], []
    for row in resolutions.get("resolutions", []):
        if row.get("action") not in LINK_ACTIONS or (row.get("datasheet_ids") or []):
            continue
        cid = row.get("catalogue_model_id")
        original = list(backup_rows.get(cid, {}).get("datasheet_ids") or [])
        scope = resolver._scope(cid)
        resolved, failures = [], []
        for legacy_id in original:
            uuid, method, detail = resolver.resolve_one(legacy_id, scope)
            if uuid:
                resolved.append({"legacy_id": legacy_id, "datasheet_id": uuid,
                                 "datasheet_name": resolver.ds_names[uuid],
                                 "method": method})
            else:
                failures.append({"legacy_id": legacy_id, "reason": method,
                                 "detail": detail})
        entry = {
            "catalogue_model_id": cid,
            "name": resolver.records.get(cid, {}).get("name"),
            "owned": cid in owned,
            "original_legacy_ids": original,
            "resolved": resolved,
            "failures": failures,
        }
        if original and resolved and not failures:
            # dedupe, preserving order (multi-id rows can map to one sheet)
            seen, ids = set(), []
            for r in resolved:
                if r["datasheet_id"] not in seen:
                    seen.add(r["datasheet_id"])
                    ids.append(r["datasheet_id"])
            row["datasheet_ids"] = ids
            row["updated_at"] = time.time()
            applied.append(entry)
        else:
            needs_review.append(entry)

    report = {
        "generated_at": time.time(),
        "mode": "apply" if args.apply else "dry-run",
        "summary": {
            "dead_rows": len(applied) + len(needs_review),
            "auto_linked": len(applied),
            "auto_linked_owned": sum(1 for e in applied if e["owned"]),
            "needs_review": len(needs_review),
            "needs_review_owned": sum(1 for e in needs_review if e["owned"]),
        },
        "applied": applied,
        "needs_review": needs_review,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    s = report["summary"]
    print(f"Dead link rows:      {s['dead_rows']}")
    print(f"Auto-linked:         {s['auto_linked']} (owned: {s['auto_linked_owned']})")
    print(f"Needs review:        {s['needs_review']} (owned: {s['needs_review_owned']})")
    print(f"Report -> {REPORT_PATH}")

    if not args.apply:
        print("Dry-run: resolutions file untouched. Re-run with --apply to write.")
        return 0
    if not applied:
        print("Nothing to apply.")
        return 0

    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(RES_PATH, BACKUP_PATH)
        print(f"Backup -> {BACKUP_PATH}")
    tmp = RES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(resolutions, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, RES_PATH)
    print(f"Rewrote {RES_PATH}")
    print("Now run: python scripts/find_datasheet_gaps.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
