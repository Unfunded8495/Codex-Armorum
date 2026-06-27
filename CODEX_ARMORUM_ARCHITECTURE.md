# Codex Armorum: Data Architecture and Migration Reference

Last reviewed: June 2026 (40k app data swap). Update this document whenever data sources, tables, or ID mappings change.

---

## Overview

The app draws from two independent data source tracks. They are not interchangeable and must be treated differently during any migration, deployment, or Docker rebuild.

| Track | Source | Regenerable? | Powers |
|---|---|---|---|
| Official 40k app export | `data/w40k/w40k.db` (SQLite, read-only) | Yes: drop in a newer DB or run the bundled exporter | Factions, unit browser, datasheets, weapons, abilities, points, detachments, enhancements, army builder, Arsenal |
| Model catalogue | JSON files in `data/` | No: must migrate manually | Purchase browser, sculpt-aware tracking |

Wahapedia and the Munitorum Field Manual (MFM) overlay are retired. Faction and datasheet ids are UUIDs from `w40k.db`. The `bsdata_id` / `unit_bsdata_id` column names on user data are kept as a legacy misnomer and now hold UUIDs.

---

## Track 1: Official 40k app export

**Source:** `data/w40k/w40k.db` - a SQLite export of the official Warhammer 40,000 mobile app's rules database. The current snapshot is `data_version: 886`. The file is git-ignored; refresh procedure is in `data/w40k/README.md`.

**Loader:** `data_store.py`
- Opens the DB with `mode=ro&immutable=1` so the file can be swapped under a running app.
- Path is overridable via the `W40K_DB_PATH` env var.
- Picks a single primary faction per datasheet via the leaf-wins rule (drop any membership that is the parent of another). `PRIMARY_FACTION_OVERRIDES` covers known exceptions.
- Chapters of the Adeptus Astartes are first-class factions in `w40k.db`, linked through `faction.parent_faction`.

**Tables read (all in `w40k.db`):**

```
faction                  ability
datasheet                extra_rule
datasheet_faction        weapon
model                    weapon_profile
detachment               enhancement
detachment_faction       stratagem
detachment_rule
```

**No persistent rules tables.** `w40k.db` is queried directly on app start; nothing in
`collection.db` mirrors it. The cleanup script `scripts/cleanup_post_app40k.py` drops the
retired `catalogue_*` and `mfm_*` tables from existing databases.

**ID formats:**
- Faction id: lowercase hex UUID, e.g. `01623188-9470-4441-96b0-e06eb2572bb5`.
- Datasheet id: lowercase hex UUID, e.g. `864734c9-d6c7-4486-92de-9b8271a6a1e5`.
- Weapon profile id: `weapon_profile.id` (UUID); rendered grouped under `weapon.name`.

**Migration rule:** the rules data is sourced entirely from `data/w40k/w40k.db`. Replace
that file with a newer snapshot (or re-export via the bundled `scripts/w40k_exporter/`)
and restart the app.

---

## Space Marine chapters and other faction trees

Chapters of the Adeptus Astartes are first-class `faction` rows in `w40k.db`, linked to their
parent via `faction.parent_faction`. The same shape applies to other multi-chapter / multi-cult
trees (e.g. Heretic Astartes -> Blood Legions / Plague Legions / ...; Aeldari -> Asuryani /
Harlequins). No chapter rollup or keyword inference runs at load time.

- **Strict roster.** `units_for_faction(fid)` returns only datasheets whose primary faction
  equals `fid`. The Adeptus Astartes card shows generics; the Blood Angels card shows
  Blood-Angels-specific datasheets only.
- **Wider matching.** `units_in_faction_tree(fid)` returns the parent's units plus all children -
  used by box/army matching so a "Space Marines" box accepts Blood Angels units.
- **Army builder.** `selectable_units_for_army(fid)` returns own units plus the parent's
  generics (one level up), so a Blood Angels army can field Tactical Squad. The army builder
  unit picker uses this rather than the strict roster.
- **Membership query.** `unit_in_faction(did, fid)` treats a Blood Angels unit as in both
  Blood Angels and Adeptus Astartes.
- **Detachment inheritance.** A chapter card with no detachments of its own shows the parent's
  full pool via `detachments_for_faction(fid)`. Enhancements follow their detachment.
- **Icons fall back to the parent.** A chapter card tries its own icon, then the parent's,
  then a tinted faction glyph (`app._resolve_faction_icon`).
- **Catalogue grouping.** `catalogue_review.catalogue_payload()` collapses chapter datasheets
  to the parent faction id so the purchase browser groups Space Marine releases under one
  faction header, unchanged by the chapter split.

The primary-faction picker (`_pick_primary_faction`) drops any membership that is the parent
of another in the same set ("leaf wins"), tiebreaking alphabetically. `PRIMARY_FACTION_OVERRIDES`
covers explicit exceptions (currently `Maggot Lords Plague Marines -> Death Guard`, the one
datasheet in `data_version: 886` with no membership row at all).

---

## Track 2: Model catalogue JSONs

**Files (all in `data/`):**

| File | Purpose | Can be deleted? |
|---|---|---|
| `model_catalogue_manual.json` | Physical model releases: the primary catalogue the app reads | No |
| `model_catalogue_resolutions.json` | Manual review decisions (link_datasheet, exclude, etc.) | No |
| `model_catalogue_images.json` | Cached image references for catalogue entries | No |
| `model_catalogue.json` | Original import archive (GW Excel spreadsheet) | Advisable to keep |
| `model_catalogue.schema.json` | JSON schema for the above | Advisable to keep |
| `model_catalogue_issues.json` | Import-time issue log | Advisable to keep |
| `model_catalogue_imported_archive.json` | Pre-review import snapshot | Advisable to keep |

**How it works:**

`catalogue_review.py` reads `model_catalogue_manual.json` and builds the purchase browser payload. For each catalogue entry it resolves the `datasheet_links` (w40k.db UUIDs) by looking them up directly in `data_store.ds_by_id`. The migration script (`scripts/migrate_to_app40k.py`) rewrites these from the legacy Wahapedia 9-digit ids on a one-time pass.

**ID format (catalogue model):** `MD-` prefixed numeric strings, e.g. `MD-50836`.

**Stored in minis as:** `minis.catalogue_model_id`. Also in `custom_box_set_contents.catalogue_model_id`.

**What these files are NOT:** they are not generated from any ruleset source. They were built from a hand-curated GW model range spreadsheet and enriched over multiple sessions. They are source data, not build artefacts.

**Migration rule:** these files must be explicitly listed in any migration checklist and copied to the new `data/` directory.

---

## Track 2b: Edition timeline

**File:** `data/editions_timeline.json` (loaded by `editions.py`, served at `GET /api/editions`).

The hand-curated Warhammer 40,000 edition timeline that powers the **Codex Archive** model browser (`/#/history`, `static/js/history.js`). It is curated source data, treated exactly like the model catalogue JSONs: copied on every migration, never regenerated from any ruleset source. Model releases in `model_catalogue_manual.json` hang off it via their `release_date` / `release_year` against the per-edition era ranges. `editions.py` is a read-once, cache-by-mtime loader; no database table is involved.

**Migration rule:** copy `data/editions_timeline.json` alongside the model catalogue JSONs.

---

## ID system

There is a single ruleset id system (w40k.db UUIDs) plus the catalogue model id.

| ID type | Format | Example | Primary column | Also in |
|---|---|---|---|---|
| w40k.db datasheet UUID | lowercase hex UUID | `864734c9-d6c7-4486-92de-9b8271a6a1e5` | `minis.datasheet_id` and `minis.unit_bsdata_id` | `custom_box_set_contents.datasheet_id`, `arsenal_weapon_datasheet.datasheet_id`, `model_catalogue` `datasheet_links`, `army_units.datasheet_id` |
| w40k.db faction UUID | lowercase hex UUID | `01623188-9470-4441-96b0-e06eb2572bb5` | (none persistent in `collection.db`) | `favourite_factions.faction_id`, `custom_box_sets.faction_id`, `army_lists.faction_id` |
| w40k.db detachment UUID | lowercase hex UUID | `c5a51e2c-...` | (none persistent in `collection.db`) | `army_lists.detachment_id` |
| Catalogue model id | MD-NNNNN | `MD-50836` | `minis.catalogue_model_id` | `custom_box_set_contents.catalogue_model_id` |

### Legacy column names

`minis.unit_bsdata_id`, `army_units.unit_bsdata_id`, and `arsenal_weapon.weapon_bsdata_id`
are a deliberate legacy misnomer kept across the w40k.db swap. They now hold w40k.db UUIDs.
The names were kept to avoid touching about thirty query sites. After migration,
`minis.datasheet_id` and `minis.unit_bsdata_id` hold the same UUID for every row.

A future cosmetic rename (`minis.unit_bsdata_id` to `canonical_datasheet_id`, etc.) is
possible but not required.

---

## Refresh procedure

The rules data is sourced from a single file. To pick up a newer snapshot:

1. Drop a newer pre-built `data/w40k/w40k.db` into place, **or** run
   `python scripts/w40k_exporter/w40k_exporter.py` against a fresh `base.apk` and
   copy the result over.
2. Restart the Flask app.

`data_store` opens `w40k.db` with `mode=ro&immutable=1`, so the file can safely be
replaced under a stopped app. The arsenal weapon catalogue is rebuilt automatically on
the next start (`init_arsenal` calls `sync_datasheets`), preserving user-entered spotting
notes and photos.

User data in `minis`, `photos`, `purchases`, box sets, armies, arsenal notes/photos, and
the model catalogue JSONs is untouched by a refresh.

---

## Migration checklist

Run this whenever deploying to a new environment, rebuilding Docker, or branching for major rework.

### Must copy (cannot be regenerated)

- [ ] `data/model_catalogue_manual.json`
- [ ] `data/model_catalogue_resolutions.json`
- [ ] `data/model_catalogue_images.json`
- [ ] `data/editions_timeline.json`
- [ ] `collection.db` (user data)
- [ ] `uploads/` directory (mini photos)
- [ ] `cache/images/catalogue/` (catalogue images)

### Rules data (drop in or re-export)

- [ ] Place `data/w40k/w40k.db` (a snapshot the user owns; refresh procedure above).
- [ ] Confirm the faction grid loads units and the unit detail pages render points.

### One-time migration from a Wahapedia-era database

If `collection.db` was last touched by the Wahapedia-era app (9-digit datasheet ids,
short-code faction ids), run the migration once before launching the new app:

- [ ] `python scripts/migrate_to_app40k.py --dry-run` and review the JSON report.
- [ ] `python scripts/migrate_to_app40k.py` to perform the rewrite (creates
      `collection.db.pre-app40k` and `data/model_catalogue_manual.json.pre-app40k`).
- [ ] Optionally `python scripts/cleanup_post_app40k.py` to drop the now-unused
      `catalogue_*` and `mfm_*` tables once dogfooding confirms the new world works.

---

## Database tables reference

### User data (never drop)

| Table | Description |
|---|---|
| `minis` | Individual model instances in the collection |
| `photos` | Photos linked to minis |
| `unit_wip`, `unit_wip_photos` | Unit-level work-in-progress notes and photos |
| `purchases` | Purchase log entries |
| `custom_box_sets` | User-defined box sets |
| `custom_box_set_contents` | Contents of each box set |
| `favourite_factions` | Starred factions |
| `army_lists` | Saved army lists |
| `army_units` | Units within army lists |
| `arsenal_weapon` | Wargear entries (Arsenal feature) |
| `arsenal_weapon_datasheet` | Weapon-to-datasheet links |
| `arsenal_weapon_photo` | Photos for Arsenal weapons |

### Rules data (external)

Lives entirely in `data/w40k/w40k.db`. Read by `data_store.py` on app start; never copied
into `collection.db`. Tables read: `faction`, `datasheet`, `datasheet_faction`, `model`,
`ability`, `extra_rule`, `weapon`, `weapon_profile`, `detachment`, `detachment_faction`,
`detachment_rule`, `enhancement`, `stratagem`.

### Retired (dropped by `scripts/cleanup_post_app40k.py`)

`catalogue_factions`, `catalogue_units`, `catalogue_weapons`, `catalogue_unit_weapons`,
`mfm_faction_state`, `mfm_meta`, `mfm_resolved_units`, `mfm_resolved_enhancements`,
`mfm_unmatched`. Held the Wahapedia import and MFM overlay; no longer populated.

---

## Key files reference

| File | Role | Regenerable? |
|---|---|---|
| `app.py` | Flask routes and API endpoints | Code: in git |
| `data_store.py` | Reads `data/w40k/w40k.db`, exposes unit/faction/detachment data | Code: in git |
| `scripts/w40k_exporter/w40k_exporter.py` | Re-exports `w40k.db` from a fresh official-app APK | Code: in git |
| `scripts/migrate_to_app40k.py` | One-time migration from Wahapedia ids to w40k.db UUIDs | Code: in git |
| `scripts/cleanup_post_app40k.py` | Drops retired `catalogue_*` and `mfm_*` tables from `collection.db` | Code: in git |
| `scripts/find_datasheet_gaps.py` | Writes a review report to `data/datasheet_gaps.{json,csv}` | Code: in git |
| `scripts/import_wiki_overrides.py` | Applies reviewed Arsenal wiki controls from a CSV | Code: in git |
| `catalogue_review.py` | Builds purchase browser payload from model_catalogue_manual.json | Code: in git |
| `editions.py` | Loads the edition timeline for the Codex Archive | Code: in git |
| `box_sets.py` | Box set logic, purchase creation | Code: in git |
| `db.py` | User-data schema init and migrations | Code: in git |
| `collection.db` | SQLite database containing all user data | User data: back up |
| `data/w40k/w40k.db` | Official 40k app rules export (UUID ids) | Refresh out-of-band |
| `data/model_catalogue_manual.json` | Physical model range catalogue | No |
| `data/model_catalogue_resolutions.json` | Manual review decisions for catalogue entries | No |
| `data/model_catalogue_images.json` | Catalogue entry image references | No |
| `data/editions_timeline.json` | Hand-curated edition timeline (Codex Archive) | No |

---

## Migration history

- **June 2026 (Wahapedia -> w40k.db).** Rules data moved from the Wahapedia CSV import
  (`catalogue_*` tables) and the Munitorum Field Manual overlay (`mfm_*` tables) to a
  read-only SQLite export of the official Warhammer 40,000 mobile app
  (`data/w40k/w40k.db`, `data_version: 886`). Faction and datasheet ids switched from
  Wahapedia short codes and 9-digit ids to lowercase hex UUIDs; chapters of the Adeptus
  Astartes became first-class factions (no chapter rollup at load time). User data was
  rewritten in place by `scripts/migrate_to_app40k.py` against the
  `collection.db.pre-app40k` backup. Wahapedia CSVs were archived under
  `archive/data/wahapedia-2026-06/`.
- **April 2026 (BSData -> Wahapedia).** Replaced the BSData `wh40k-10e` XML import with
  the Wahapedia CSV export as the sole ruleset source. Pre-migration snapshot kept as
  `collection.db.pre-wahapedia`.
