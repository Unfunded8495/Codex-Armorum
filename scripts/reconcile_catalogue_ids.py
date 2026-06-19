"""One-time migration: remap the BSData ids that remain in the model-catalogue
JSON layer onto native Wahapedia ids.

The catalogue tables were migrated to Wahapedia (wahapedia_importer.py), but the
model-catalogue JSON layer still referenced BSData ids in three places. This
script repairs all three:

  1. data/model_catalogue_resolutions.json: datasheet_ids that are BSData GUIDs
     are remapped to Wahapedia datasheet ids. The GUID is resolved to a name via
     data/legacy_datasheet_names.json, then matched against the live store by
     name (Unicode-normalised). Ambiguous names (one name, several factions) are
     disambiguated by the catalogue model's own faction_label.
  2. data/model_catalogue_manual.json: each model_release faction_id (a BSData
     faction GUID) is replaced with the Wahapedia faction code derived from the
     record's faction_label.
  3. collection.db: any minis row whose datasheet_id is still a BSData GUID is
     remapped the same way (datasheet_id and unit_bsdata_id both updated).

Anything that cannot be resolved with confidence is left untouched and listed in
the report (Forge World / Legends units Wahapedia does not carry, etc.).

Usage (from repo root):
    python scripts/reconcile_catalogue_ids.py          # dry run, report only
    python scripts/reconcile_catalogue_ids.py --apply   # write changes
"""
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import data_store  # noqa: E402
from catalogue_review import canonical_faction_label  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
RES_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
MAN_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
LEGACY_PATH = os.path.join(DATA_DIR, "legacy_datasheet_names.json")
DB_PATH = os.path.join(ROOT, "collection.db")

# Sub-factions and prefixed labels that do not map 1:1 onto a Wahapedia faction
# name. Wahapedia collapses Space Marine chapters into SM and the Aeldari and
# Imperial Agents trees into single codes; the catalogue keeps the finer
# faction_label for its cards, but faction_id must be a real Wahapedia code.
SUBFACTION_TO_CODE = {
    "blood angels": "SM",
    "dark angels": "SM",
    "space wolves": "SM",
    "deathwatch": "SM",
    "supplement marines": "SM",
    "black templars": "SM",
    "craftworlds": "AE",
    "harlequins": "AE",
    "ynnari": "AE",
    "inquisition": "AoI",
    "imperial assassins": "AoI",
    "agents of the imperium": "AoI",
    "tau empire": "TAU",
}

GUID_RE = re.compile(r"^[0-9a-f]{2,4}-[0-9a-f]{2,4}-[0-9a-f]{2,4}-[0-9a-f]{2,4}$")


def norm(s):
    """Normalise a unit name for matching: unify apostrophes and dashes, drop a
    trailing [Legends] tag, collapse whitespace, casefold."""
    if not s:
        return ""
    for ch in ("’", "‘", "ʼ", "´", "`"):
        s = s.replace(ch, "'")
    for ch in ("–", "—", "−"):
        s = s.replace(ch, "-")
    s = re.sub(r"\s*\[legends\]\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def is_guid(value):
    return isinstance(value, str) and bool(GUID_RE.match(value))


def build_indexes(store):
    name_to_ids = {}
    for did, u in store.ds_by_id.items():
        name_to_ids.setdefault(norm(u["name"]), []).append(did)
    fac_name_to_code = {}
    for f in store.factions:
        fac_name_to_code[norm(f["name"])] = f["id"]
    return name_to_ids, fac_name_to_code


def label_to_code(label, fac_name_to_code):
    """Map a catalogue faction_label to a Wahapedia faction code, or None."""
    canon = canonical_faction_label(label or "")
    seg = canon.split(" - ")[-1].strip()  # "Xenos - Orks" -> "Orks"
    key = norm(seg)
    if key in SUBFACTION_TO_CODE:
        return SUBFACTION_TO_CODE[key]
    if key in fac_name_to_code:
        return fac_name_to_code[key]
    return None


def resolve_name(name, name_to_ids, prefer_code=None):
    """Return (wahapedia_id, status). status: clean | disambiguated | ambiguous |
    nomatch."""
    ids = name_to_ids.get(norm(name), [])
    if not ids:
        return None, "nomatch"
    if len(ids) == 1:
        return ids[0], "clean"
    if prefer_code:
        matches = [i for i in ids
                   if data_store.get_store().ds_by_id[i]["faction_id"] == prefer_code]
        if len(matches) == 1:
            return matches[0], "disambiguated"
    return None, "ambiguous"


def main(apply):
    store = data_store.get_store()
    name_to_ids, fac_name_to_code = build_indexes(store)
    legacy = json.load(open(LEGACY_PATH, encoding="utf-8")).get("datasheet_names", {})

    man = json.load(open(MAN_PATH, encoding="utf-8"))
    releases = man.get("model_releases", [])
    # cmid -> faction code (for resolution disambiguation) and cmid -> model name
    # (fallback when a GUID is missing from the legacy-name bridge).
    cmid_code = {}
    cmid_name = {}
    for r in releases:
        cmid_code[r.get("id")] = label_to_code(r.get("faction_label", ""), fac_name_to_code)
        cmid_name[r.get("id")] = r.get("name")

    # ---- Part A: resolution datasheet_ids ----------------------------------
    res = json.load(open(RES_PATH, encoding="utf-8"))
    a_clean = a_disamb = 0
    a_unresolved = []  # (cmid, guid, name, reason)
    for r in res.get("resolutions", []):
        cid = r.get("catalogue_model_id")
        ids = r.get("datasheet_ids") or []
        new_ids = []
        changed = False
        for x in ids:
            if not is_guid(x):
                new_ids.append(x)
                continue
            name = legacy.get(x)
            # Fall back to the catalogue model's own name when the GUID is not in
            # the legacy-name bridge (the model name almost always matches the
            # datasheet it links to, e.g. "Drop Pod").
            fallback = False
            if not name:
                name = cmid_name.get(cid)
                fallback = True
            if not name:
                new_ids.append(x)
                a_unresolved.append((cid, x, None, "no legacy name"))
                continue
            wid, status = resolve_name(name, name_to_ids, cmid_code.get(cid))
            if wid and fallback:
                status = status + " (via model name)"
            if wid:
                new_ids.append(wid)
                changed = True
                if status == "clean":
                    a_clean += 1
                else:
                    a_disamb += 1
            else:
                new_ids.append(x)
                a_unresolved.append((cid, x, name, status))
        if changed:
            r["datasheet_ids"] = new_ids

    # ---- Part B: model_releases faction_id ---------------------------------
    b_mapped = 0
    b_unmapped = {}  # label -> count
    for r in releases:
        fid = r.get("faction_id")
        if not is_guid(fid):
            continue
        code = label_to_code(r.get("faction_label", ""), fac_name_to_code)
        if code:
            r["faction_id"] = code
            b_mapped += 1
        else:
            b_unmapped[r.get("faction_label", "")] = b_unmapped.get(r.get("faction_label", ""), 0) + 1

    # ---- Part C: minis rows with a GUID datasheet_id -----------------------
    c_fixed = []
    c_unresolved = []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, datasheet_id, catalogue_model_id, label FROM minis").fetchall()
    for m in rows:
        did = m["datasheet_id"]
        if not did or did in store.ds_by_id:
            continue
        if not is_guid(did):
            continue
        name = legacy.get(did)
        prefer = cmid_code.get(m["catalogue_model_id"])
        wid, status = (resolve_name(name, name_to_ids, prefer) if name else (None, "no legacy name"))
        if wid:
            c_fixed.append((m["id"], m["label"], did, wid))
            if apply:
                conn.execute("UPDATE minis SET datasheet_id=?, unit_bsdata_id=? WHERE id=?",
                             (wid, wid, m["id"]))
        else:
            c_unresolved.append((m["id"], m["label"], did, name, status))

    # ---- write / report ----------------------------------------------------
    if apply:
        json.dump(res, open(RES_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(man, open(MAN_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        conn.commit()
    conn.close()

    print("=" * 70)
    print("CATALOGUE ID RECONCILIATION", "(APPLIED)" if apply else "(DRY RUN)")
    print("=" * 70)
    print("\n[A] resolutions.json datasheet_ids")
    print(f"    remapped clean (1:1 name)   : {a_clean}")
    print(f"    remapped by faction context : {a_disamb}")
    print(f"    left unresolved             : {len(a_unresolved)}")
    for cid, guid, name, reason in a_unresolved:
        print(f"        - {cid}  {guid}  name={name!r}  ({reason})")
    print("\n[B] manual.json model_releases faction_id")
    print(f"    remapped to Wahapedia code  : {b_mapped}")
    print(f"    left unmapped               : {sum(b_unmapped.values())}")
    for lab, n in sorted(b_unmapped.items()):
        print(f"        - {lab!r}: {n}")
    print("\n[C] minis with BSData GUID datasheet_id")
    print(f"    fixed                       : {len(c_fixed)}")
    for mid, label, old, new in c_fixed:
        print(f"        - {label!r}  {old} -> {new}")
    print(f"    left unresolved             : {len(c_unresolved)}")
    for mid, label, old, name, reason in c_unresolved:
        print(f"        - {label!r}  {old}  name={name!r}  ({reason})")
    if not apply:
        print("\n(dry run: nothing written; re-run with --apply to persist)")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
