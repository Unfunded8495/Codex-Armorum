"""Drop the now-unused Wahapedia catalogue and MFM tables from collection.db.

Run only after dogfooding confirms the new w40k.db-backed app works as
intended. Until this runs, rollback is "restore collection.db.pre-app40k and
git checkout master".

    python scripts/cleanup_post_app40k.py --dry-run
    python scripts/cleanup_post_app40k.py

The script:
  - DROPs every `catalogue_*` table (catalogue_factions, catalogue_units,
    catalogue_weapons, catalogue_unit_weapons).
  - DROPs every `mfm_*` table (so a future mfm_ schema addition is caught too).
  - VACUUMs the database to reclaim space.

The CREATE statements for these tables have already been removed from db.py in
the same commit that introduced the w40k.db data source.
"""

import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_DB = os.path.join(ROOT, "collection.db")


def _tables_to_drop(conn):
    rows = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
          AND (name LIKE 'catalogue_%' OR name LIKE 'mfm_%')
        ORDER BY name
    """).fetchall()
    return [r[0] for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(COLLECTION_DB):
        print(f"collection.db not found at {COLLECTION_DB}.")
        return 1

    conn = sqlite3.connect(COLLECTION_DB)
    tables = _tables_to_drop(conn)
    if not tables:
        print("No catalogue_* or mfm_* tables present. Nothing to do.")
        conn.close()
        return 0

    print("Tables to drop:")
    for t in tables:
        print(f"  {t}")
    if args.dry_run:
        print("Dry run - no changes written.")
        conn.close()
        return 0

    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
