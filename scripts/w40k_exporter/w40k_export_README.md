# w40k_exporter — official 40k app data export

`w40k_exporter.py` turns your own copy of the official Warhammer 40,000 mobile
app's APK (`base.apk`) into the rules dataset Codex Armorum runs on. It reads
the app's bundled data dump, resolves it to plain English records, and writes
a foldered JSON/CSV tree and/or the relational SQLite database
(`w40k.db`) that `data_store.py` consumes.

## Usage

```powershell
# everything: JSON + CSV faction tree, _reference/ files, manifest, README, and w40k.db
python scripts/w40k_exporter/w40k_exporter.py C:\path\to\base.apk -o C:\w40k_staging --sqlite

# just the database (fastest; still writes manifest + generated README)
python scripts/w40k_exporter/w40k_exporter.py C:\path\to\base.apk -o C:\w40k_staging --only-sqlite

# no arguments -> a small tkinter GUI with the same options
python scripts/w40k_exporter/w40k_exporter.py
```

| Flag | Effect |
|---|---|
| `-o / --output` | Output folder (default `w40k_export`) |
| `--sqlite` | Also build `w40k.db` alongside the JSON/CSV tree |
| `--only-sqlite` | Build only `w40k.db` (skip the JSON/CSV faction folders) |
| `--no-json` / `--no-csv` | Drop one half of the foldered output |

The first line of output is `Data version: NNN` — the snapshot identifier the
official app reports for its data. It is also stored in the db (`meta` table)
and in `manifest.json`.

## What it exports

Everything the app knows, additively richer with each exporter revision:

- **Factions** (chapters/legions as first-class rows via `parent_faction`,
  canonical `name` vs UI `display_name`), army rules, allegiance abilities.
- **Datasheets**: statlines per model, weapons with all profiles, abilities,
  extra rules, damage brackets, keywords (+ conditional keywords with
  structured `requires`), unit-composition points including **gated tiers**
  (`required_detachments` / `required_faction_keywords`), and the structured
  **wargear-loadout enforcement** (options / choose_from / limited_choices /
  all_model_choices, plus each miniature's `default_loadout`).
- **Army-building enforcement**: `leader_group` attachment conditions, model
  Warlord flags, enhancement rule flags (`take_limit`, `epic_hero_eligible`,
  ...), faction-membership exclusions (applied to `datasheet_faction`, raw
  rows kept in `datasheet_faction_excluded`), keyword limit groups, ally
  restrictions, per-faction detachment-points overrides.
- **Detachments** with rules, enhancements (structured eligibility), and
  stratagems; **allied factions** as three queryable tables.
- **Reference data**: keywords, weapon abilities, publications, battle sizes,
  missions (packs, primary/secondary, deployments, layouts, presets, twists),
  FAQs, and the **core rulebook** modelled for a reader
  (`rule_section` / `rule_block` / `rule_reference`, plus FTS tables).

The authoritative description of the *current* export — table by table, with
record counts — is the README the exporter generates into its output folder:
for the live dataset that is [`data/w40k/README.md`](../../data/w40k/README.md)
(committed alongside `manifest.json` and `_reference/`; the `w40k.db` file
itself is gitignored).

## How Codex Armorum uses the output

`data/w40k/` *is* an exporter output folder: `w40k.db` + generated
`README.md` + `manifest.json` + `_reference/`. The Flask app opens the db
read-only (`immutable=1`) on start; nothing is imported into `collection.db`.

To move to a new app data version, do **not** export straight over
`data/w40k/` — export to a staging folder, diff it against the live db with
`scripts/compare_w40k_db.py`, and follow the runbook:
[`CODEX_ARMORUM_DATA_UPDATE.md`](../../CODEX_ARMORUM_DATA_UPDATE.md).

## Notes

- All data is read locally from your own copy of the APK. Artwork referenced
  by image URLs in the source is not downloaded.
- Universal stratagems that belong to no detachment are not duplicated into
  every faction folder.
- Records carrying no faction keyword are filed under an `Unaligned` folder
  rather than dropped.
- If the exporter crashes on a new APK, the app's internal schema changed;
  this script is the contract between the APK and everything downstream and
  must be fixed first.
