"""Catalogue / rules integrity tool: coverage gaps and dangling references.

Two jobs, one tool, three modes:

  (default)          Coverage report. Every w40k.db datasheet that no catalogue
                     model release effectively links to. Writes
                     data/datasheet_gaps.json + .csv. This is check (B): the count
                     is expected nonzero (Legends, never-modelled units) and is
                     gated on regression vs a committed baseline, not on zero.

  --report           Dangling-reference worklist. Walks every user-data location
                     in catalogue_id_locations.LOCATIONS and prints each stored id
                     that resolves to nothing, classified re-resolvable vs
                     irreducible. Exit 0. This report IS the remediation worklist.

  --verify           Gate mode. Check (A): exit 1 if ANY user-data ref dangles
                     (zero tolerance, no baseline). Check (B): exit 1 if coverage
                     gaps regress beyond data/datasheet_gaps_baseline.json. The
                     quarantine count is printed separately so orphaned minis are
                     known, not silent.

  --update-baseline  Regenerate check (B)'s baseline deliberately.

Linked-id definition (the raw-union to effective-union shift)
-------------------------------------------------------------
Linked ids come from catalogue_links.effective_link_ids per record, NOT a raw
union of every datasheet_links entry. So a datasheet counts as linked here
exactly when catalogue_payload would render it linked: resolution-pinned ids win
on link_datasheet records, and no_current_datasheet records contribute nothing.
This is stricter than the old raw union and moves the gap numbers; the baseline
is therefore generated after this lands.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import Counter
from difflib import SequenceMatcher

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
sys.path.insert(0, BASE)

import catalogue_id_locations as R  # noqa: E402
import catalogue_links as cl  # noqa: E402

MANUAL_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
RES_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
GAPS_JSON = os.path.join(DATA_DIR, "datasheet_gaps.json")
GAPS_CSV = os.path.join(DATA_DIR, "datasheet_gaps.csv")
BASELINE_PATH = os.path.join(DATA_DIR, "datasheet_gaps_baseline.json")
COLLECTION_DB = os.environ.get("COLLECTION_DB_PATH", os.path.join(BASE, "collection.db"))
W40K_DB = os.environ.get("W40K_DB_PATH", os.path.join(DATA_DIR, "w40k", "w40k.db"))
LEGACY_NAMES_PATH = os.path.join(DATA_DIR, "legacy_datasheet_names.json")
LEGACY_NAMES_ARCHIVE = os.path.join(BASE, "archive", "data", "legacy_datasheet_names.json")


def _load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


# ---------------------------------------------------------------------------
# Name normalisation (unchanged from the Wahapedia-era tool; domain-tuned).
def normalise(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("’", "'").replace("�", "")
    text = text.replace("t'au", "tau").replace("t’au", "tau")
    import re
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(primaris|adeptus|astra|space marine|space marines)\b", " ", text)
    text = re.sub(r"\bof\s+(?:slaanesh|khorne|nurgle|tzeentch|chaos)\b", " ", text)
    text = text.replace("hellbane", "helbane")
    text = re.sub(r"\bsorcerer lord\b", "sorcerer", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    _no_strip_s = {"chaos", "bonus", "nexus", "virus", "status", "focus", "class"}
    drop = {"a", "an", "and", "kit", "model", "models", "of", "or", "set", "the", "with"}
    words = []
    for word in text.split():
        if word in drop:
            continue
        if len(word) > 3 and word.endswith("s") and word not in _no_strip_s:
            word = word[:-1]
        words.append(word)
    return " ".join(words)


# ---------------------------------------------------------------------------
# Linked-id set: per-record effective union via the shared resolver.
def _resolution_map():
    doc = _load_json(RES_PATH, {"resolutions": []})
    return {r.get("catalogue_model_id"): r for r in doc.get("resolutions", [])}


def effective_linked_ids() -> set:
    linked = set()
    catalogue = _load_json(MANUAL_PATH, {"model_releases": []})
    resolutions = _resolution_map()
    for record in catalogue.get("model_releases", []):
        resolution = resolutions.get(record.get("id"), {})
        if cl.is_render_excluded(resolution):
            continue
        for did in cl.effective_link_ids(record, resolution):
            if did:
                linked.add(did)
    return linked


# ---------------------------------------------------------------------------
# Coverage gaps (check B).
def _model_release_index(catalogue, resolutions):
    """Index non-excluded model releases by normalised name (for suggesting a
    home for a gap). Excluded / accessory / box-product records are skipped so
    they are never proposed as a link target."""
    index = {}
    for record in catalogue.get("model_releases", []):
        if cl.is_render_excluded(resolutions.get(record.get("id"), {})):
            continue
        key = normalise(record.get("name", ""))
        if key:
            index.setdefault(key, []).append(record)
    return index


def find_cross_faction_candidates(ds_name, ds_scope, release_index, store):
    """Candidate releases (in a different army than ds_scope) with a matching
    name. ds_scope is the datasheet's parent-collapsed faction, so a Blood Angels
    release is not proposed as cross-faction for an Adeptus Astartes datasheet."""
    target = normalise(ds_name)
    if not target:
        return []
    target_tokens = set(target.split())
    candidates = []
    for key, releases in release_index.items():
        key_tokens = set(key.split())
        exact = target == key
        dice = (2 * len(target_tokens & key_tokens) / (len(target_tokens) + len(key_tokens))
                if target_tokens and key_tokens else 0)
        fuzzy = SequenceMatcher(None, target, key).ratio()
        if exact:
            confidence, method = 1.0, "exact"
        elif dice >= 0.72:
            confidence, method = round(dice, 3), "token"
        elif fuzzy >= 0.82:
            confidence, method = round(fuzzy, 3), "fuzzy"
        else:
            continue
        for release in releases:
            if store.faction_parent(release.get("faction_id", "")) == ds_scope:
                continue  # same army, already covered
            candidates.append({
                "catalogue_model_id": release.get("id"),
                "release_name": release.get("name"),
                "release_faction_id": release.get("faction_id"),
                "release_date": release.get("release_date", ""),
                "confidence": confidence,
                "match_method": method,
            })
    candidates.sort(key=lambda c: -c["confidence"])
    return candidates[:4]


def classify_gap(candidates) -> str:
    if not candidates:
        return "genuinely_missing"
    if candidates[0]["confidence"] >= 0.86:
        return "cross_faction_shared"
    return "needs_review"


def compute_coverage_gaps(store):
    linked = effective_linked_ids()
    catalogue = _load_json(MANUAL_PATH, {"model_releases": []})
    resolutions = _resolution_map()
    release_index = _model_release_index(catalogue, resolutions)

    gaps = []
    for ds in store.datasheets:
        did = ds["id"]
        if did in linked:
            continue
        fid = ds.get("faction_id", "")
        scope = store.faction_parent(fid)
        fac_row = store.faction_by_id.get(fid, {})
        candidates = find_cross_faction_candidates(ds["name"], scope, release_index, store)
        gaps.append({
            "datasheet_id": did,
            "datasheet_name": ds["name"],
            "faction_id": fid,
            "faction_name": fac_row.get("display_name") or fac_row.get("name", fid),
            "role": ds.get("role", ""),
            "is_legend": bool(ds.get("is_legends_bool")),
            "gap_type": classify_gap(candidates),
            "candidates": candidates,
        })

    gaps.sort(key=lambda g: (g["gap_type"], g["faction_name"], g["datasheet_name"]))
    summary = {
        "unlinked_datasheet_count": len(gaps),
        "by_type": dict(Counter(g["gap_type"] for g in gaps)),
        "by_faction": dict(Counter(g["faction_name"] for g in gaps).most_common()),
        "legends_in_gaps": sum(1 for g in gaps if g["is_legend"]),
    }
    return {"schema_version": 2, "summary": summary, "gaps": gaps}


def _write_coverage(report):
    tmp = GAPS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, GAPS_JSON)

    fields = ["gap_type", "datasheet_id", "datasheet_name", "faction_name", "role",
              "is_legend", "candidate_1_name", "candidate_1_faction", "candidate_1_confidence"]
    with open(GAPS_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for g in report["gaps"]:
            row = {k: g.get(k) for k in fields if k in g}
            if g["candidates"]:
                c = g["candidates"][0]
                row["candidate_1_name"] = c["release_name"]
                row["candidate_1_faction"] = c["release_faction_id"]
                row["candidate_1_confidence"] = c["confidence"]
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Dangling-reference walk (checks A / --report).
def _valid_id_sets():
    conn = sqlite3.connect(f"file:{W40K_DB}?mode=ro&immutable=1", uri=True)
    valid_ds = {r[0] for r in conn.execute("SELECT id FROM datasheet")}
    valid_fac = {r[0] for r in conn.execute("SELECT id FROM faction")}
    conn.close()
    man = _load_json(MANUAL_PATH, {"model_releases": []})
    valid_md = {r.get("id") for r in man.get("model_releases", []) if r.get("id")}
    return valid_ds, valid_fac, valid_md


def _classify_value(value, id_type, valid):
    """None if the id resolves, else a short reason. Value shape wins over the
    location's declared id_type, so a cat:/MD value in a datasheet column routes
    to the catalogue (this retires the cat:MD-50979 false positive)."""
    valid_ds, valid_fac, valid_md = valid
    if value in (None, ""):
        return None
    if R.is_cat_id(value) or R.is_md_id(value):
        return None if R.cat_to_md(value) in valid_md else "unknown catalogue model id"
    if id_type == R.FACTION_UUID:
        if R.is_faction_sentinel(value):
            return None  # intentional placeholder, not a dangling ref
        return None if value in valid_fac else "unknown faction id"
    if id_type == R.CATALOGUE_MODEL_ID:
        return None if value in valid_md else "unknown catalogue model id"
    if id_type == R.DATASHEET_UUID:
        return None if value in valid_ds else "unknown datasheet id"
    # detachment_uuid / weapon_uuid: no validator yet, treat as resolving.
    return None


def _legacy_names():
    """{legacy_id: name} bridge, preferring data/ then archive/data/."""
    for path in (LEGACY_NAMES_PATH, LEGACY_NAMES_ARCHIVE):
        doc = _load_json(path, None)
        if doc:
            return doc.get("datasheet_names", {})
    return {}


def walk_dangling(valid, *, include_derived):
    """Yield dict rows for every stored user-data id that does not resolve.

    Each row: location label, kind, table/column or json path, the dead value,
    reason, and a row locator (sqlite rowid, or json index trail) for the
    remediation script. include_derived adds the non-blocking derived locations
    (e.g. photos.datasheet_id) so the worklist matches the live table.
    """
    rows = []
    authorities = {R.USER_DATA} | ({R.DERIVED} if include_derived else set())

    conn = sqlite3.connect(COLLECTION_DB)
    try:
        for loc in R.LOCATIONS:
            if loc.authority not in authorities:
                continue
            if loc.kind == "sqlite":
                try:
                    cur = conn.execute(f"SELECT rowid, {loc.column} FROM {loc.table}")
                except sqlite3.OperationalError:
                    continue
                for rowid, value in cur.fetchall():
                    reason = _classify_value(value, loc.id_type, valid)
                    if reason:
                        rows.append({"location": loc.label, "authority": loc.authority,
                                     "kind": "sqlite", "table": loc.table,
                                     "column": loc.column, "rowid": rowid,
                                     "value": value, "reason": reason})
            else:  # json
                doc = _load_json(loc.path, None)
                if not doc:
                    continue
                for _container, key, value in R.walk_json(doc, loc.accessor):
                    reason = _classify_value(value, loc.id_type, valid)
                    if reason:
                        rows.append({"location": loc.label, "authority": loc.authority,
                                     "kind": "json", "path": loc.path,
                                     "key": key, "value": value, "reason": reason})
    finally:
        conn.close()
    return rows


# ---------------------------------------------------------------------------
# Commands.
def cmd_coverage(store):
    report = compute_coverage_gaps(store)
    _write_coverage(report)
    s = report["summary"]
    print(f"Unlinked datasheets: {s['unlinked_datasheet_count']} "
          f"(Legends: {s['legends_in_gaps']})")
    print(f"By type: {s['by_type']}")
    print("Top factions with gaps:")
    for name, count in list(s["by_faction"].items())[:10]:
        print(f"  {name}: {count}")
    print(f"Wrote {GAPS_JSON}")
    print(f"Wrote {GAPS_CSV}")
    return 0


def cmd_report(store):
    valid = _valid_id_sets()
    legacy = _legacy_names()
    rows = walk_dangling(valid, include_derived=True)

    blocking = [r for r in rows if r["authority"] == R.USER_DATA]
    derived = [r for r in rows if r["authority"] == R.DERIVED]

    def bridgeable(r):
        return bool(legacy.get(r["value"]))

    by_loc = Counter(r["location"] for r in rows)
    print("Dangling references by location (value -> nothing):")
    for loc, count in by_loc.most_common():
        print(f"  {loc:42s} {count}")
    re_resolvable = [r for r in blocking if bridgeable(r)]
    irreducible = [r for r in blocking if not bridgeable(r)]
    print()
    print(f"Blocking (user_data): {len(blocking)}  "
          f"[name-bridgeable: {len(re_resolvable)}, irreducible: {len(irreducible)}]")
    print(f"Derived (non-blocking, e.g. photos): {len(derived)}")
    if irreducible:
        print("\nIrreducible (no legacy name -> quarantine candidates):")
        for r in irreducible:
            print(f"  {r['location']:36s} {r['value']}")
    return 0


def cmd_verify(store, update_baseline=False):
    valid = _valid_id_sets()
    blocking = [r for r in walk_dangling(valid, include_derived=False)]

    coverage = compute_coverage_gaps(store)
    cov_count = coverage["summary"]["unlinked_datasheet_count"]

    if update_baseline:
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"unlinked_datasheet_count": cov_count,
                       "by_type": coverage["summary"]["by_type"]},
                      fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"Wrote baseline -> {BASELINE_PATH} (unlinked={cov_count})")
        return 0

    ok = True
    # Check (A): dangling refs, zero tolerance.
    if blocking:
        ok = False
        print(f"CHECK A FAILED: {len(blocking)} dangling user-data reference(s):")
        for r in blocking[:20]:
            print(f"  {r['location']:36s} {r['value']}  ({r['reason']})")
    else:
        print("CHECK A: 0 dangling user-data references.")

    # Quarantine count, reported separately (known, not silent).
    qcount = _quarantine_count()
    print(f"Quarantined refs (needs review): {qcount}")

    # Check (B): coverage-gap regression vs baseline.
    baseline = _load_json(BASELINE_PATH, None)
    if baseline is None:
        print(f"CHECK B: no baseline at {BASELINE_PATH}; run --update-baseline.")
    else:
        base = baseline.get("unlinked_datasheet_count", 0)
        if cov_count > base:
            ok = False
            print(f"CHECK B FAILED: coverage gaps {cov_count} > baseline {base}.")
        else:
            print(f"CHECK B: coverage gaps {cov_count} <= baseline {base}.")

    return 0 if ok else 1


def _quarantine_count():
    conn = sqlite3.connect(COLLECTION_DB)
    try:
        return conn.execute("SELECT COUNT(*) FROM quarantined_refs").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--report", action="store_true",
                   help="Print the dangling-reference worklist (exit 0).")
    g.add_argument("--verify", action="store_true",
                   help="Gate: exit 1 on any dangling ref or coverage regression.")
    g.add_argument("--update-baseline", action="store_true",
                   help="Regenerate the coverage-gap baseline.")
    args = parser.parse_args()

    from data_store import get_store
    store = get_store()

    if args.report:
        return cmd_report(store)
    if args.verify:
        return cmd_verify(store)
    if args.update_baseline:
        return cmd_verify(store, update_baseline=True)
    return cmd_coverage(store)


if __name__ == "__main__":
    raise SystemExit(main())
