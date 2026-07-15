# Ruleset source: BSData to Wahapedia

Date: 2026-04
Kind: migration
Summary: Replaced the BSData XML import with the Wahapedia CSV export as the sole ruleset source.

The original ruleset import, the community-maintained BSData `wh40k-10e` XML
files, was replaced by the Wahapedia CSV export as the sole source of
factions, datasheets and rules data.

## What changed

- All rules data (factions, datasheets, weapon profiles, points) now loaded
  from Wahapedia's CSV export into the `catalogue_*` tables.
- Current points came from a separate Munitorum Field Manual overlay
  (`mfm_*` tables) layered over the Wahapedia base data.
- A pre-migration snapshot of user data was kept as
  `collection.db.pre-wahapedia`.

This is the earliest recorded source migration; detail beyond the above was
not captured at the time. Both the BSData and Wahapedia pipelines have since
been retired entirely (see the June 2026 migration to the official app's
database).
