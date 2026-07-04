# Army-builder test suite

Tests that the army builder agrees with `w40k.db`, behaves deterministically, and
survives a round trip. Standalone scripts (no pytest, no new runtime deps); the
only test-only dependency is Playwright, for the UI layer.

## Run

```
python tests/run_all.py              # engine + api + golden(verify) + fuzz
python tests/run_all.py --ui         # also the browser journeys
python tests/run_all.py --golden-build   # (re)bless golden snapshots, then run
```

Each layer is also runnable on its own, e.g. `python tests/engine_invariants.py`.
A layer prints `ok` / `XX` / `--` lines and exits non-zero on any failure.

## The layers (cheapest and broadest first)

1. **`engine_invariants.py`** -- exhaustive, data-derived, no server. Sweeps every
   datasheet, faction, and battle size: points fidelity (default-size price ==
   `default_points`), default-loadout legality and `points_delta == 0`,
   weapon-array balance, enhancement eligibility (no Epic Hero passes; every
   datasheet-specific group resolves), and picker well-formedness. This is the
   correctness backbone.
2. **`api_roundtrip.py`** -- in-process Flask client on an isolated DB. The
   add-unit guard parity (the chapter add-guard: every picker unit is addable,
   nothing else), server validation codes (duplicate / excludes / allies), and
   export/import idempotence.
3. **`golden_master.py`** -- one small army per faction, snapshotted and diffed.
   Deterministic, so any diff is an intended change (re-bless with `--build`) or a
   regression. Snapshots live in `tests/golden/` and are committed.
4. **`fuzz_armies.py`** -- many random armies. No 5xx, deterministic validation,
   non-negative points, idempotent round trip. Catches combination bugs.
5. **`ui_journeys.py`** -- Playwright (headless Chromium) driving the real UI:
   create army, add unit, a unit edit moving live points (squad size -- wargear
   is points-neutral for most 10e units), over-limit validation, missions page,
   no console errors. The thin true-to-the-user layer.

## Isolation

`db.py` already honours `COLLECTION_DB_PATH`. The api/golden/fuzz layers copy
`collection.db` to a temp file and point the env at it, so they never touch real
data and start no server. `ui_journeys.py` starts `app.py` on its own isolated
copy and stops it (via `/api/shutdown`) when done, leaving nothing running.

## Feature detection (Phase 5/6)

The suite is written to the full Phase 1-6 contract but skips anything not yet
present rather than failing: `duplicate_cap`, allies (`allied_by_host` /
`ally_config_for`), `core_stratagems`, `army_rules_for`, `missions`, and the
export/import routes are all probed first. So the same suite runs clean on a tree
where later phases are absent and lights up as they land.

## UI layer setup (one-time)

```
pip install playwright
playwright install chromium
```

Then add the stable hooks in `tests/TESTIDS.md` to the JS/templates. Without them
the journeys fall back to text selectors, which are brittle; with them the suite
survives UI tweaks. Keep the UI layer thin -- it is the most user-like but least
robust; the engine sweeps are where coverage lives.

## First run

Golden verify reports "no snapshots" until you bless a baseline once, in your
tree, with `python tests/golden_master.py --build`. Do this after the resolved
output is what you want; thereafter a diff means something changed.

## Role in rules-data updates

When `data/w40k/w40k.db` is refreshed to a new official-app data version
(see `CODEX_ARMORUM_DATA_UPDATE.md`), this suite is the verification step:
engine invariants sweep every datasheet in the *new* data, and golden-master
diffs should correspond one-to-one with the points/content changes that
`scripts/compare_w40k_db.py` reported. Review the diffs, then re-bless with
`python tests/run_all.py --golden-build`.

## Note on the chapter add-guard check

`api_roundtrip.py`'s "a generic unit the picker offers is accepted" check is the
chapter add-guard regression. It passes only when the add route gates on the
picker set (the fix). It is the suite demonstrating it catches that exact class of
bug.
