# Codex Armorum: Rules-Data Update Runbook

How to move to a new snapshot of the official Warhammer 40,000 app's data:
re-export, **compare new against old**, swap the file in, and verify nothing
broke. Follow it top to bottom whenever the official app ships an update
(balance dataslate, new codex, points changes, errata).

Companion docs: [`CODEX_ARMORUM_ARCHITECTURE.md`](CODEX_ARMORUM_ARCHITECTURE.md)
(what the data tracks are), [`CODEX_ARMORUM_APP_MAP.md`](CODEX_ARMORUM_APP_MAP.md)
(how the app consumes them).

---

## The model in one paragraph

All rules data lives in one read-only SQLite file, `data/w40k/w40k.db`,
exported from your own copy of the official app's APK by
`scripts/w40k_exporter/w40k_exporter.py`. The Flask app never writes to it, and
nothing in `collection.db` mirrors it - so an update is a **file swap**, not a
database migration. What *can* go wrong is at the joins: your user data
(minis, army lists, catalogue links) stores datasheet/faction UUIDs copied by
value, tooltips and the /rules page are hand-curated against the current
ruleset, and the golden-master tests snapshot current points. The runbook
exists to find those breakpoints *before* you notice them in the UI.

**UUID stability:** ids come from the app's own internal database, so a
datasheet keeps its UUID across data versions. The risk is not renumbering but
**removal** (a unit squatted or moved to Legends leaves your minis pointing at
nothing). The compare tool's "removed" lists are exactly the set to worry
about.

---

## Step 0 - Baseline: prove the current state is clean

Do this *before* touching anything, so post-swap failures are attributable to
the new data and not pre-existing rot.

```powershell
python scripts/find_datasheet_gaps.py --verify   # user-data refs + coverage gate
python tests/run_all.py                          # engine + api + golden + fuzz
```

Both must pass. Then keep the old database for comparison and rollback:

```powershell
copy data\w40k\w40k.db data\w40k\w40k.db.prev
```

(`data/w40k/w40k.db*` is gitignored, so the copy is invisible to git.)

## Step 1 - Get the updated base.apk

Update the official Warhammer 40,000 app on your device, then pull your own
copy of its APK:

```powershell
adb shell pm list packages | findstr -i "warhammer 40"   # find the package id
adb shell pm path <package.id>                           # prints the base.apk path
adb pull <that path> C:\platform-tools\base.apk
```

(Any other way you obtain your own copy of the APK works the same; the
exporter only needs the file. Previous exports used
`C:\platform-tools\base.apk`.)

## Step 2 - Export to a staging folder (never straight over the live db)

```powershell
python scripts/w40k_exporter/w40k_exporter.py C:\path\to\base.apk -o C:\w40k_staging --sqlite
```

- `--sqlite` builds `w40k.db` **plus** the JSON/CSV faction tree, the
  `_reference/` files, `manifest.json`, and a generated `README.md` describing
  the export. Use `--only-sqlite` if you only want the database.
- Run with no arguments to get a small GUI instead.
- The first line of output is `Data version: NNN` - the current live snapshot
  is recorded in `data/w40k/README.md` and in the db's `meta` table.

If the exporter crashes, the app's internal schema has changed in a way the
exporter doesn't understand yet; fix `w40k_exporter.py` first (it is the
contract between the APK and everything downstream).

## Step 3 - Compare new against old

```powershell
python scripts/compare_w40k_db.py data\w40k\w40k.db C:\w40k_staging\w40k.db
python scripts/compare_w40k_db.py data\w40k\w40k.db C:\w40k_staging\w40k.db --full   # untruncated lists
```

The tool is read-only and informational. Walk its report top to bottom; each
section maps to an action:

| Report section | What it means | What to do |
|---|---|---|
| `meta` | data_version bump | Sanity check it went *up*; record the new number in Step 6 |
| `schema` (tables/columns added) | Exporter or app grew new data | Usually additive and safe. New enforcement data is an opportunity: check whether `data_store.py` / the army builder should consume it |
| `schema` (tables/columns **removed**) | Something the app may read is gone | Grep `data_store.py` for the table before swapping; adapt first |
| `row counts` | Volume deltas | Orientation only; large unexplained drops deserve a look |
| `factions` added/removed | New army / squatted army | Removed factions can strand `favourite_factions`, `army_lists.faction_id`, `custom_box_sets.faction_id` - Step 5a catches the damage |
| `datasheets` **removed** | Units gone (squatted / merged) | The critical list. Any minis, army units, or catalogue links pointing at these will dangle - Step 5a is mandatory |
| `datasheets` points changed / renamed | Balance pass | Expect golden-master diffs in Step 5b; nothing else to do |
| `datasheets` rules content changed | Stats/weapons/abilities/wargear/leader data changed | Expect golden diffs; spot-check one changed unit in the UI vs the official app |
| `detachments` / `enhancements` / `stratagems` | Detachment ecosystem changes | Saved army lists referencing a removed detachment/enhancement will show validation errors in the builder (by design, not data loss) |
| `battle sizes` | Points/limit caps changed | Engine invariants + goldens cover it |
| `keywords & weapon abilities` | New/changed weapon keywords | **Sync `static/weapon_keywords.json`** - Step 5c |
| `core rules & FAQs` | Rulebook text changed | **Refresh the /rules source** - Step 5d |

Nothing so far has touched the live app. If the diff looks wrong (e.g. the
export half-failed), stop here and re-export.

## Step 4 - Swap the new data in

1. Stop the Flask app (Seal Vault, or Ctrl+C). `data_store` opens the db
   `immutable=1`, so never swap under a *running* app.
2. Copy the staging export over the live folder - the db plus the generated
   docs, so the committed description tracks the data:

```powershell
copy C:\w40k_staging\w40k.db       data\w40k\w40k.db
copy C:\w40k_staging\README.md     data\w40k\README.md
copy C:\w40k_staging\manifest.json data\w40k\manifest.json
robocopy C:\w40k_staging\_reference data\w40k\_reference /MIR
```

3. Restart: `python app.py`. The Arsenal weapon catalogue rebuilds itself on
   start (`init_arsenal` → `sync_datasheets`), preserving user notes/photos.

## Step 5 - Verify

### 5a. User-data integrity (the dangling-reference gate)

```powershell
python scripts/find_datasheet_gaps.py --verify
```

- **Check A** (zero tolerance): every rules id stored in user data still
  resolves. Fails exactly when Step 3's "removed" lists intersect your
  collection. To fix:
  ```powershell
  python scripts/find_datasheet_gaps.py --report          # the worklist
  python scripts/remediate_dangling_refs.py               # dry run
  python scripts/remediate_dangling_refs.py --apply       # re-key / quarantine
  ```
  Re-keyable rows (unit renamed, same model) are moved to the new UUID;
  irreducible rows are quarantined, never silently deleted.
- **Check B** (coverage): catalogue models whose linked datasheets vanished.
  Review, re-link via the Model Catalogue UI or
  `scripts/reresolve_catalogue_faction.py`, then
  `python scripts/find_datasheet_gaps.py --update-baseline` once the new gap
  set is deliberate.

### 5b. The test suite (points fidelity + behaviour)

```powershell
python tests/run_all.py
```

- **engine_invariants** sweeps every datasheet/faction/battle-size in the *new*
  data - points fidelity, default-loadout legality, enhancement eligibility.
  Failures here mean the new data broke an engine assumption; fix code, not
  data.
- **golden_master** diffs are *expected* - they should correspond one-to-one
  with the points/content changes Step 3 reported. Review, then re-bless:
  ```powershell
  python tests/run_all.py --golden-build
  ```
- **api_roundtrip / fuzz** should stay green regardless of data version.

### 5c. Weapon-keyword tooltips (if Step 3 flagged keywords)

`static/weapon_keywords.json` is the hand-curated tooltip glossary rendered on
datasheets. Add entries for new weapon abilities and update changed rules
text. **Ordering matters**: an entry whose tooltip text mentions another
keyword must appear *after* the entry it references.

### 5d. The /rules page (if Step 3 flagged core-rules text)

The Core Rules page is built from `data/rules/wh40k_core_rules_combined.md`  - 
a hand-merged combination of the app's rules text and the printed rulebook
PDF, not generated directly from `w40k.db`. When the app's rule text changes:

1. Edit the combined markdown (and `data/rules/commentary.md` /
   `flavour.json` if affected) to match the new wording.
2. Rebuild: `python scripts/build_rules.py` → regenerates
   `data/rules/core_rules.json`.
3. Reload `/rules` and spot-check the changed sections.

### 5e. Eyeball it

Open the app and compare against the official app on a phone: the faction
grid loads, a changed datasheet renders its new profile, and a saved army's
points total matches what the official app computes for the same list.

## Step 6 - Commit and record

```powershell
git add data/w40k/README.md data/w40k/manifest.json data/w40k/_reference tests/golden data/datasheet_gaps_baseline.json
git commit -m "Refresh w40k data to data_version NNN"
```

Also, in the same commit or alongside it:

- Add a **Migration history** entry to `CODEX_ARMORUM_ARCHITECTURE.md`
  (date, old → new data_version, anything notable from the compare report).
- Update the data_version mentioned in `README.md` / architecture docs if it
  is stated there.
- Delete `data\w40k\w40k.db.prev` once you are confident (or keep it until
  the next update - it is gitignored either way).

## Rollback

```powershell
# stop the app first
copy data\w40k\w40k.db.prev data\w40k\w40k.db
git checkout -- data/w40k/README.md data/w40k/manifest.json data/w40k/_reference tests/golden
python app.py
```

User data is untouched by a swap in either direction, so rollback is exactly
the reverse file copy. If you already ran `remediate_dangling_refs.py --apply`,
its first-apply backups (`collection.db` + the JSON catalogues, suffixed
`.pre-remediate`) restore the pre-remediation user data.

---

## Quick reference card

```text
0  find_datasheet_gaps --verify  +  tests/run_all.py     (must be green)
   copy w40k.db -> w40k.db.prev
1  adb pull the updated base.apk
2  w40k_exporter.py <apk> -o <staging> --sqlite
3  compare_w40k_db.py  data/w40k/w40k.db  <staging>/w40k.db
4  stop app; copy staging db + README + manifest + _reference over data/w40k/
5  find_datasheet_gaps --verify        (remediate if removed units hit you)
   tests/run_all.py                    (review golden diffs; --golden-build)
   weapon_keywords.json                (if keywords changed)
   data/rules + build_rules.py         (if core rules text changed)
6  commit + migration-history entry in CODEX_ARMORUM_ARCHITECTURE.md
```
