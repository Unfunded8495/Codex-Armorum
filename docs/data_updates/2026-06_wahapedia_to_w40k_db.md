# Ruleset source: Wahapedia to the official app database (data_version 886)

Date: 2026-06
Kind: migration
Versions: none -> 886
Summary: Rules data moved to a read-only SQLite export of the official Warhammer 40,000 app. UUID ids, chapters as first-class factions, MFM overlay retired.

The Wahapedia CSV import (`catalogue_*` tables) and the Munitorum Field
Manual points overlay (`mfm_*` tables) were replaced by `data/w40k/w40k.db`,
a read-only SQLite export of the official Warhammer 40,000 mobile app's own
rules database, produced from the user's copy of the app's `base.apk` by
`scripts/w40k_exporter/w40k_exporter.py`. First adopted snapshot:
`data_version: 886`.

## Why

Wahapedia was a scrape of a third-party site; the app export is a clean
licensed source. The app carries current points directly, so the MFM
overlay's reason to exist disappeared with it.

## What changed

- **Identity system**: faction and datasheet ids switched from Wahapedia
  short codes and 9-digit ids to lowercase hex UUIDs. Legacy 9-digit ids are
  dead; any still found in user data are stale data to fix.
- **Chapters became first-class factions**: Adeptus Astartes is a parent
  faction with Blood Angels, Dark Angels, Space Wolves and the rest as
  children via `faction.parent_faction`. The load-time chapter rollup was
  removed.
- **User data rewritten in place** by `scripts/migrate_to_app40k.py`
  (idempotent, dry-run first, backup kept as `collection.db.pre-app40k`).
  The `bsdata_id` / `unit_bsdata_id` column names were kept as a legacy
  misnomer and now hold UUIDs.
- **Wahapedia CSVs archived** under `archive/data/wahapedia-2026-06/`; the
  `catalogue_*` and `mfm_*` tables were dropped by
  `scripts/cleanup_post_app40k.py`.
- `virtual_bool` is forced False for every datasheet; the new export has no
  equivalent semantic (accepted behavioural change).
