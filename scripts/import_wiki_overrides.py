"""One-off importer for manual Arsenal wiki link/status overrides."""
from collections import Counter
import csv
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import arsenal_store as store
from db import db


DEFAULT_CSV = os.path.join(ROOT, "data", "arsenal_wiki_overrides_full.csv")
REQUIRED_COLUMNS = {"weapon_name", "wiki_title", "wiki_url", "confidence", "notes"}
LINK_STATUSES = {"verified", "base_fallback"}
EXPECTED_COUNTS = {
    "verified": 67,
    "base_fallback": 143,
    "skip": 79,
    "no_match": 22,
    "needs_check": 1826,
}


def _read_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        rows = [dict(row) for row in reader]
    bad_statuses = sorted({
        (row.get("confidence") or "").strip()
        for row in rows
        if (row.get("confidence") or "").strip() not in store.MANUAL_REFERENCE_STATUSES
    })
    if bad_statuses:
        raise RuntimeError(f"CSV has unknown confidence values: {', '.join(bad_statuses)}")
    return rows


def import_wiki_overrides(csv_path=DEFAULT_CSV):
    rows = _read_rows(csv_path)
    csv_counts = Counter((row.get("confidence") or "").strip() for row in rows)
    updated = 0
    unmatched = []

    with db() as c:
        store.ensure_manual_wiki_schema(c)
        before_text = {
            row["id"]: ((row["spotting_notes"] or ""), (row["source"] or ""))
            for row in c.execute("SELECT id, spotting_notes, source FROM arsenal_weapon").fetchall()
        }
        if not before_text:
            raise RuntimeError("No arsenal_weapon rows found. Run the Arsenal sync before importing overrides.")

        c.execute("UPDATE arsenal_weapon SET wiki_status='', wiki_url=''")
        for row in rows:
            weapon_name = (row.get("weapon_name") or "").strip()
            status = (row.get("confidence") or "").strip()
            wiki_url = (row.get("wiki_url") or "").strip() if status in LINK_STATUSES else ""
            matches = c.execute(
                "SELECT id FROM arsenal_weapon WHERE lower(name)=lower(?)",
                (weapon_name,),
            ).fetchall()
            if not matches:
                unmatched.append(weapon_name)
                continue
            for match in matches:
                c.execute(
                    "UPDATE arsenal_weapon SET wiki_status=?, wiki_url=? WHERE id=?",
                    (status, wiki_url, match["id"]),
                )
                updated += 1

        after_text = {
            row["id"]: ((row["spotting_notes"] or ""), (row["source"] or ""))
            for row in c.execute("SELECT id, spotting_notes, source FROM arsenal_weapon").fetchall()
        }
        status_counts = {
            row["wiki_status"]: row["n"]
            for row in c.execute("""SELECT wiki_status, COUNT(*) n
                                    FROM arsenal_weapon
                                    WHERE COALESCE(wiki_status,'')<>''
                                    GROUP BY wiki_status""").fetchall()
        }

    return {
        "csv_rows": len(rows),
        "csv_counts": dict(sorted(csv_counts.items())),
        "expected_counts": EXPECTED_COUNTS,
        "counts_match_expected": dict(csv_counts) == EXPECTED_COUNTS,
        "updated": updated,
        "unmatched": unmatched,
        "status_counts": status_counts,
        "status_counts_match_expected": status_counts == EXPECTED_COUNTS,
        "text_fields_unchanged": before_text == after_text,
    }


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    summary = import_wiki_overrides(csv_path)
    print(f"CSV rows: {summary['csv_rows']}")
    print(f"Updated weapon rows: {summary['updated']}")
    print(f"CSV status counts: {summary['csv_counts']}")
    print(f"Database status counts: {summary['status_counts']}")
    print(f"Counts match expected: {summary['status_counts_match_expected']}")
    print(f"Descriptions/source unchanged: {summary['text_fields_unchanged']}")
    if summary["unmatched"]:
        print(f"Unmatched weapon names ({len(summary['unmatched'])}):")
        for name in summary["unmatched"]:
            print(f"  {name}")
        raise SystemExit(1)
    if not summary["status_counts_match_expected"] or not summary["text_fields_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
