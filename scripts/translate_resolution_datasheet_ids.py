"""Translate model_catalogue_resolutions.json datasheet_ids to w40k.db UUIDs.

The original w40k.db migration translated `datasheet_id` inside the manual
catalogue's nested `datasheet_links`, but never touched
`model_catalogue_resolutions.json`. Every linkable resolution row still
carries legacy 9-digit Wahapedia ids in its `datasheet_ids` list, so the
catalogue payload's link resolver drops them as unknown and a
resolution-overridden multi-faction model (e.g. Rhino, Chaos Spawn) ends up
in only its stored top-level faction's filter bucket. This script closes
that gap.

The translation is mechanical: each manual.json nested link carries its
original 9-digit id in `_legacy_id` alongside the new UUID, so we build a
catalogue-model-scoped {legacy_id: uuid} map and apply it to the matching
resolution's `datasheet_ids`. Per-model scoping matters because the same
legacy id can be reused across catalogue rows and we only ever want the
mapping a specific model's own audit trail records.

Outputs
-------
- Backup: data/model_catalogue_resolutions.json.pre-ds-translate (only
  written on the first apply; never overwritten).
- Report: data/catalogue_resolution_translate_report.json with counts and
  the list of dead rows (legacy ids the manual record's audit trail did
  not cover).

Idempotency
-----------
Re-running on an already-translated file (no linkable resolution carries a
legacy 9-digit datasheet_id) aborts before any write.

--dry-run runs the translation in memory and writes the report only.
"""
import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES_PATH = os.path.join(ROOT, "data", "model_catalogue_resolutions.json")
MAN_PATH = os.path.join(ROOT, "data", "model_catalogue_manual.json")
BACKUP_PATH = RES_PATH + ".pre-ds-translate"
REPORT_PATH = os.path.join(ROOT, "data", "catalogue_resolution_translate_report.json")


def _looks_uuid(v):
    return isinstance(v, str) and len(v) == 36 and v.count("-") == 4


def _looks_legacy(v):
    return isinstance(v, str) and v.isdigit() and len(v) >= 7


def _legacy_map_for_record(record):
    """Return {legacy_9digit_id: uuid} from the record's nested links'
    _legacy_id audit trail. The migration script wrote _legacy_id alongside
    every translated datasheet_id."""
    out = {}
    for link in record.get("datasheet_links", []):
        legacy = link.get("_legacy_id")
        new = link.get("datasheet_id")
        if legacy and new and _looks_uuid(new):
            out[legacy] = new
    return out


def _is_idempotent(resolutions):
    for row in resolutions.get("resolutions", []):
        if row.get("action") not in ("link_datasheet", "link_multiple_datasheets"):
            continue
        for did in row.get("datasheet_ids", []) or []:
            if _looks_legacy(did):
                return False
    return True


def translate(resolutions, manual):
    records_by_id = {r["id"]: r for r in manual.get("model_releases", [])}
    fully_translated = []
    partially_translated = []
    fully_dead = []
    non_linkable = 0

    for row in resolutions.get("resolutions", []):
        if row.get("action") not in ("link_datasheet", "link_multiple_datasheets"):
            non_linkable += 1
            continue
        cid = row.get("catalogue_model_id")
        record = records_by_id.get(cid, {})
        legacy_map = _legacy_map_for_record(record)
        original = list(row.get("datasheet_ids", []) or [])
        new_ids = []
        misses = []
        for did in original:
            if _looks_legacy(did):
                mapped = legacy_map.get(did)
                if mapped:
                    new_ids.append(mapped)
                else:
                    misses.append(did)
            else:
                new_ids.append(did)
        row["datasheet_ids"] = new_ids

        summary = {
            "id": cid,
            "name": (record.get("name") if record else None),
            "original": original,
            "translated": new_ids,
            "dropped_legacy_ids": misses,
        }
        if not misses:
            fully_translated.append(summary)
        elif new_ids:
            partially_translated.append(summary)
        else:
            fully_dead.append(summary)

    report = {
        "summary": {
            "linkable_rows": len(fully_translated) + len(partially_translated) + len(fully_dead),
            "fully_translated": len(fully_translated),
            "partially_translated": len(partially_translated),
            "fully_dead": len(fully_dead),
            "non_linkable_rows": non_linkable,
        },
        "partially_translated": partially_translated,
        "fully_dead": fully_dead,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(RES_PATH, encoding="utf-8") as fh:
        resolutions = json.load(fh)
    with open(MAN_PATH, encoding="utf-8") as fh:
        manual = json.load(fh)

    if _is_idempotent(resolutions):
        print("model_catalogue_resolutions.json already holds translated "
              "datasheet ids (no legacy 9-digit ids on any linkable row). "
              "Nothing to do.")
        return 0

    report = translate(resolutions, manual)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    s = report["summary"]
    print(f"Report -> {REPORT_PATH}")
    print(f"  linkable rows         {s['linkable_rows']}")
    print(f"  fully translated      {s['fully_translated']}")
    print(f"  partially translated  {s['partially_translated']}")
    print(f"  fully dead            {s['fully_dead']}")

    if args.dry_run:
        print("Dry-run complete; resolutions file untouched.")
        return 0

    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(RES_PATH, BACKUP_PATH)
        print(f"Backup -> {BACKUP_PATH}")
    else:
        print(f"Backup already exists at {BACKUP_PATH}; keeping it.")

    tmp = RES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(resolutions, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, RES_PATH)
    print(f"Rewrote {RES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
