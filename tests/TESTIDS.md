# UI test hooks (data-testid)

The Playwright suite in `ui_journeys.py` binds to stable `data-testid` attributes
so it survives copy and layout tweaks. Where a hook is missing it falls back to
text or role selectors, which break easily. Add these once for a durable suite.
They are inert: no styling or behaviour, just attributes.

| testid | element | file (where the markup is built) |
|---|---|---|
| `army-detail` | the army-builder detail container (three-panel grid) | `static/js/army-detail.js` |
| `unit-picker-panel` | the persistent left-panel unit picker | `static/js/army-detail.js` (`showArmy`) |
| `detail-panel` | the right context/detail panel | `static/js/army-detail.js` (`showArmy`) |
| `detail-empty` | the right-panel placeholder (nothing selected) | `static/js/army-detail.js` |
| `army-points` | the live total-points number (centre header) | `static/js/army-detail.js` |
| `validation-card` | the validation messages panel (centre) | `static/js/army-detail.js` |
| `config-battlesize` | the Battle Size config row (opens right panel) | `static/js/army-detail.js` |
| `config-detachment` | the Detachment(s) config row (opens right panel) | `static/js/army-detail.js` |
| `dp-budget` | the "used / budget DP" readout in the detachment panel | `static/js/army-detail.js` |
| `detachment-chip` | a selected detachment chip | `static/js/army-detail.js` |
| `detachment-add` | the "+ Add detachment" select | `static/js/army-detail.js` |
| `detachment-remove` | the ✕ on a detachment chip | `static/js/army-detail.js` |
| `detachment-disposition` | the derived Force Disposition label on a chip | `static/js/army-detail.js` |
| `unit-row` | each roster unit row (click to open in right panel) | `static/js/army-detail.js` (`renderRoster`) |
| `unit-size-input` | the per-unit squad-size number input (in the row) | `static/js/army-detail.js` (`armyUnitRow`) |
| `unit-warlord-toggle` | the warlord toggle (in the right panel detail) | `static/js/army-detail.js` (`renderUnitDetail`) |
| `unit-enhancement-editor` | the enhancement editor (right panel) | `static/js/army-detail.js` |
| `unit-leader-attach` | the "Attach to" control (right panel detail) | `static/js/army-detail.js` |
| `unit-profiles-toggle` | the Profiles (statline/weapons) collapse (right panel) | `static/js/army-detail.js` |
| `wargear-editor` | the wargear editor container (right panel) | `static/js/army-detail.js` |
| `ally-badge` | the "Ally" badge on allied rows | `static/js/army-detail.js` |
| `army-rule-card` | the faction Army Rule card (centre) | `static/js/army-detail.js` |
| `stratagems-card` | the detachment Stratagems card (centre) | `static/js/army-detail.js` |
| `new-army-button` | "New Army" on the army list | `static/js/army-list.js` |
| `faction-select` | faction picker in the create flow | create-army UI |
| `battle-size-select` | battle-size picker in the create flow | create-army UI |
| `create-army-confirm` | confirm/create button | create-army UI |
| `add-unit-button` | "+ Add Unit" (opens the legacy modal picker) | `static/js/army-detail.js` |
| `picker-unit-<NAME>` | a unit option in the picker (left panel + legacy modal), suffixed by name | `static/js/unit-picker.js` |
| `export-button` | export control (centre header) | `static/js/army-detail.js` |
| `import-button` | import control on the army list | `static/js/army-list.js` |
| `nav-missions` | the Missions nav entry | nav / `templates` |
| `missions-view` | the missions reference container | `static/js/missions.js` |

For list-like hooks (`unit-row`, `picker-unit-<NAME>`) set the attribute in the
template literal as the row is built, e.g. ``data-testid="unit-row"`` on each
roster row and ``data-testid="picker-unit-${unit.name}"`` on each picker entry.
