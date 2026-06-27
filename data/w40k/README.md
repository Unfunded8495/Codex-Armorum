# Official Warhammer 40,000 app data export

This directory holds `w40k.db`, the SQLite export of the official Warhammer 40,000
mobile-app rules data. It is the authoritative source for every game-rule fact
the catalogue surfaces (units, weapons, abilities, points, detachments,
enhancements, stratagems).

The current snapshot is `data_version: 886`.

## Why it is here

The previous data source was a scrape of Wahapedia. `w40k.db` is a clean
licensed source the user owns, with first-class chapter factions, structured
wargear loadouts, leader/led-by lists, and current points. It replaces both the
Wahapedia importer and the Munitorum Field Manual (MFM) overlay.

## Why it is not committed

`w40k.db` is a 12 MB binary file refreshed out-of-band. It is listed in the
top-level `.gitignore` and must be present locally for the app to start.

## Refreshing the snapshot

Two options:

1. Drop a newer pre-built `w40k.db` into this directory (`data/w40k/w40k.db`).
2. Run the bundled exporter against a fresh `base.apk`:
   `python scripts/w40k_exporter/w40k_exporter.py`
   then copy the result into `data/w40k/`.

Restart the Flask app after either route.

## Pointing the app at a different DB

The default path is `data/w40k/w40k.db` relative to the project root. Set the
`W40K_DB_PATH` env var to override (useful for CI or dev against a staging
snapshot).

## All path overrides

For testing the migration against a throwaway copy of `collection.db` (or for
CI runs against staging data), four env vars are honoured. Leave them unset for
normal operation; the production defaults are unchanged.

| Env var | Default | Read by |
|---|---|---|
| `W40K_DB_PATH` | `data/w40k/w40k.db` | `data_store.py`, `scripts/migrate_to_app40k.py` |
| `COLLECTION_DB_PATH` | `collection.db` (project root) | `db.py`, `scripts/migrate_to_app40k.py` |
| `MANUAL_JSON_PATH` | `data/model_catalogue_manual.json` | `catalogue_review.py`, `scripts/migrate_to_app40k.py` |
| `MIGRATION_REPORT_PATH` | `data/migration_app40k_report.json` | `scripts/migrate_to_app40k.py` |

Each override is independent. A migration dry-run against a throwaway copy
looks like:

```
COLLECTION_DB_PATH=data/_migration_test/collection.db \
MANUAL_JSON_PATH=data/_migration_test/model_catalogue_manual.json \
MIGRATION_REPORT_PATH=data/_migration_test/migration_app40k_report.json \
  python scripts/migrate_to_app40k.py --dry-run
```

The migration script derives both backup paths (`*.pre-app40k`) from the
live paths above, so the backups land next to the copy, not next to the live
file.
