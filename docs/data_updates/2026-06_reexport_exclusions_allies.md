# Re-export: faction exclusions and allied factions (data_version 886)

Date: 2026-06-28
Kind: tooling
Versions: 886 (same data, better export)
Summary: The exporter learned faction-keyword exclusions (Sir Hekhtur leaves Imperial Knights) and started exporting the allied-faction system.

Second exporter revision, run against the same `base.apk` (`data_version:
886`, so the same underlying app data). Two changes to what the export
captures:

## What changed

- **`datasheet_faction` honours `faction_keyword_excluded_datasheet`**: bad
  memberships the app itself suppresses (such as Sir Hekhtur under Imperial
  Knights) no longer leak into the export. The 1142-datasheet total was
  unchanged; `data_store.py` inherited the correction automatically because
  membership runs only through `datasheet_faction`. A unit left with zero
  memberships is skipped at load unless a `PRIMARY_FACTION_OVERRIDES` rule
  reassigns it.
- **Allied factions exported**: new tables `allied_faction`,
  `allied_faction_host`, `allied_faction_datasheet` (21 / 87 / 320 rows)
  plus `_reference/allied_factions.{json,csv}`. Present but unread by the
  app at the time; the army builder consumes them now.

Because `data_version` did not change, the presence of the allied tables,
not the version number, signals this newer export.
