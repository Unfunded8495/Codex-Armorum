# Exporter v3: full army-building enforcement data (data_version 886)

Date: 2026-07-03
Kind: tooling
Versions: 886 (same data, full enforcement surface)
Summary: The export gained every army-building enforcement structure the app holds: leader groups, warlord and enhancement flags, gated points tiers, keyword limits. The update runbook and compare tool arrived with it.

Third exporter revision, run against the same `base.apk` (`data_version:
886`). The on-disk `w40k.db` was first verified to reproduce byte-identically
from the APK, then the exporter was extended strictly additively (structural
diff confirmed: every pre-existing table, column and JSON key unchanged).

## New tables

- `datasheet_faction_excluded`: all 23 exclusion rows (22 bar parent-faction
  generics from chapters and cannot be expressed via `datasheet_faction`).
- `leader_group` (1267 rows): bodyguard type (leader/support), required and
  excluded detachment, `requires_all_units_keyword`, keyword-based members.
- `detachment_faction_points_cost`: per-faction detachment-points overrides.
- `keyword_limit_group` and `keyword_limit_group_detachment`: roster keyword
  limits and their detachment gates.
- `keyword_ally_restriction`.

## New columns and JSON keys

- `model`: Warlord and enhancement flags, melee/ranged invulnerable saves.
- `enhancement`: `take_limit`, `counts_toward_limit`, `epic_hero_eligible`,
  `non_character_eligible`, `cannot_be_warlord`, `grants_leader_attachment`.
- `detachment`: `linked_datasheets` (is_warlord, count), `unique_keywords`,
  mandatory and granted warlord miniatures.
- `stratagem`: secondary-effect CP fields.
- `allied_faction`: warlord columns.
- Points tiers carry `required_faction_keyword(_id)s` and
  `required_detachment(_id)s` (gated pricing); `wargear_loadout` gained
  `default_loadout` (per-miniature equipped-with, including counts);
  `conditional_keywords` carry structured `requires`.

## Process tooling added alongside

- `CODEX_ARMORUM_DATA_UPDATE.md`: the top-to-bottom refresh runbook
  (baseline, export to staging, compare, swap, verify, record).
- `scripts/compare_w40k_db.py`: old-vs-new database compare whose report
  sections map one-to-one onto runbook actions.

The army builder was subsequently rebuilt to consume and enforce most of
this data; enforcement status is tracked in
`docs/WARGEAR_REACHABILITY_PLAN.md` and the army-builder parity notes.
