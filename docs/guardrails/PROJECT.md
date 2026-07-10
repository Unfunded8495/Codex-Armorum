# PROJECT.md - Codex Armorum specifics (project-owned; kit upgrades never touch this file)

Trigger: starting any task in this repo that touches data files, IDs, the army builder, or the manual-style UI; or you are about to answer a question about how the app is wired.

## PR1. Doc router (read the doc; do not answer from memory)
| You need | Read |
|---|---|
| Request flow, module graph, which JS file owns which page | CODEX_ARMORUM_APP_MAP.md |
| Where data lives, ID systems, what is regenerable vs user data | CODEX_ARMORUM_ARCHITECTURE.md |
| A new official-app data snapshot arrived | CODEX_ARMORUM_DATA_UPDATE.md (follow top to bottom; do not improvise the steps) |
| Run or extend the test suite; UI test ids | tests/README.md, tests/TESTIDS.md |
| How w40k.db is produced from the APK | scripts/w40k_exporter/w40k_export_README.md |
| Continue the wargear-reachability backlog (unreachable legal loadouts) | docs/WARGEAR_REACHABILITY_PLAN.md (live tracker; update it as slices land) |

## PR2. The three ID systems (the number one confusion trap here)
- "Model" means a physical mini in the catalogue, keyed by a slug string. It is NOT a game unit.
- "Datasheet" means a game unit from w40k.db, keyed by a lowercase hex UUID. Legacy 9-digit Wahapedia ids are dead; a one-time migration rewrote them. If you see a 9-digit id in user data, it is stale data to fix, not a format to imitate.
- A mini whose kit has no datasheet uses the synthetic key `cat:<catalogue-id>` (resolver in app.py; search for "cat:"). This convention is not in ARCHITECTURE.md; this line is its documentation.
- Game edition is 40k 11th only. Training-data knowledge of earlier editions is wrong here; verify any rule, points value, or stratagem against w40k.db or data/rules/ before writing it.

## PR3. Mandatory gates (after the left column, run the right column and paste its output)
| After changing | Run |
|---|---|
| Any catalogue JSON in data/, or any migration script | `python scripts/find_datasheet_gaps.py --verify` (locations registry: catalogue_id_locations.py). Broken refs are quarantined, never kept-old. |
| Markdown under data/rules/ | `python scripts/build_rules.py`, then load /rules and check the edited section renders |
| Markdown under data/rules/insights/ | `python scripts/build_insights.py`, then `python scripts/build_rules.py` (commentary source links), then load /rules/insights |
| Army-builder logic (army.py, army_validation.py, data_store.py, static/js/army_builder.js) | `python tests/run_all.py` |
| Any template or JS the browser renders | `python tests/run_all.py --ui` (Playwright; it starts its own isolated app.py and stops it itself, so do not start a server for it) |

Golden-master snapshots in tests/golden/ are generated files (HS3): an intended diff is re-blessed with `python tests/run_all.py --golden-build`, never hand-edited.

## PR4. Data ownership (what you may and may not write to)
- data/w40k/w40k.db is a read-only input. Never modify it; a new version comes from the runbook re-export.
- Catalogue JSON in data/ (model_catalogue_manual.json, resolutions, purchases) is user data, not regenerable (HS2 territory). Bulk edits go in a deferred script per IR9, one file per operation.
- data/rules/ and static/weapon_keywords.json are hand-maintained. In weapon_keywords.json the entry ORDER matters: tooltip texts reference keywords defined earlier. Append-or-insert with care; never sort the file.

## PR5. UI conventions (manual design system)
- Shared skin lives in static/css/manual.css; each page scopes its overrides (body.ab-roster for the roster, `ars-` class prefix for arsenal because `al-` is taken by army-list). Match the scoping pattern of the page you are editing; do not add global selectors.
- Overlays and drawers: z-index must exceed the sticky chrome (60). If an overlay does not appear, check for `hidden` being defeated by a display:flex rule before touching z-index (this exact bug is in git history, commit 4198c37).
- Typography: italics mark flavour text ONLY; hints, descriptions, and summaries stay upright. No em dashes in any output, including UI strings and commits.

## PR6. Session hygiene specific to this repo
- Another Claude session may be running the Flask dev server. Before starting or killing anything on the port, check what is running and never blanket-kill python processes; stop only the server you started.
- After each task that changed files, remind the user to commit. Do not commit yourself unless asked.
