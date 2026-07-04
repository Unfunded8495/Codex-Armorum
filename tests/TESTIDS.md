# UI test hooks (data-testid)

The Playwright suite in `ui_journeys.py` binds to stable `data-testid` attributes
so it survives copy and layout tweaks. Where a hook is missing it falls back to
text or role selectors, which break easily. Add these once for a durable suite.
They are inert: no styling or behaviour, just attributes.

As of the companion-app-parity rebuild, the army builder is a 2-panel layout
(roster + a unit-options right panel) plus three full-screen overlays: the
add-unit picker, the Command Bunker reference, and the Edit Roster settings
screen. Battle Size and Detachments moved out of the right panel into Edit
Roster; the always-visible left unit-picker rail is gone, replaced by the
overlay.

## Army list / create flow (`static/js/army-list.js`, untouched by the rebuild)

| testid | element |
|---|---|
| `new-army-button` | "New Army" on the army list |
| `faction-select` | faction picker in the create flow |
| `battle-size-select` | battle-size picker in the create flow |
| `create-army-confirm` | confirm/create button |
| `import-button` | import control on the army list |

## Roster screen (`static/js/army-detail.js`)

| testid | element |
|---|---|
| `army-detail` | the army-builder detail container (3-column grid on the manual "Battle Roster sheet") |
| `army-title` | the army name — now an editable `<input>` styled as the page title (wired to `saveArmyMeta`; also still editable from Edit Roster) |
| `open-command-bunker` | the faction-badge button that opens Command Bunker |
| `context-strip` | the left rail's Configuration card (same hooks as the old context strip, reskinned) |
| `ctx-faction` | configuration row -> opens Command Bunker |
| `ctx-battlesize` | the Configuration card's Battle Size `<select>` (edits directly via `saveArmyMeta`; the Edit Roster sub-screen path `er-row-battlesize` still exists) |
| `ctx-detachment` | the "Choose Detachments" button -> opens Edit Roster on the Detachments sub-screen; warning-styled (`.is-missing`) when none is selected |
| `ctx-enhancements` | static configuration line: enhancements used / battle-size limit |
| `roster-kebab` | the overflow (⋮) button next to the army name -> opens the Edit Roster / Duplicate Roster menu |
| `foc-section-<characters\|battleline\|dedicated-transports\|other-datasheets>` | each Force-Org section wrapper |
| `foc-add-<slug>` | a section's "+" -- opens the add-unit picker pre-scoped to that category (same slug format as `foc-section-`) |
| `points-hud` | the persistent points/validity pill |
| `army-points` | the live total-points number (inside the HUD) |
| `validation-card` | the validation messages panel |
| `unit-row` | each roster unit row (click the body to open it in the right panel) |
| `ally-badge` | the "Ally" badge on allied rows |
| `detail-panel` | the right unit-options panel |
| `detail-empty` | the right-panel placeholder (nothing selected) |

## Unit-options right panel (`static/js/army-detail.js`, `renderUnitDetail`)

| testid | element |
|---|---|
| `unit-warlord-toggle` | the Warlord checkbox |
| `unit-enhancement-editor` | the Enhancements accordion body (cards render inside once fetched) |
| `wargear-editor` | the Wargear Options accordion body |
| `unit-leader-attach` | the "Attach to…" control |
| `unit-profiles-toggle` | the Profiles (statline/weapons) collapse |
| `unit-size-input` | the squad-size number input -- now in this panel, not the roster row |

## Add-unit picker overlay (`static/js/unit-picker.js`, `templates/army_builder.html`)

| testid | element |
|---|---|
| `unit-picker-panel` | the picker overlay itself (`#unitPickerModal`) -- now a full-screen, open-on-demand overlay, not an always-visible panel |
| `picker-unit-<NAME>` | a unit card in the picker, suffixed by exact name; the `.po-add` button inside it is what actually adds the unit -- the card body toggles an inline datasheet-profile preview (`.po-profile`) instead |

## Command Bunker overlay (`static/js/army-detail.js`)

| testid | element |
|---|---|
| (none yet) | Datasheets/Stratagems/Detachment Rules/Army Rules sections and their contents have no dedicated hooks today; add some here if a journey starts exercising this screen |

## Edit Roster overlay (`static/js/army-detail.js`)

| testid | element |
|---|---|
| `edit-roster-modal` | the overlay itself (`#editRosterModal`) |
| `menu-edit-roster` | the "Edit Roster" item in the roster-kebab menu |
| `menu-duplicate-roster` | the "Duplicate Roster" item in the roster-kebab menu |
| `er-row-battlesize` | the main screen's Battle Size row -> opens that sub-screen |
| `er-row-detachment` | the main screen's Detachments row -> opens that sub-screen (the DP-budget card list, same markup/hooks as below) |

## Detachment Points card list (`static/js/army-detail.js`, `renderDetachmentPanel`)

Used inside the Edit Roster "Detachments" sub-screen.

| testid | element |
|---|---|
| `detachment-panel` | the DP-budget header + card list wrapper |
| `dp-budget` | the "used / budget DP" pill |
| `detachment-chip` | a detachment card's clickable name (toggles it on/off; carries `style="cursor:pointer"` only when affordable -- unaffordable cards have no `style` attribute at all, which is how a test tells them apart) |
| `detachment-disposition` | the derived Force Disposition label, shown on a card only once it's selected |

## Missions (`static/js/missions.js`, `templates/_topbar.html`, untouched)

| testid | element |
|---|---|
| `nav-missions` | the Missions nav entry |
| `missions-view` | the missions reference container |

## Export (`static/js/army-detail.js`)

| testid | element |
|---|---|
| `export-button` | export control (centre header) |

## Removed since the companion-app-parity rebuild

These existed before the rebuild and no longer apply -- the elements they
pointed at are gone, not renamed, because the interaction itself changed:

- `config-battlesize` / `config-detachment` -- were right-panel-opening rows
  on the roster page; Battle Size/Detachments moved to Edit Roster
  (`er-row-battlesize` / `er-row-detachment`) and the right panel is unit-only now.
- `detachment-add` / `detachment-remove` -- were a `<select>` and a chip's ✕;
  replaced by clicking a `detachment-chip` card directly (toggles on/off).
- `add-unit-button` -- was the unscoped "+ Add Unit" button; every add is
  category-scoped now (`foc-add-<slug>`), so there's no unscoped entry point.

## Conventions

For list-like hooks (`unit-row`, `picker-unit-<NAME>`, `foc-section-<slug>`) set
the attribute in the template literal as the row is built, e.g.
``data-testid="unit-row"`` on each roster row and
``data-testid="picker-unit-${unit.name}"`` on each picker card.
