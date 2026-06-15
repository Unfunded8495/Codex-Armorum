# Codex Armorum: Data Architecture and Migration Reference

Last reviewed: June 2026. Update this document whenever data sources, tables, or ID mappings change.

---

## Overview

The app draws from three independent data source tracks. They are not interchangeable and must be treated differently during any migration, deployment, or Docker rebuild.

| Track | Source | Regenerable? | Powers |
|---|---|---|---|
| BSData | GitHub wh40k-10e repo (.cat/.gst XML) | Yes -- run bsdata_importer.py | Unit browser, army builder, Arsenal wargear |
| Wahapedia CSVs | 3 CSV files in data/ | No -- must keep | Detachments, Enhancements, Wahapedia ID bridge |
| Model catalogue | 3 JSON files in data/ | No -- must migrate manually | Purchase browser |

---

## Track 1: BSData GitHub repo (purple)

**Source:** `bsdata/wh40k-10e/` -- cloned from https://github.com/BSData/wh40k-10e

**Importer:** `bsdata_importer.py`
- Drops and repopulates all four `catalogue_*` tables on every run
- Safe to run at any time; no data is permanently lost
- Run after any `git pull` on the bsdata subdir to pick up ruleset updates

**Database tables populated:**

| Table | Content |
|---|---|
| `catalogue_factions` | Faction names and BSData GUIDs |
| `catalogue_units` | Units with stats, abilities, keywords, points, composition, leader targets |
| `catalogue_weapons` | Weapon profiles (ranged and melee) |
| `catalogue_unit_weapons` | Many-to-many link between units and weapons |

**ID format:** GUID hex strings, e.g. `6de-ccee-11b4-be3e`

**Stored in minis as:** `minis.unit_bsdata_id`

**Migration rule:** These tables can be dropped entirely and reimported. No backup needed.

---

## Track 2: Wahapedia CSVs (teal)

**Files (all in `data/`):**

| File | Purpose | Can be deleted? |
|---|---|---|
| `Datasheets.csv` | Name-based Wahapedia ID bridge (see below) | No |
| `Detachments.csv` | Detachment browser -- no BSData equivalent | No |
| `Enhancements.csv` | Enhancement browser -- no BSData equivalent | No |

**Why Datasheets.csv is still required:**

`data_store._build_wahapedia_aliases()` runs at startup and builds a reverse map of Wahapedia 9-digit IDs to BSData unit dicts. This is done in two steps:

1. **Step 1 (highest confidence):** Reads `minis.unit_bsdata_id` for any rows where that column is populated (set during the Phase 3 migration). Uses those as verified exact matches.
2. **Step 2 (fallback):** Walks `Datasheets.csv` and name-matches any remaining Wahapedia IDs to BSData units by unit name.

Without `Datasheets.csv`, step 2 fails silently and any Wahapedia IDs not yet covered by step 1 (i.e. units not in the user's collection) resolve to nothing. This breaks datasheet link resolution in the purchase browser.

**Why Detachments.csv and Enhancements.csv are permanent:**

BSData XML carries no detachment or enhancement data. There is no pathway to replace these files from any other source. They stay forever regardless of how many times BSData is re-imported.

**ID format (Wahapedia):** 9-digit zero-padded numeric strings, e.g. `000002686`

**Stored in minis as:** `minis.datasheet_id` (legacy column, set at time of mini creation)

**Migration rule:** These three CSV files must be copied verbatim into the new `data/` directory on every migration.

---

## Track 3: Model catalogue JSONs (amber)

**Files (all in `data/`):**

| File | Purpose | Can be deleted? |
|---|---|---|
| `model_catalogue_manual.json` | 971 physical model releases -- the primary catalogue the app reads | No |
| `model_catalogue_resolutions.json` | 423 manual review decisions (link_datasheet, exclude, etc.) | No |
| `model_catalogue_images.json` | 330 cached image references for catalogue entries | No |
| `model_catalogue.json` | Original import archive (853 entries from GW Excel spreadsheet) | Advisable to keep |
| `model_catalogue.schema.json` | JSON schema for the above | Advisable to keep |
| `model_catalogue_issues.json` | Import-time issue log | Advisable to keep |
| `model_catalogue_imported_archive.json` | Pre-review import snapshot | Advisable to keep |

**How it works:**

`catalogue_review.py` reads `model_catalogue_manual.json` at startup and builds the purchase browser payload. For each catalogue entry it resolves the `datasheet_links` (which contain Wahapedia 9-digit IDs) by looking them up in `data_store.ds_by_id`. This is why the Wahapedia ID bridge (Track 2) must be working for the purchase browser to show datasheet links correctly.

**ID format (catalogue model):** `MD-` prefixed numeric strings, e.g. `MD-50836`

**Stored in minis as:** `minis.catalogue_model_id`

**Also stored in:** `custom_box_set_contents.catalogue_model_id`

**What these files are NOT:** They are not generated from BSData. They were built from a hand-curated GW model range Excel spreadsheet and enriched over multiple sessions. They are source data, not build artefacts.

**Migration rule:** These files must be explicitly listed in any migration checklist and copied to the new `data/` directory. They cannot be recreated from BSData or from the database.

---

## Three ID systems summary

| ID type | Format | Example | Primary column | Also in |
|---|---|---|---|---|
| Wahapedia ID | 9-digit zero-padded | `000002686` | `minis.datasheet_id` | `custom_box_set_contents.datasheet_id`, `model_catalogue_resolutions.json` datasheet_ids |
| BSData GUID | GUID hex string | `6de-ccee-11b4-be3e` | `minis.unit_bsdata_id` | `catalogue_units.bsdata_id`, `army_units.unit_bsdata_id` |
| Catalogue model ID | MD-NNNNN | `MD-50836` | `minis.catalogue_model_id` | `custom_box_set_contents.catalogue_model_id` |

The Wahapedia-to-BSData bridge is built at runtime by `data_store._build_wahapedia_aliases()` and lives in `data_store.ds_by_id`. It is not persisted to the database; it is rebuilt every startup.

---

## Migration checklist

Run this whenever deploying to a new environment, rebuilding Docker, or branching for major rework.

### Must copy (cannot be regenerated)

- [ ] `data/Datasheets.csv`
- [ ] `data/Detachments.csv`
- [ ] `data/Enhancements.csv`
- [ ] `data/model_catalogue_manual.json`
- [ ] `data/model_catalogue_resolutions.json`
- [ ] `data/model_catalogue_images.json`
- [ ] `data/model_catalogue.json`
- [ ] `data/model_catalogue.schema.json`
- [ ] `data/model_catalogue_issues.json`
- [ ] `data/model_catalogue_imported_archive.json`
- [ ] `data/arsenal_wiki_overrides_full.csv`
- [ ] `data/box_sets.json` (if present)
- [ ] `collection.db` (user data)
- [ ] `uploads/` directory (mini photos)
- [ ] `cache/images/catalogue/` (catalogue images)

### Must regenerate after migration

- [ ] Run `python bsdata_importer.py` to populate `catalogue_*` tables
- [ ] Confirm `catalogue_units` count is non-zero (currently ~1533)
- [ ] Confirm purchase browser loads entries (currently 971 in manual catalogue)

### Safe to drop and rebuild

- `catalogue_factions`, `catalogue_units`, `catalogue_weapons`, `catalogue_unit_weapons` -- all rebuilt by `bsdata_importer.py`
- `__pycache__/` directories -- rebuilt by Python at runtime
- `bsdata/wh40k-10e/` -- re-cloneable from GitHub

---

## Database tables reference

### User data (never drop)

| Table | Description |
|---|---|
| `minis` | Individual model instances in the collection |
| `photos` | Photos linked to minis |
| `purchases` | Purchase log entries |
| `custom_box_sets` | User-defined box sets |
| `custom_box_set_contents` | Contents of each box set |
| `favourite_factions` | Starred factions |
| `army_lists` | Saved army lists |
| `army_units` | Units within army lists |
| `arsenal_weapon` | Wargear entries (Arsenal feature) |
| `arsenal_weapon_datasheet` | Weapon-to-datasheet links |
| `arsenal_weapon_photo` | Photos for Arsenal weapons |

### BSData import tables (safe to drop and rebuild)

| Table | Description |
|---|---|
| `catalogue_factions` | Faction index from BSData |
| `catalogue_units` | Unit definitions from BSData |
| `catalogue_weapons` | Weapon profiles from BSData |
| `catalogue_unit_weapons` | Unit/weapon many-to-many links |

---

## Key files reference

| File | Role | Regenerable? |
|---|---|---|
| `app.py` | Flask routes and API endpoints | Code -- in git |
| `data_store.py` | Loads BSData tables, builds ID bridges, exposes unit/faction data | Code -- in git |
| `bsdata_importer.py` | Parses BSData XML, populates catalogue_* tables | Code -- in git |
| `catalogue_review.py` | Builds purchase browser payload from model_catalogue_manual.json | Code -- in git |
| `box_sets.py` | Box set logic, purchase creation | Code -- in git |
| `db.py` | Schema init and legacy migrations | Code -- in git |
| `collection.db` | SQLite database containing all user data and BSData tables | User data -- back up |
| `data/Datasheets.csv` | Wahapedia datasheet index (ID bridge fallback) | No |
| `data/Detachments.csv` | Detachment definitions (no BSData source) | No |
| `data/Enhancements.csv` | Enhancement definitions (no BSData source) | No |
| `data/model_catalogue_manual.json` | 971-entry physical model range catalogue | No |
| `data/model_catalogue_resolutions.json` | Manual review decisions for catalogue entries | No |
| `data/model_catalogue_images.json` | Catalogue entry image references | No |
| `bsdata/wh40k-10e/` | Cloned BSData ruleset XML | Re-cloneable from GitHub |
