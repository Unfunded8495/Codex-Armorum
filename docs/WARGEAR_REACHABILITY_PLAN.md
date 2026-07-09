# Wargear Reachability Plan

Goal: every loadout the official app allows is buildable in the army builder, and every
loadout it forbids is flagged. This tracks the "53 datasheets with legal loadouts the UI
cannot reach" found by the 2026-07-05 audit (see memory: project_army_builder_parity_gaps).

Status legend: `[ ]` open, `[x]` done, `[-]` dropped/baselined (record why in the log).
Update this file as slices land; each phase deletes its sheets from the reachability
baseline and records the suite run in the log at the bottom.

Related, already shipped (2026-07-05):
- Legality warn gate: `wargear._cluster_legal_sets` + end-of-`validate_selection` check.
  Reachable-but-illegal states now warn ("Illegal loadout: ..."). 0 false positives across
  all 1141 default loadouts.
- choose_from semantics (the oracle for everything below): a loadout picks exactly `limit`
  choice bundles; the explicit empty bundle may fill any number of slots; non-empty bundles
  repeat only when `allow_duplicates`; a pick's count multiplies by its `option_qty` grant.

---

## Phase 0 - Acceptance oracle

Promote the session audit script into the test suite so every later phase is verified
mechanically, not by hand re-audit.

- [x] `tests/wargear_reachability.py`: enumerate UI-reachable selections per auditable
      datasheet, run each through `validate_selection`, assert:
      (a) every reachable-but-illegal end state carries the "Illegal loadout" warn;
      (b) the legal-but-unreachable set matches the checked-in baseline.
- [x] `data/wargear_reachability_baseline.json` + writer flag (`--update-baseline`,
      mirrors the `datasheet_gaps_baseline.json` pattern; baseline only ever shrinks).
- [x] Wire into `tests/run_all.py`.
- [-] Source script to adapt: session scratchpad `wargear_legality_audit2.py` was lost
      with its session. The enumerator was reconstructed from the engine contracts and
      army-detail.js renderGroupHtml instead (option_qty multiplier and
      repeatable-empty cluster semantics reproduced; verified on Bloodthirster,
      Cadre Fireblade, Ancient in Terminator Armour).

## Phase 1 - Engine-only: broken and half-wired replacements (~20 sheets, no JS)

### 1a. Swaps that never displace their default (link resolution failed) - DONE 2026-07-08
Picking Y leaves X equipped: the true "Y instead of X" state is unreachable AND the
"X+Y" state is reachable-illegal. Fix landed: the primary choose_from linking pass in
`wargear.wargear_schema` treated `all_choose_from_items - alt_items` as displaced, which
also zeroed items the alt KEEPS (the Palatine's blade). Now a default item is displaced
only if it is absent from every bundle offering the alternative. Verified by the Phase 0
oracle: unreachable sheets 108 -> 76 (58 loadouts now reachable, incl. Palatine), full
`run_all.py` green (golden unchanged), assertion (a) still clean, baseline re-blessed.

- [x] Linking pass in `wargear.wargear_schema` (bundle-aware displaced-item computation)
- [x] Guard: the Phase 0 oracle is the mechanical invariant (baseline shrink-only)
- Sheets:
  - [ ] Palatine (bolt pistol -> plasma pistol)
  - [ ] Venom / Ynnari Venom (twin splinter rifle -> splinter cannon)
  - [ ] Ynnari Archon (splinter pistol -> blast pistol)
  - [ ] Sydonian Skatros (radium jezzail -> transuranic arquebus)
  - [ ] Land Speeder (onslaught gatling cannon -> heavy flamer)
  - [ ] Venerable Dreadnought (storm bolter -> heavy flamer; assault cannon group)
  - [ ] Shield-Captain (guardian spear group)
  - [ ] Armiger Helverin / Armiger Warglaive (Questoris heavy stubber -> meltagun)

### 1b. Quantity on either side of a swap
"This model's 2 X can be replaced with ..." / "... replaced with 2 Y": wire
`linked_default_qty` (displace both copies) and `option_qty` (grant both copies) through
the plain replace_one path like the pool path already does, including points.

- [ ] Engine change in `validate_selection` replace_one block + schema qty derivation
- Sheets:
  - [ ] Acastus Knight Porphyrion / Chaos Acastus Knight Porphyrion (2 autocannons)
  - [ ] Contemptor-Achillus Dreadnought (2 lastrum storm bolters)
  - [ ] Telemon Heavy Dreadnought (2 iliastus culverins)
  - [ ] Hekaton Land Fortress (2 twin bolt cannons)
  - [ ] Stormraven Gunship (hurricane bolters)
  - [ ] Valkyrie (2 heavy bolters)
  - [ ] Gladiator Valiant (multi-melta pair; note: its clusters share item names, the
        warn gate drops them, so the oracle is the reachability test here)
  - [ ] Wraithlord (paired arm weapons)
  - [ ] Chimera / Inquisitorial Chimera (hull weapon groups)
  - [ ] Canoptek Spyders (particle beamer pair)
  - [ ] Ripper Swarms / Ethereal / Execrator / Krieg Command Squad (verify class during
        implementation; move to the correct phase if misfiled)

## Phase 2 - Count steppers for "up to N" additive items (~10 sheets, zero new JS)

"can be equipped with up to N X" / "up to two of the following, and can take duplicates"
renders today as a 0/1 checkbox. Classify in `_instruction_type` as `limited_per_n` with a
STATIC cap (no per-5-models threshold); stepper UI, cap badge and validation already exist.

- [ ] `_instruction_type` + limits synthesis for static caps
- Sheets:
  - [ ] Battlewagon (up to 4 big shootas)
  - [ ] Big'ed Bossbunka (big shootas)
  - [ ] AX-1-0 Tiger Shark / Tiger Shark (seeker missiles)
  - [ ] Devilfish (seeker missiles)
  - [ ] Hammerhead Gunship (seeker missiles)
  - [ ] Riptide Battlesuit (missile drones)
  - [ ] Cadre Fireblade (up to two drones, duplicates allowed; also removes its
        reachable-illegal 3-drone state once the cap is enforced)
  - [ ] Wraithknight / Wraithknight with Ghostglaive (up to two of the following)

## Phase 3 - Parser extensions reusing existing machinery (~5 sheets)

### 3a. Compound "replaced with 1 X and one of the following"
Bundle the fixed part into EACH bullet choice via `_bullet_bundles` (multi-item bundle
machinery from 2026-07-02 handles rendering/counting/pricing already). Also removes the
axe-alone class of reachable-illegal states.

- [ ] Parser extension + bundle invariant
- Sheets:
  - [ ] Bloodthirster (1 axe of Khorne and one of: bloodflail / lash)
  - [ ] Rogal Dorn Battle Tank
  - [ ] Kroot War Shaper (dart-bow and tri-blade -> bladestave and prey-hook)

### 3b. Missed weapon arrays ("can each be replaced" over multiple copies)
`_array_specs` rejects these; diagnose the pool-member/choose_from match and fix
detection. Per-mount select UI already exists.

- [ ] Detection fix + invariant
- Sheets:
  - [ ] Deff Dread (2 big shootas + 2 dread klaws, each replaceable)
  - [ ] War Walkers (each shuriken cannon)

## Phase 4 - New UI mechanics

### 4a. Dual "equip X OR replace Y with X" tri-state (Chaos Rhino family)
Card rows: `None` / `X` / `X (replaces Y)`. Client cost near zero: `wgRadio` rows already
post arbitrary set maps, so rows are `{}` / `{X:1, Y:1}` / `{X:1}` with data-keys asserting
the whole slot. Engine work: classify the wording, link the default, add an
`optional_displace` flag so `validate_selection` stale-default healing allows default+X to
coexist for the additive row.

- [ ] Corpus re-scan for the wording ("or can replace") beyond the audited 629 sheets;
      list every affected datasheet here before implementing
- [ ] Engine: classification + link + `optional_displace`
- [ ] UI: tri-state rows (army-detail.js renderGroupHtml replace_one branch)
- [ ] UI journey: Rhino havoc-only loadout buildable, warn-free
- Sheets:
  - [ ] Chaos Rhino (all faction variants share the pattern)

### 4b. Per-carrier picks (dynamic cap on surviving carriers)
"For each Helbrute fist this model is equipped with, it can be equipped with one of ..."
with the fist count depending on sibling groups' picks. New small group type: carrier item
+ cap = current carrier count; one pick row-set per carrier (or steppers sharing the cap);
validation clamps picks to carrier count (upgrades this class from warn-only to enforced).

- [ ] Engine group type + dynamic cap in `validate_selection`
- [ ] UI control + UI journey (Helbrute: two fists -> two guns; hammer -> cap drops to 1)
- Sheets:
  - [ ] Helbrute (all faction variants)

## Phase 5 - Multi-miniature ensembles (timeboxed diagnosis, ~11 sheets)

Named-character bands and command squads. Extend the oracle to per-miniature attribution
FIRST, then diagnose; expected mostly 1a/1b per mini plus export quirks. Baseline
permanently where the export itself is inconsistent (record `[-]` with reason).

- [ ] Oracle per-mini attribution
- Sheets:
  - [ ] Gaunt's Ghosts
  - [ ] Aestred Thurga and Agathae Dolan
  - [ ] Krieg Command Squad / Cadian Command Squad (also listed in 1b, reconcile)
  - [ ] Drayden's Lance Command Squad
  - [ ] Rogue Trader Entourage
  - [ ] Purge Corps Serberys Sulphurhounds (empty default_loadout in export; likely `[-]`)
  - [ ] The Twin Lance
  - [ ] Callous Blades Infractors
  - [ ] Vow-Sworn Sword Brethren Squad
  - [ ] Wardens of Ultramar
  - [ ] Brokhyr Iron-master

---

## Cross-cutting gates (every phase)

- `python tests/run_all.py --ui` green + reachability oracle green (baseline shrink only).
- Golden re-bless only for intended payload diffs (`--golden-build`).
- New engine invariants for each new schema behaviour.
- One browser walkthrough per phase on a representative sheet (Rhino 4a, Helbrute 4b,
  Battlewagon 2).
- Commit after each phase.

## Log

- 2026-07-05: Plan created. Prerequisites shipped the same day: wgGroupTitle label fix,
  choose_from legality warn gate (40/52 illegal-loadout sheets now warn; the rest are
  multi-mini or guard-excluded). Nothing in phases 0-5 started yet.
- 2026-07-08: Phase 0 landed. tests/wargear_reachability.py enumerates UI-reachable
  selections (default size) for 1001 auditable single-model-cluster datasheets and:
  (a) HARD-FAILs on any unwarned reachable-illegal end state - currently CLEAN (the
  legality gate is complete on the auditable subset); (b) tracks legal-but-unreachable
  loadouts vs data/wargear_reachability_baseline.json (shrink-only, --update-baseline).
  Baseline captured 108 sheets / 462 unreachable loadouts - more than the 53 the manual
  audit found, because the oracle is exhaustive. Notable new finding: many squad
  sergeants (Tactical, Devastator, ...) render their "replace bolt pistol and boltgun
  with one X and one Y" group with a cap of 0 (validate_selection clamps every swap to 0
  with "max 0 at this size"), so the whole sergeant weapon menu is unreachable. Wired
  into run_all.py after the engine layer.
- 2026-07-08: Phase 1a landed (bundle-aware displaced-item linking in wargear_schema).
  Oracle baseline 108 -> 76 sheets / 462 -> 404 loadouts (58 now reachable); (a) clean;
  run_all.py green (golden unchanged). Still open: Phase 1b quantity swaps still reproduce
  (Acastus 2x Lascannon, Contemptor 2x Infernus incinerator, Valkyrie 2x Heavy bolter);
  the cap-0 sergeant class needs a new pickable control for its choose_from (design TBD).
