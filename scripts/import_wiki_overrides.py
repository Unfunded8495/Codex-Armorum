"""Apply manually reviewed Arsenal wiki links from a CSV file.

Expected columns: ``weapon_name``, ``wiki_url``, and ``confidence``.  The
``wiki_title`` and ``notes`` columns are accepted for compatibility with the
review export but are not stored by the current Arsenal schema.
"""
import argparse
import csv
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from arsenal_store import MANUAL_REFERENCE_STATUSES, db, display_name


def import_wiki_overrides(path):
    """Import reviewed wiki controls and return a concise summary."""
    updated = 0
    unmatched = []
    status_counts = {}

    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    with db() as c:
        for row in rows:
            name = display_name(row.get("weapon_name", ""))
            status = (row.get("confidence") or "").strip()
            url = (row.get("wiki_url") or "").strip()
            if not name or status not in MANUAL_REFERENCE_STATUSES:
                unmatched.append(name or row.get("weapon_name", ""))
                continue
            weapon = c.execute(
                "SELECT id FROM arsenal_weapon WHERE lower(name)=lower(?)", (name,)
            ).fetchone()
            if not weapon:
                unmatched.append(name)
                continue
            c.execute(
                "UPDATE arsenal_weapon SET wiki_url=?, wiki_status=? WHERE id=?",
                (url, status, weapon["id"]),
            )
            updated += 1
            status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "updated": updated,
        "unmatched": unmatched,
        "status_counts": status_counts,
        # This importer updates only the two manual wiki-control fields.
        "text_fields_unchanged": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Reviewed wiki override CSV")
    args = parser.parse_args()
    summary = import_wiki_overrides(args.csv_path)
    print(f"Updated: {summary['updated']}")
    print(f"Unmatched: {len(summary['unmatched'])}")
    if summary["unmatched"]:
        print("\n".join(summary["unmatched"]))


if __name__ == "__main__":
    main()
