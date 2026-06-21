# Codex Armorum: Data Architecture and Migration Reference

Last reviewed: June 2026 (Wahapedia migration). Update this document whenever data sources, tables, or ID mappings change.

---

## Overview

The app draws from two independent data source tracks. They are not interchangeable and must be treated differently during any migration, deployment, or Docker rebuild.

| Track | Source | Regenerable? | Powers |
|---|---|---|---|
| Wahapedia CSV export | CSV files in `data/` | Yes: re-fetch then re-import | Factions, unit browser, datasheets, weapons, abilities, points, detachments, enhancements, army builder, Arsenal |
| Model catalogue | JSON files in `data/` | No: must migrate manually | Purchase browser, sculpt-aware tracking |

BSData has been fully retired. There is no `bsdata/` repo, no `bsdata_importer.py`, and no runtime Wahapedia-to-BSData alias bridge. Every unit lookup now keys on the native Wahapedia datasheet id.

---

## Track 1: Wahapedia CSV export

**Source:** pipe-delimited CSV files under `data/`, downloaded from `https://wahapedia.ru/wh40k10ed/`.

**Fetcher:** `scripts/fetch_wahapedia.py` downloads the full set (raw bytes, preserving the UTF-8 BOM and pipe delimiter).

**Importer:** `wahapedia_importer.py`
- Drops and repopulates all four `catalogue_*` tables on every run.
- Safe to run at any time; no user data is touched.
- Keys every row on native Wahapedia ids.

**Files used by the importer (all in `data/`):**

```
Factions.csv                     Datasheets_keywords.csv
Datasheets.csv                   Datasheets_abilities.csv
Datasheets_models.csv            Datasheets_leader.csv
Datasheets_wargear.csv           Abilities.csv
Datasheets_options.csv           Detachments.csv
Datasheets_unit_composition.csv  Enhancements.csv
Datasheets_models_cost.csv
```

`Detachments.csv` and `Enhancements.csv` are read directly by `data_store._load_detachment_data()` (the detachment and enhancement browsers). The remaining Wahapedia files (`Source.csv`, `Stratagems.csv`, `Datasheets_stratagems.csv`, etc.) are downloaded for completeness but are not yet consumed.

**Database tables populated:**

| Table | Content |
|---|---|
| `catalogue_factions` | Faction names, keyed by Wahapedia faction code |
| `catalogue_units` | Units with stats, abilities, keywords, points, composition, options, loadout, leader targets, legend, link, virtual flag |
| `catalogue_weapons` | Weapon profiles (ranged and melee), including a `description` column |
| `catalogue_unit_weapons` | Many-to-many link between units and weapons |

**ID formats:**
- Faction id: Wahapedia faction short code, e.g. `CSM`, `SM`, `TYR`.
- Datasheet id: 9-digit zero-padded string, e.g. `000002570`.
- Weapon id: synthetic `datasheet_id:line:line_in_wargear` (Wahapedia weapons are scoped to a datasheet line, not globally unique).

**Migration rule:** these tables can be dropped entirely and reimported. Re-fetch with `scripts/fetch_wahapedia.py`, then run `python wahapedia_importer.py`.

---

## Space Marine chapter rollup

Wahapedia carries one Space Marines faction code, `SM`, holding every chapter (Blood Angels, Dark Angels, Space Wolves, Deathwatch, Black Templars, and the codex chapters). To restore per-chapter browsing and favouriting, `data_store._apply_chapter_rollup()` derives a per-chapter faction card at load time. This is purely load-time and data-driven, so it survives every reimport with no manual step.

- **Detection is data-driven.** Chapters are the faction keywords (`is_faction_keyword=true`, stored on each unit dict with the `Faction: ` prefix) that appear on `SM` datasheets, minus `CHAPTER_KEYWORD_EXCLUDE` (`Adeptus Astartes`, `Imperium`, `Agents of the Imperium`) and minus any keyword that equals a real faction name. A new chapter added by Wahapedia appears automatically. `CHAPTER_ALLOWLIST` (empty by default) can curate the set without touching logic.
- **The importer stays unaware of chapters.** No chapter rows are written to any table. After a reimport, `data_store` rebuilds the chapter cards from whatever keywords the fresh CSVs contain.
- **Chapter ids are stable.** A chapter faction id is `parent::chapter`, e.g. `SM::Blood Angels`. It is deterministic from the keyword text, so favourites (`favourite_factions`), box tags (`custom_box_sets`) and army factions (`army_lists`) that persist a chapter id keep resolving across reimports. The `::` separator cannot occur in a real Wahapedia faction code. Helpers: `faction_parent(fid)`, `is_chapter_faction(fid)`.
- **Assignment.** A datasheet carrying exactly one detected chapter keyword is reassigned to that chapter (its `faction_id` becomes the chapter id); generic datasheets stay under `SM`. `units_for_faction(fid)` is strict (the `SM` card shows generic units only, a chapter card shows its own), while `units_in_faction_tree(fid)` returns the parent plus all chapter children (used by box/army matching) and `unit_in_faction(did, fid)` treats a chapter unit as belonging to both its chapter and the parent.
- **Detachments inherit the parent pool.** Wahapedia codes every chapter detachment under `SM` and gives no field attributing a detachment to a chapter, so a chapter card shows the full Space Marines detachment pool via `detachments_for_faction(fid)` (parent fallback). Enhancements follow their detachment.
- **Icons fall back to the parent.** A chapter card tries its own icon, then the parent Space Marines icon, then the tinted glyph (`app._resolve_faction_icon`). No icon files are invented.
- **The catalogue view groups chapters under the parent.** `catalogue_review.catalogue_payload()` collapses chapter datasheet factions back to `SM` (via `faction_parent`) so the purchase browser grouping and catalogue search scope are unchanged by the rollup.

A load-time assertion warns loudly (without raising) if any of `CORE_EXPECTED_CHAPTERS` (Blood Angels, Dark Angels, Space Wolves, Deathwatch, Black Templars) fails to resolve to a non-empty card, so a Wahapedia keyword restructure surfaces on the next refresh instead of silently re-merging a chapter into Space Marines. The read-only diagnostic `scripts/inspect_chapters.py` re-derives the chapter set from the live CSVs.

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

`catalogue_review.py` reads `model_catalogue_manual.json` and builds the purchase browser payload. For each catalogue entry it resolves the `datasheet_links` (Wahapedia 9-digit ids) by looking them up directly in `data_store.ds_by_id`. Because the store is now Wahapedia-native, these links resolve without any bridge.

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

There is now a single ruleset id system plus the catalogue model id.

| ID type | Format | Example | Primary column | Also in |
|---|---|---|---|---|
| Wahapedia datasheet id | 9-digit zero-padded | `000002570` | `minis.datasheet_id` and `minis.unit_bsdata_id` | `catalogue_units.bsdata_id`, `custom_box_set_contents.datasheet_id`, `arsenal_weapon_datasheet.datasheet_id`, `model_catalogue` `datasheet_links` |
| Wahapedia faction code | short alpha | `CSM` | `catalogue_factions.bsdata_id` | `favourite_factions.faction_id`, `custom_box_sets.faction_id`, `army_lists.faction_id`, `catalogue_units.faction_id` |
| Catalogue model id | MD-NNNNN | `MD-50836` | `minis.catalogue_model_id` | `custom_box_set_contents.catalogue_model_id` |

### Legacy column names

The column names `catalogue_units.bsdata_id`, `minis.unit_bsdata_id`, `army_units.unit_bsdata_id`, and `arsenal_weapon.weapon_bsdata_id` are a deliberate legacy misnomer. They now hold Wahapedia ids, not BSData GUIDs. The names were kept to avoid touching about thirty query sites. After the migration, `minis.datasheet_id` and `minis.unit_bsdata_id` hold the same Wahapedia datasheet id for every row.

A future cosmetic rename (`catalogue_units.bsdata_id` to `datasheet_id`, `minis.unit_bsdata_id` to `canonical_datasheet_id`) is possible but not required.

---

## Refresh procedure

To pull a newer Wahapedia ruleset:

1. `python scripts/fetch_wahapedia.py` (re-downloads the CSVs into `data/`).
2. `python wahapedia_importer.py` (drops and repopulates the four `catalogue_*` tables).

The arsenal weapon catalogue is rebuilt automatically on the next app start (`init_arsenal` calls `sync_datasheets`), preserving user-entered spotting notes and photos.

User data in `minis`, `photos`, `purchases`, box sets, armies, arsenal notes/photos, and the model catalogue JSONs is untouched by a refresh.

---

## Migration checklist

Run this whenever deploying to a new environment, rebuilding Docker, or branching for major rework.

### Must copy (cannot be regenerated)

- [ ] `data/model_catalogue_manual.json`
- [ ] `data/model_catalogue_resolutions.json`
- [ ] `data/model_catalogue_images.json`
- [ ] `data/model_catalogue.json`
- [ ] `data/model_catalogue.schema.json`
- [ ] `data/model_catalogue_issues.json`
- [ ] `data/model_catalogue_imported_archive.json`
- [ ] `data/editions_timeline.json`
- [ ] `data/arsenal_wiki_overrides_full.csv`
- [ ] `collection.db` (user data)
- [ ] `uploads/` directory (mini photos)
- [ ] `cache/images/catalogue/` (catalogue images)

### Regenerable (re-fetch and re-import)

- [ ] Run `python scripts/fetch_wahapedia.py` to download the Wahapedia CSVs into `data/`.
- [ ] Run `python wahapedia_importer.py` to populate the `catalogue_*` tables.
- [ ] Confirm `catalogue_units` count is non-zero (currently ~1712).
- [ ] Confirm purchase browser loads entries.

### Safe to drop and rebuild

- `catalogue_factions`, `catalogue_units`, `catalogue_weapons`, `catalogue_unit_weapons`: all rebuilt by `wahapedia_importer.py`.
- `__pycache__/` directories: rebuilt by Python at runtime.

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

### Wahapedia import tables (safe to drop and rebuild)

| Table | Description |
|---|---|
| `catalogue_factions` | Faction index from Wahapedia |
| `catalogue_units` | Unit definitions from Wahapedia |
| `catalogue_weapons` | Weapon profiles from Wahapedia |
| `catalogue_unit_weapons` | Unit/weapon many-to-many links |

---

## Key files reference

| File | Role | Regenerable? |
|---|---|---|
| `app.py` | Flask routes and API endpoints | Code: in git |
| `data_store.py` | Loads the Wahapedia catalogue tables, exposes unit/faction data | Code: in git |
| `wahapedia_importer.py` | Parses the Wahapedia CSVs, populates catalogue_* tables | Code: in git |
| `scripts/fetch_wahapedia.py` | Downloads the Wahapedia CSV export into `data/` | Code: in git |
| `catalogue_review.py` | Builds purchase browser payload from model_catalogue_manual.json | Code: in git |
| `editions.py` | Loads the edition timeline for the Codex Archive | Code: in git |
| `box_sets.py` | Box set logic, purchase creation | Code: in git |
| `db.py` | Schema init and legacy migrations | Code: in git |
| `collection.db` | SQLite database containing all user data and catalogue tables | User data: back up |
| `data/Datasheets*.csv`, `data/Factions.csv`, `data/Abilities.csv` | Wahapedia ruleset export | Re-fetchable |
| `data/Detachments.csv`, `data/Enhancements.csv` | Detachment and enhancement definitions | Re-fetchable |
| `data/model_catalogue_manual.json` | Physical model range catalogue | No |
| `data/model_catalogue_resolutions.json` | Manual review decisions for catalogue entries | No |
| `data/model_catalogue_images.json` | Catalogue entry image references | No |
| `data/editions_timeline.json` | Hand-curated edition timeline (Codex Archive) | No |

---

## Migration history

The June 2026 migration replaced BSData (GitHub wh40k-10e .cat/.gst XML) with the Wahapedia CSV export as the sole ruleset source. The migration scripts live in `scripts/` (`capture_baseline.py`, `fetch_wahapedia.py`, `reconcile_ids.py`). The pre-migration database snapshot is `collection.db.pre-wahapedia`. The most visible behavioural change: Space Marine chapters (Blood Angels, Space Wolves, Dark Angels, Deathwatch, and others) are no longer separate factions in the source data; Wahapedia groups them all under `Space Marines` (`SM`). Per-chapter browsing and favouriting were then restored on top of that data by the load-time chapter rollup (see "Space Marine chapter rollup" above), which derives chapter cards from the faction keywords without leaving Wahapedia.
