# Faction Roster + Unit Datasheet redesign plan

Extends the "My Armies" PDF-manual design (handoff Pt3) to the two SPA drill-down
views: the **Faction Roster** (`#/faction/:fid`) and the **Unit Datasheet**
(`#/unit/:did`). The My Armies home is already done and is the reference
implementation for the paper-shell mechanics (see `static/css/my-armies.css`,
`showHome()` in `static/js/home.js`).

House rules apply throughout: no em dashes anywhere, smallest change that solves
the task, scope every CSS override to its page, run the gates in section 8 after
each phase, and stop the dev server when done.

## Progress

- [x] **Phase 0 - shared paper-shell foundation** (DONE, verified: home visually
  unchanged, shared theme toggle works, `python tests/run_all.py --ui` green).
- [x] **Phase 1 - Faction Roster** (DONE, verified: paper hero, stacked role
  sections, role filter, theme-agnostic tiles paper here + dark on Purchases,
  browse-all + empty state on paper, dark mode, `--ui` green).
- [x] **Phase 2 - Unit Datasheet** (DONE, verified: paper datasheet with stat
  lines + ranged/melee weapon tables + keyword pills + points, Card view,
  Collection tab empty + populated (mini cards / selects / gear chips), linked
  release editor, dark mode, all via a token remap scoped to
  `body.unit-sheet .rl-shell`; the shared datasheet renderers and the Army
  Builder are untouched (files unchanged, scope-guarded); `--ui` green).
- [x] **Follow-on: Mini manager** (`#/mini/:did`) (DONE). Reuses the unit-sheet
  paper skin (body sets `rl-spa unit-sheet mini-sheet`) plus `mini-page.css`:
  the sculpt "display case" is kept as a deliberate DARK island (dark tokens
  re-asserted locally so cut-out minis pop on their radial stage), while the
  reliquary ledger, built/unbuilt mini cards, title/legend and WIP notes are
  paper. Dark mode + shared toggle work; `--ui` green.

## 1. Locked decisions

1. **Faction-tile navigation stays as-is.** A roster tile keeps linking to
   `#/mini/:did` (manage minis). The datasheet stays reachable via "Browse All
   Datasheets". We do not re-point roster tiles at the datasheet.
2. **Do the lot on the unit page.** The full paper restyle includes the datasheet
   (Information / Detailed + Card), the "My Collection" mini-management tab, and
   the linked catalogue-release editor. Nothing on the unit page is left dark.
3. **Faction page switches to role sections.** Replace the current role filter
   tabs (show/hide) with stacked role sections (one section header + grid per
   role), matching the design and the home's allegiance grouping. A role quick
   filter may remain in the reading strip but the layout is sectioned.
4. **`buildUnitTiles` becomes theme-agnostic.** One shared tile renderer whose
   colours come from CSS variables that resolve to paper tokens inside a paper
   shell and to the existing dark values everywhere else (Purchases). No fork.

## 2. Design source and data

- Visual direction and tokens: `static/css/my-armies.css` (light + dark `--rl-*`
  token blocks) and the handoff README sections 2-5.
- Handoff README section 9 defines these two screens; the sample JSON confirms
  the data the design expects:
  - Roster unit: `{did, name, role, points, models, stages:{done,bench,raw}}`.
  - Datasheet: `{name, faction, role, points, keywords[], profile:{m,t,sv,w,ld,oc},
    invuln, ranged[], melee[], abilities[], loadout}`.
- No new backend data is required. Both views already have real endpoints:
  - `GET /api/factions/:fid/units` (roster with role, bought, owned, unlogged, points, multikit_groups)
  - `GET /api/collection?faction_id=` (owned minis with stage)
  - `GET /api/units/:did` (full datasheet payload: models/profile, ranged, melee,
    abilities, composition, loadout, costs, points_steps, keywords, invuln,
    collection_minis, linked_catalogue_models, multikit_alternatives, ...)

## 3. Grounding: current state vs design

| Design screen | App view today | Work is mostly |
|---|---|---|
| Faction Roster: hero + owned units grouped by role with done/bench/raw | `showFaction()` in `static/js/home.js` (dark hero, role filter tabs, niche tiles with Blessed/Rites/Forge counts) | Visual: paper shell, design hero, role sections |
| Unit Datasheet: stat line, ranged/melee tables, abilities, keywords | `showUnit()` in `static/js/unit.js` (dark two-column datasheet + Collection tab + linked releases) | Visual: paper "printed datasheet" plus full restyle of collection + editor |

Relevant functions:
- Faction: `showFaction()`, `factionHero()`, `wireUnitFilter()`,
  `buildUnitTiles()` (exported), `renderFactionBrowse()` in `static/js/home.js`.
- Unit: `showUnit()`, `renderCollectionShell()`, `populateMiniList()`,
  `miniGroupCard()`, `renderHeroGallery()`, `renderLinkedReleases()`,
  `renderLrePanel()`, `setupLinkedReleases()` in `static/js/unit.js`.
- Datasheet blocks (in `static/js/datasheet.js`, imported by `unit.js`):
  `renderDatasheetModels`, `renderInvuln`, `renderDamaged`, `renderWargear`,
  `renderAbilities`, `renderUnitComposition`, `renderLeaderAttach`,
  `renderOptions`, `renderTransport`, `renderPoints`, `renderKeywords`.
- Shared card: `renderDatasheetCard()` in `static/js/datasheet-card.js`.

Constraints found by grep (must respect):
- `buildUnitTiles` is used by BOTH `home.js` (roster) and `purchases.js:533`.
  Decision 4 resolves this (theme-agnostic tile).
- `renderDatasheetCard()` and the `datasheet.js` helpers are shared with the Army
  Builder (`army-list.js`, `army-detail.js`, `unit-picker.js`). All paper
  overrides MUST be scoped to `body.unit-sheet` so those other consumers are
  untouched.
- `#/mini/:did` (mini-page.js) and the unit page's "My Collection" tab overlap in
  purpose (both manage a unit's minis). We are not unifying them here.

## 4. Phase 0: shared paper-shell foundation (prerequisite) - DONE

Today the paper shell lives only in `my-armies.css` under `body.home-armies`.
Extract the reusable skin so all three paper views share one copy and one theme
toggle.

Steps:
1. New `static/css/spa-shell.css`, scoped to a shared `body.rl-spa` class. Move
   into it from `my-armies.css`: the `--rl-*` token blocks (light and
   `[data-rl-theme="dark"]`), the `main#view` full-bleed override, the
   `.scanlines` hide, `.rl-shell` + paper texture, the reading strip and chips and
   theme toggle (generalise the current `.am-strip*` names), the hero base, the
   section-header chip, and the shared keyframes.
2. Trim `my-armies.css` to home-only components (rail, index grid, hero specifics
   the home needs). Keep home visuals identical (re-verify with a screenshot).
3. New tiny module `static/js/rl-theme.js` exporting the theme helpers currently
   inline in `home.js` (`amThemeMode`, persist, the toggle wiring). Import it from
   `home.js`, `showFaction`, and `showUnit` so all three share `caRules.theme`.
4. Router (`static/js/app.js`): set `body.rl-spa` plus exactly one per-view class
   (`home-armies` / `faction-roster` / `unit-sheet`) for paper views, and clear
   all of them before dispatching any non-paper (dark) view. Extend the existing
   one-line home reset added in the home phase.
5. Load `spa-shell.css` before the per-page CSS in `templates/index.html`.

Size: 1 new CSS file, 1 tiny JS module, refactor of my-armies.css, ~15 lines of
JS. No visible change to the home (verify), no change to dark views.

Done-when: home still renders and toggles exactly as before;
`python tests/run_all.py --ui` passes.

## 5. Phase 1: Faction Roster (`showFaction`, restyle) - DONE

Goal: `#/faction/:fid` in the paper shell: faction hero, then owned units as
role sections with done/bench/raw counts; browse-all and empty states on paper.

Steps:
1. **Shell + strip.** Wrap `showFaction` output in `.rl-shell` + wrap container;
   set `body.faction-roster` + `data-rl-theme`. Reading strip carries: a
   "back to The Muster Field" chip (`#/`), a role quick-filter (All / Epic Hero /
   Character / Battleline / ... with counts), and the theme toggle.
2. **Hero.** Restyle `factionHero()` to the design hero (it is already close):
   banner art (`banner_url`), eyebrow (`group` or allegiance), Cinzel name,
   italic tagline (reuse `FACTION_TAGLINE`), stat plate (Models / Painted / pct),
   progress bar, existing actions (Record Purchase / Browse All Datasheets).
3. **Role sections (decision 3).** Replace the filter tabs with stacked sections:
   for each role present (order from the existing `roleOrder` array) render a
   section header chip + a tile grid. The strip role chips filter by
   showing/hiding sections client-side (no refetch), mirroring the home filter.
4. **Unit tiles (decision 4).** Restyle `buildUnitTiles()` output to the shared
   theme-agnostic tile: niche/cutout thumb (keep the cutout to uncut to glyph
   fallback chain and the multikit "shared kit" note), unit name, role, model
   count, and the tri-count relabelled to `done / bench / raw`. Tile keeps
   linking to `#/mini/:did` (decision 1).
5. **Browse-all + empty.** Restyle `renderFactionBrowse()` and the no-minis empty
   state to paper (hero + CTA to purchases / browse).

Files: `static/js/home.js` (showFaction, factionHero, buildUnitTiles,
renderFactionBrowse, filter wiring), new `static/css/faction-roster.css`, and the
tile token variables added in spa-shell.css / the shared tile CSS.

Done-when: a faction with minis shows the paper roster with role sections and
done/bench/raw; a faction with none shows the paper empty state; browse-all,
role filter, dark mode, and mobile all behave; Purchases page tiles still look
correct (theme-agnostic tile check); `python tests/run_all.py --ui` passes.

## 6. Phase 2: Unit Datasheet (`showUnit`, full restyle) - DONE

Goal: `#/unit/:did` as a paper "printed datasheet", plus paper restyle of the
collection tab and the linked-releases editor (decision 2).

Steps:
1. **Shell + strip.** Wrap `showUnit` output in the paper shell; set
   `body.unit-sheet` + theme. Reading strip carries a back-to-faction chip
   (`#/faction/:fid`), the Detailed/Card and Information/Collection toggles as
   chips, and the theme toggle.
2. **Datasheet header (centerpiece).** Paper stat band: Cinzel name, role +
   points, faction, keywords line, and the profile stat line (M / T / Sv / W /
   Ld / OC) from `renderDatasheetModels(d.models)`, restyled, with `invuln`
   surfaced. This is the iconic 40k datasheet header.
3. **Body blocks.** Scope-restyle the `datasheet.js` blocks to paper tables and
   panels: `renderWargear('Ranged Weapons')` and `('Melee Weapons')`,
   `renderAbilities`, `renderUnitComposition`, `renderLeaderAttach`,
   `renderOptions`, `renderTransport`, `renderPoints`, `renderKeywords`. Keep the
   arsenal weapon-hover (`setupArsenalHover`).
4. **Card view.** Restyle the `renderDatasheetCard()` output for the paper scope,
   scoped to `body.unit-sheet` only.
5. **Media column.** Restyle the hero gallery (`renderHeroGallery`), the owned
   panel, and the multikit-alternatives note to paper.
6. **Collection tab (decision 2).** Restyle `renderCollectionShell` +
   `populateMiniList` + `miniGroupCard` + `miniSubCard`: mini group cards, stage
   selects, paint dots, gear chips, notes textareas, photo rails and uploaders,
   duplicate/delete controls, and the squad-suggestion hint. Paper surfaces,
   readable ink, token-driven accents.
7. **Linked catalogue-release editor (decision 2).** Restyle
   `renderLinkedReleases`, `renderLrePanel`, `renderLreImageSection`, and the
   form inputs (`.cfe-input`, `.am-label`, `.ff-input`, `.btn-*`) as used inside
   this editor. Scope the form-control overrides to `body.unit-sheet` so the
   global modal/catalogue styles are untouched.
8. **Scoping guard (critical).** Every override in this phase lives under
   `body.unit-sheet .<class>`. The shared `renderDatasheetCard()` and
   `datasheet.js` classes used by the Army Builder must render unchanged there.

Files: `static/js/unit.js`, light scoped-class touches to `static/js/datasheet.js`
and possibly `static/js/datasheet-card.js` markup, new
`static/css/unit-sheet.css`.

Done-when: a character and a multi-model unit both render the paper datasheet
(stat band, ranged/melee tables, abilities, keywords, points); Card view,
Collection tab (add/stage/photo/gear/notes/duplicate/delete), and the linked
release editor all work and look paper; arsenal hover works; the Army Builder
datasheet card is visually unchanged (scoping proof); dark mode and mobile
behave; `python tests/run_all.py --ui` passes.

## 7. Cross-cutting details

- **Theme-agnostic tile (decision 4).** Give the shared unit tile its own surface
  and ink variables (for example `--tile-surface`, `--tile-ink`, `--tile-edge`)
  that default to the current dark values in base CSS and are overridden to paper
  tokens under `body.rl-spa` (or `body.faction-roster`). Same markup renders
  correctly in the dark Purchases page and the paper roster. Verify both pages
  after the change.
- **Shared-component scoping.** `renderDatasheetCard()` and the `datasheet.js`
  helpers are shared with the Army Builder. Never restyle their classes globally;
  always prefix with `body.unit-sheet`.
- **Mini-page overlap.** Left as-is; no unification of `#/mini/:did` and the unit
  page collection tab in this work.
- **No scrollIntoView** on app shell interactions (existing project rule).
- **Reduced motion.** Reuse the existing `prefers-reduced-motion` handling; keep
  new animations short and behind the same guard.

## 8. Verification gates (run per phase, paste output)

- Backend/logic unchanged in these phases, but still run `python tests/run_all.py`
  after any JS/template change and `python tests/run_all.py --ui` (Playwright,
  starts and stops its own isolated app.py) as the phase gate.
- Manual preview checks with screenshots each phase: light, dark, and mobile
  (>=360px, no horizontal overflow), plus the specific behaviours listed in each
  phase's done-when.
- Regression checks unique to these phases: Purchases tiles after the
  theme-agnostic tile change (Phase 1); Army Builder datasheet card after the
  scoped restyle (Phase 2).
- Stop the dev server after testing. Remind the user to commit after each phase.

## 9. File inventory

New:
- `static/css/spa-shell.css` (Phase 0, shared skin under `body.rl-spa`)
- `static/js/rl-theme.js` (Phase 0, shared theme helpers)
- `static/css/faction-roster.css` (Phase 1)
- `static/css/unit-sheet.css` (Phase 2)

Edited:
- `static/js/app.js` (router body-class management)
- `static/css/my-armies.css` (trim shared bits moved to spa-shell.css)
- `static/js/home.js` (showFaction, factionHero, buildUnitTiles,
  renderFactionBrowse, filter wiring)
- `static/js/unit.js` (showUnit and its render/collection/linked-release helpers)
- `static/js/datasheet.js` and possibly `static/js/datasheet-card.js` (scoped
  class touches only)
- `templates/index.html` (link spa-shell.css + the two new page CSS files)

## 10. Sequencing

Phase 0 (foundation) then Phase 1 (faction) then Phase 2 (unit). Deliver phase by
phase for approval rather than one drop. Each phase must be green on
`python tests/run_all.py --ui` with preview screenshots before starting the next.
