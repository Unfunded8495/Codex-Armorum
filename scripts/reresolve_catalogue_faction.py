"""Re-resolve every catalogue model's faction from w40k.db as authority.

Background
----------
`data/model_catalogue_manual.json` still carries Wahapedia-era 3-letter
faction codes (ORK, SM, CSM, ...) in every `faction_id` field, both at the
top level and nested inside each `datasheet_links[]` entry. The recent
w40k.db migration translated only `datasheet_id`, never `faction_id`.

This script does not translate the old codes. It makes w40k.db the authority
for a model's faction, in line with the rest of the app, by resolving the
faction from the linked datasheet's primary faction. The legacy code is used
only as a fallback for link-less models.

Authority order (per model, first that resolves wins)
-----------------------------------------------------
1. Has datasheet links -> faction = the linked datasheet's primary faction
   (the leaf-wins primary the app already computes in DataStore._pick_primary_faction).
   The stored legacy code is ignored even if it disagrees.
2. No datasheet links, legacy code maps to a w40k.db faction -> translate
   the code through FACTION_CODE_TO_NAME to the UUID.
3. No datasheet links, code is unmapped (TF, UA, UN, or anything unknown)
   -> assign the placeholder "unresolved" sentinel.

For 1 and 2 the label is the bare faction.name from w40k.db. For 3 it is
"Unresolved". No "Xenos - " / "Imperium - " prefix is baked into the stored
label; grouped display, if wanted, is a render-time concern.

Multi-faction link sets
-----------------------
A model whose links span more than one primary faction has its top-level
faction set to the primary faction of the majority of its links. Ties are
broken by the first link's resolved faction. Every nested link keeps its
own resolved faction even when it differs from the model's top-level
choice. Such models are surfaced in the report so a wrong kitbash tag
cannot hide.

Safety gate
-----------
A "near-tie" multi-faction model is one whose top-level faction was chosen
by a margin of one link over the next alternative, or by the tie-break
rule rather than a clear majority. Those are the only multi-faction rows
where the top-level pick is genuinely uncertain.

The apply path aborts when near-tie or unresolved-placeholder exceeds
HANDFUL. The override flag --accept-near-tie-cosmetic-only bypasses the
near-tie portion of the gate ONLY after a human has confirmed in code
that catalogue filter membership follows the nested links (A1 in the
ticket), making every near-tie pick theme-only because the model still
appears under every faction it links to.

Test-row deletion
-----------------
MD-50942 (Delete Test, faction code TF) is a junk test record. It is
dropped from the catalogue as part of this rewrite and logged in the
report so the deletion is auditable.

Outputs
-------
- Backup: data/model_catalogue_manual.json.pre-faction-reresolve (only
  written on the first apply; never overwritten).
- Report: data/catalogue_faction_reresolve_report.json with counts and
  full row lists for each bucket.
"""
import argparse
import json
import os
import shutil
import sys
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import data_store  # noqa: E402

MANUAL_JSON = os.path.join(ROOT, "data", "model_catalogue_manual.json")
RESOLUTIONS_JSON = os.path.join(ROOT, "data", "model_catalogue_resolutions.json")
BACKUP_PATH = MANUAL_JSON + ".pre-faction-reresolve"
REPORT_PATH = os.path.join(ROOT, "data", "catalogue_faction_reresolve_report.json")

UNRESOLVED_ID = "unresolved"
UNRESOLVED_LABEL = "Unresolved"
HANDFUL = 10

DROP_RECORD_IDS = {"MD-50942"}  # "Delete Test" (faction code TF), confirmed junk.

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
    "TF":  None,
}


def _norm(s):
    if not s:
        return ""
    s = s.replace("’", "'").replace("‘", "'")
    return unicodedata.normalize("NFKD", s).casefold().strip()


def _looks_like_uuid(v):
    return isinstance(v, str) and len(v) == 36 and v.count("-") == 4


def _build_code_to_uuid(store):
    name_to_id = {_norm(f["name"]): f["id"] for f in store.factions}
    out = {}
    unresolved_codes = []
    for code, name in FACTION_CODE_TO_NAME.items():
        if name is None:
            continue
        fid = name_to_id.get(_norm(name))
        if fid:
            out[code] = fid
        else:
            unresolved_codes.append((code, name))
    return out, unresolved_codes


def _resolve_link_faction(link_did, store):
    """Return the link's resolved primary faction UUID, or None if the
    datasheet is missing from w40k.db."""
    ds = store.ds_by_id.get(link_did)
    return ds.get("faction_id") if ds else None


def _majority_pick(per_link_fids):
    """Return (winner_fid, margin) or (None, 0) when no link resolved.

    Margin is the difference between the winning bucket's link count and the
    next bucket's link count, or the winner's own count when it is the only
    bucket. Ties are broken by first-link order; margin in that case is 0."""
    resolved = [f for f in per_link_fids if f]
    if not resolved:
        return None, 0
    counts = Counter(resolved)
    sorted_counts = sorted(counts.values(), reverse=True)
    top_count = sorted_counts[0]
    second_count = sorted_counts[1] if len(sorted_counts) > 1 else 0
    margin = top_count - second_count
    winners = {fid for fid, c in counts.items() if c == top_count}
    if len(winners) == 1:
        return next(iter(winners)), margin
    for fid in resolved:
        if fid in winners:
            return fid, margin
    return resolved[0], margin


def _bare_name(store, fid):
    if fid == UNRESOLVED_ID:
        return UNRESOLVED_LABEL
    f = store.faction_by_id.get(fid)
    return f["name"] if f else fid


def _is_idempotent(data):
    """True when no legacy 3-letter codes remain at any faction_id position."""
    for r in data.get("model_releases", []):
        fid = r.get("faction_id", "") or ""
        if fid and fid != UNRESOLVED_ID and not _looks_like_uuid(fid):
            return False
        for link in r.get("datasheet_links", []):
            lfid = link.get("faction_id", "") or ""
            if lfid and lfid != UNRESOLVED_ID and not _looks_like_uuid(lfid):
                return False
    return True


def _runtime_link_ids(record, resolution):
    """Return the datasheet_id list the catalogue payload will actually use
    at runtime for this record, mirroring catalogue_review.catalogue_payload.

    When a resolution is present the resolution's narrowed datasheet_ids win
    (the user has explicitly pinned the model to those datasheets), otherwise
    the manual record's nested links are used."""
    action = (resolution or {}).get("action", "")
    if action in {"link_datasheet", "link_multiple_datasheets"}:
        return [d for d in (resolution.get("datasheet_ids") or []) if d]
    if action == "no_current_datasheet":
        return []
    return [l["datasheet_id"] for l in record.get("datasheet_links", [])
            if l.get("datasheet_id")]


def resolve(data, store, resolutions_by_id):
    """Pure resolution pass over `data` in place. Returns the report dict.

    Mutates each record's faction_id, faction_label, and every nested
    datasheet_links[].faction_id. Also drops every record id listed in
    DROP_RECORD_IDS from data['model_releases']."""
    code_to_uuid, missing_codes = _build_code_to_uuid(store)

    resolved_by_datasheet = []
    resolved_by_code_fallback = []
    unresolved_placeholder = []
    multi_faction_links = []
    near_tie = []
    code_vs_datasheet_conflict = []
    deleted_records = []

    kept = []
    for r in data.get("model_releases", []):
        cid = r.get("id")
        name = r.get("name", "")
        old_code = r.get("faction_id", "") or ""

        if cid in DROP_RECORD_IDS:
            deleted_records.append({
                "id": cid,
                "name": name,
                "old_code": old_code,
                "reason": "test record dropped per A3",
            })
            continue
        kept.append(r)

        # Always rewrite every nested link's faction_id (the manual.json
        # nested links survive even when a resolution narrows the runtime
        # set; their faction_id field must still be aligned).
        per_nested_fids = []
        nested_details = []
        for link in r.get("datasheet_links", []):
            did = link.get("datasheet_id")
            if not did:
                per_nested_fids.append(None)
                nested_details.append({
                    "datasheet_id": did,
                    "datasheet_name": link.get("datasheet_name", ""),
                    "old_faction_id": link.get("faction_id", ""),
                    "resolved_faction_id": None,
                    "resolved_faction_name": None,
                })
                continue
            nested_fid = _resolve_link_faction(did, store)
            per_nested_fids.append(nested_fid)
            nested_details.append({
                "datasheet_id": did,
                "datasheet_name": link.get("datasheet_name", ""),
                "old_faction_id": link.get("faction_id", ""),
                "resolved_faction_id": nested_fid,
                "resolved_faction_name": _bare_name(store, nested_fid) if nested_fid else None,
            })

        # The top-level pick uses the runtime link set (resolution-narrowed
        # when present) so the stored faction_id agrees with the link set
        # the catalogue payload will actually traverse, not the wider
        # historical kit's variants. This was the source of the MD-50424
        # mismatch where the tile themed off the original 3-link majority
        # but the filter bucket was driven by the resolution's single GK
        # variant.
        runtime_link_ids = _runtime_link_ids(r, resolutions_by_id.get(cid))
        per_link_fids = [_resolve_link_faction(did, store) for did in runtime_link_ids]
        link_details = [{
            "datasheet_id": did,
            "datasheet_name": store.ds_by_id.get(did, {}).get("name", ""),
            "resolved_faction_id": fid,
            "resolved_faction_name": _bare_name(store, fid) if fid else None,
        } for did, fid in zip(runtime_link_ids, per_link_fids)]

        top_fid, margin = _majority_pick(per_link_fids)
        if top_fid:
            bucket = "datasheet"
        elif old_code in code_to_uuid:
            top_fid = code_to_uuid[old_code]
            bucket = "code_fallback"
            margin = 0
        else:
            top_fid = UNRESOLVED_ID
            bucket = "unresolved"
            margin = 0

        top_name = _bare_name(store, top_fid)
        r["faction_id"] = top_fid
        r["faction_label"] = top_name
        for link, nested_fid in zip(r.get("datasheet_links", []), per_nested_fids):
            # Stamp the "unresolved" sentinel onto any nested link whose
            # datasheet_id did not resolve in w40k.db (these are dead links
            # to old 9-digit Wahapedia ids the prior migration could not
            # translate; the legacy code is removed but the row stays put
            # so the audit trail in _legacy_id is preserved).
            link["faction_id"] = nested_fid if nested_fid else UNRESOLVED_ID

        row_summary = {
            "id": cid,
            "name": name,
            "old_code": old_code,
            "resolved_faction_id": top_fid,
            "resolved_faction_label": top_name,
            "links": link_details,
        }

        if bucket == "datasheet":
            resolved_by_datasheet.append(row_summary)
            old_uuid = code_to_uuid.get(old_code)
            if old_uuid and old_uuid != top_fid:
                code_vs_datasheet_conflict.append({
                    "id": cid,
                    "name": name,
                    "old_code": old_code,
                    "code_implied_faction_id": old_uuid,
                    "code_implied_faction_name": _bare_name(store, old_uuid),
                    "datasheet_resolved_faction_id": top_fid,
                    "datasheet_resolved_faction_name": top_name,
                    "links": link_details,
                })
            distinct_link_fids = {fid for fid in per_link_fids if fid}
            if len(distinct_link_fids) > 1:
                multi_row = {
                    "id": cid,
                    "name": name,
                    "top_level_faction_id": top_fid,
                    "top_level_faction_name": top_name,
                    "margin": margin,
                    "link_factions": sorted(distinct_link_fids),
                    "link_faction_names": sorted(
                        _bare_name(store, fid) for fid in distinct_link_fids),
                    "links": link_details,
                }
                multi_faction_links.append(multi_row)
                if margin <= 1:
                    near_tie.append(multi_row)
        elif bucket == "code_fallback":
            resolved_by_code_fallback.append(row_summary)
        else:
            unresolved_placeholder.append(row_summary)

    data["model_releases"] = kept

    report = {
        "summary": {
            "model_count": len(kept),
            "resolved_by_datasheet": len(resolved_by_datasheet),
            "resolved_by_code_fallback": len(resolved_by_code_fallback),
            "unresolved_placeholder": len(unresolved_placeholder),
            "multi_faction_links": len(multi_faction_links),
            "near_tie": len(near_tie),
            "code_vs_datasheet_conflict": len(code_vs_datasheet_conflict),
            "deleted_records": len(deleted_records),
        },
        "missing_faction_code_targets": [
            {"code": c, "expected_w40k_name": n} for c, n in missing_codes
        ],
        "a1_filter_membership": {
            "answer": "nested-links",
            "evidence": [
                "static/js/catalogue-review.js:51 - filter checks "
                "item.army_ids which is built from the nested-link union",
                "app.py:1420-1421 - search API uses army_ids union plus "
                "top-level fallback",
                "box_sets.py:144 and 794-795 - same union pattern",
            ],
            "change_required": False,
            "note": "Top-level faction_id is theme-only; multi-faction "
                    "models appear under every faction they link to via "
                    "the army_ids union.",
        },
        "deleted_records": deleted_records,
        "resolved_by_code_fallback": resolved_by_code_fallback,
        "unresolved_placeholder": unresolved_placeholder,
        "near_tie": near_tie,
        "multi_faction_links": multi_faction_links,
        "code_vs_datasheet_conflict": code_vs_datasheet_conflict,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve and write the report only; do not touch the JSON.")
    parser.add_argument(
        "--accept-near-tie-cosmetic-only", action="store_true",
        help="Bypass the near-tie portion of the safety gate. ONLY valid "
             "after A1 has confirmed in code that catalogue filter "
             "membership follows the nested-link union, which makes every "
             "near-tie top-level pick theme-only. Does not bypass the "
             "unresolved-placeholder portion of the gate.")
    args = parser.parse_args()

    with open(MANUAL_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        with open(RESOLUTIONS_JSON, encoding="utf-8") as fh:
            resolutions_doc = json.load(fh)
    except (OSError, ValueError):
        resolutions_doc = {"resolutions": []}
    resolutions_by_id = {
        r.get("catalogue_model_id"): r
        for r in resolutions_doc.get("resolutions", [])
    }

    if _is_idempotent(data):
        print("model_catalogue_manual.json already holds resolved faction ids "
              "(no legacy codes detected). Nothing to do.")
        return 0

    store = data_store.get_store()
    report = resolve(data, store, resolutions_by_id)

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    s = report["summary"]
    print(f"Report -> {REPORT_PATH}")
    print(f"  models                        {s['model_count']}")
    print(f"  resolved_by_datasheet         {s['resolved_by_datasheet']}")
    print(f"  resolved_by_code_fallback     {s['resolved_by_code_fallback']}")
    print(f"  unresolved_placeholder        {s['unresolved_placeholder']}")
    print(f"  multi_faction_links           {s['multi_faction_links']}")
    print(f"    near_tie (margin <= 1)      {s['near_tie']}")
    print(f"  code_vs_datasheet_conflict    {s['code_vs_datasheet_conflict']}")
    print(f"  deleted_records               {s['deleted_records']}")

    if args.dry_run:
        print("Dry-run complete; JSON untouched.")
        return 0

    unresolved_trip = s["unresolved_placeholder"] > HANDFUL
    near_tie_trip = (s["near_tie"] > HANDFUL
                     and not args.accept_near_tie_cosmetic_only)
    if unresolved_trip or near_tie_trip:
        if unresolved_trip:
            print(f"Safety gate tripped: unresolved_placeholder "
                  f"({s['unresolved_placeholder']}) exceeds HANDFUL "
                  f"({HANDFUL}). Review the report.")
        if near_tie_trip:
            print(f"Safety gate tripped: near_tie ({s['near_tie']}) "
                  f"exceeds HANDFUL ({HANDFUL}). Confirm A1 "
                  f"(nested-link membership) and re-run with "
                  f"--accept-near-tie-cosmetic-only to acknowledge "
                  f"that near-tie picks are cosmetic only.")
        return 2

    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(MANUAL_JSON, BACKUP_PATH)
        print(f"Backup -> {BACKUP_PATH}")
    else:
        print(f"Backup already exists at {BACKUP_PATH}; keeping it.")

    tmp = MANUAL_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, MANUAL_JSON)
    print(f"Rewrote {MANUAL_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
