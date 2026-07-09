# Plan: "How to Play" Guide Page

Status: PROPOSED (awaiting approval, PLAN.md P7)
Source content: data/rules/how_to_play.md (written 2026-07-06, verified against the 11th edition ruleset)

## TASK

- TRIGGER: Turn the how-to-play walkthrough into a page on the app, using as many of the existing image assets as possible.
- GOAL: A new server-rendered guide page in the manual (PDF-paper) style, reachable from the topbar, that walks a new player from a blank table to the final score, illustrated with every relevant diagram, deployment map, layout image and faction art piece already in static/images/.
- FILES:
  - app.py (new route, ~10 lines)
  - templates/guide.html (NEW, the page: content + structure)
  - static/css/guide.css (NEW, page-scoped styles, `gd-` prefix)
  - static/js/guide.js (NEW, small: scrollspy TOC, layout image fetch, plan/measure toggle, theme strip)
  - templates/_topbar.html (one nav link)
- EST: 5 files, roughly 750 lines total (most of it guide.html content).
- DONE-WHEN: `python app.py` serves /how-to-play with zero 404s in the network tab for every embedded image, the TOC scrollspy tracks all sections, the light/dark toggle switches the paper theme, and the page renders sanely at mobile width. Server stopped afterwards.

## Architecture decision

**Recommended: hand-authored Jinja template (server-rendered), not a markdown build pipeline.**

The /rules page pipeline (markdown -> build_rules.py -> core_rules.json -> rules.js renders) exists because the core rules are 3,300 lines of source that changes with GW updates. The guide is one curated editorial page whose layout IS the design: hero art, image grids, phase flow strips, side-by-side figures. Markdown is a poor container for that, and a parser + API route + client renderer is three moving parts for a page that changes rarely.

So: guide.html carries the content directly. data/rules/how_to_play.md stays as the editorial source document; a comment at the top of both files points at the other so they do not silently drift.

Rejected alternative (noted per IR6 spirit): extending build_rules.py or adding scripts/build_guide.py. Revisit only if the guide starts changing often.

## Route and navigation

- Route: `GET /how-to-play` -> guide.html, `active_page="guide"`, breadcrumb "How to Play".
- Topbar: add one link in the secondary nav (templates/_topbar.html), placed immediately before Core Rules: How to Play | Core Rules | ... A new player's reading order becomes the nav order.
- Cross-links inside the page go to /rules (deep anchors like #s07 work today), /missions, /army-builder, /arsenal/loadouts, /collection.

## Visual design

Follows the established manual/PDF-paper style (rules.css look): light paper default, Cinzel/EB Garamond/Oswald/PT Sans, no .scanlines overlay, dark reading mode via the shared rl-theme.js helper (localStorage key `caRules.theme`, so the whole app switches together).

Page structure:
- Sticky sidebar TOC (left, like /rules) listing the 8 guide chapters; scrollspy highlights the current one.
- Main column: a hero, then numbered chapters. Every chapter gets at least one figure.
- All images `loading="lazy"` with explicit width/height (from images_manifest.json where known) to avoid layout shift.
- Click-to-zoom lightbox for diagrams (simple: a dialog element + one JS handler, no dependency).
- CSS scoped under `body.gd-guide` with `gd-` class prefix throughout (PROJECT.md CSS scoping trap; `rl-` belongs to /rules, `mz-` to /missions).
- Typography rules: italics only for flavour quotes; informational text upright.

## Image plan (the point of the exercise)

Every asset below already exists in static/images/. Total: all 34 rules diagrams, all 6 deployment maps, 3+ layout images, the Boyz datasheet, faction art, and the 40k logo. Roughly 50 images.

### Hero
- warhammer_40_000_logo.png over a faction-art collage strip (a row of 5-6 of the 27 faction jpgs, CSS-cropped).

### Ch 1: What You Need
- exampledatasheetboyz.jpg as a "this is a datasheet, you will need one per unit" annotated figure.

### Ch 2: Muster Your Army
- Faction art grid: all 27 faction jpgs as small tiles (they double as a "pick your faction" visual index; each tile links to the army builder).
- Battle-size table stays hardcoded HTML (values verified against w40k.db `battle_size`; they change per edition, not per data update).

### Ch 3: Setting Up
- 3.1 Generate the mission: the 6 deployment icons (ic_hammer_and_anvil.png etc.) as a labelled grid; 3 example objective layouts (ic_layout_*.png) with the plan/measure toggle reused from the missions page pattern.
- 3.2 Build the battlefield: diagram-terrain-placed-on-a-mat, diagram-terrain-placed-on-the-battlefield, diagram-terrain-and-movement-top, diagram-terrain-and-movement-bottom.
- 3.3 Place objectives: diagram-controlling-a-terrain-objective.
- 3.4 Deploy: the deployment grid from 3.1 anchors here too via a cross-link; battlefield size note (44 x 60 inches, as stated on the missions page).

### Ch 4: The Battle Round (the diagram-dense chapter)
- Command phase: diagram-battle-shock-examples.
- Movement phase: diagram-moving-in-a-straight-line, diagram-rotating, diagram-coherency, diagram-engagement.
- Shooting phase / visibility: diagram-model-visible, diagram-model-fully-visible, diagram-unit-visible, diagram-unit-fully-visible, diagram-benefit-of-cover, diagram-hidden-and-obscuring, diagram-solid.
- Attack sequence: diagram-making-attacks, diagram-resolving-attack-dice, diagram-resolving-other-attacks, diagram-allocation-groups, diagram-attacking-attached-units.
- Charge phase: diagram-making-a-charge-move.
- Fight phase: diagram-start-of-fight-phase, diagram-pile-in-moves, diagram-normal-fight, diagram-overrun-fight.
- "Going further" sidebar (advanced rules teaser linking into /rules): diagram-engaged-monsters-vehicles-shooting, diagram-plunging-fire, diagram-making-a-surge-move, diagram-taking-to-the-skies, diagram-objective-consolidation, diagram-ongoing-consolidation.

### Ch 5-8 (Scoring, CP, First Game, Quick Reference)
- Ch 5 reuses diagram-controlling-a-terrain-objective as a small inline reminder figure (same asset, second placement).
- Ch 7 "first game script" gets a checklist card styled like the mission cards; no new imagery needed.
- Ch 8 quick reference: pure typographic tables (distances, turn order, attack sequence).

### Layout images: dynamic, not hardcoded
The layout PNGs are keyed by mission_layout UUID (ic_layout_<id with underscores>.png). Hardcoding UUIDs would break on the next w40k.db update, so guide.js makes one fetch of /api/missions and renders the first layout from each of 3 families, using the same slug scheme missions.js already uses (line ~302). Deployment map images are stable named files and are hardcoded.

## Decomposition (each step verifiable alone)

1. **Route + skeleton.** app.py route, guide.html with topbar/footer/TOC scaffold and hero, empty chapters, guide.css tokens. Verify: page loads, theme toggle works, no console errors.
2. **Chapters 1-3 content + images.** Verify: all setup images 200, figures match captions.
3. **Chapter 4 content + images.** Verify: all 30 phase/attack diagrams 200, lightbox opens/closes.
4. **Chapters 5-8 + dynamic layout strip.** Verify: /api/missions fetch renders 3 layout figures, plan/measure toggle flips images.
5. **Topbar link + polish pass.** Verify: nav highlight on /how-to-play, mobile width sane, dark mode sane, no em dashes (grep), full page screenshot.

## Verification (VERIFY.md gate, run at the end)

- `python app.py`, open /how-to-play in the preview browser.
- Network tab: filter failed; zero 404s.
- preview_snapshot: TOC entries and all 8 chapter headings present.
- Dark mode + mobile resize screenshots.
- `grep` for em dashes in the new files: zero hits.
- Stop the Flask server (check for a sibling session's server first per workflow memory).
- Remind to commit.

## Open questions (blocking none, defaults chosen)

- ASSUMPTION: route named /how-to-play with nav label "How to Play". Alternative: /guide.
- ASSUMPTION: faction tiles link to /army-builder generally, not per-faction (per-faction deep links can come later).
- ASSUMPTION: the guide does not appear inside the /rules TOC; it is a sibling page. Adding a banner link at the top of /rules ("New to the game? Start with How to Play") is a one-line follow-up if wanted.
