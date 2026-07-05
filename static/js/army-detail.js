import { esc, api, intOr } from './utils.js';
import { state, ensureBattleSizes } from './army-state.js';
import { setBreadcrumb } from './header.js';
import { renderDatasheetCard } from './datasheet-card.js';

const view       = document.getElementById('view');
const breadcrumb = document.getElementById('breadcrumb');

const ROLE_ORDER = ['Epic Hero','Character','Battleline','Infantry','Mounted',
  'Beast','Monster','Vehicle','Swarm','Transport','Fortification','Other','Unaligned'];

// Force-Org buckets the roster screen groups into (matches the reference
// app's section order exactly). Driven by each unit's server-computed
// `foc_category`, not the finer-grained battlefield `role` above (which the
// unit picker still uses for its own internal grouping).
const FOC_ORDER = ['Characters', 'Battleline', 'Dedicated Transports', 'Other Datasheets'];

export { ROLE_ORDER, FOC_ORDER };

/* ---- army detail view --------------------------------------------------- */

export async function showArmy(aid){
  view.innerHTML = `<div class="loading">Preparing battle plans…</div>`;
  let army;
  try{ army = await api(`/api/armies/${aid}`); }
  catch(e){
    view.innerHTML=`<div class="loading load-error">Failed to load army.<br><small>${esc(e.message)}</small></div>`;
    return;
  }
  state.army = army;
  setBreadcrumb([
    {label:'My Armies', href:'/'},
    {label:'Army Builder', href:'/army-builder'},
    {label:army.name},
  ]);

  // Three-column desktop layout: army config + validation (left rail), roster
  // (centre), context-sensitive unit-options detail (right). The unit picker
  // is the right-docked drawer in #unitPickerModal (unit-picker.js), opened on
  // demand from a Force-Org section's "+".
  view.innerHTML = `
    ${renderRosterHeader(army)}
    <div class="ab-detail ab-3col" data-testid="army-detail">
      <aside class="ab-leftrail" id="leftRail">${renderLeftRail(army)}</aside>
      <section class="ab-centre" id="centrePanel">
        <div id="rosterBody">${renderRoster(army.units, army.accent)}</div>
        <div class="ab-colophon" id="abColophon">${renderColophon(army)}</div>
      </section>
      <aside class="ab-rightpanel" id="rightPanel" data-testid="detail-panel">${renderRightPlaceholder()}</aside>
    </div>`;

  renderAbStrip(army);      // quick-strip FOC chips + live points readout
  wireCentreInputs(army);
  restoreRight();           // re-open a prior right-panel selection after a refetch
}

function renderColophon(army){
  return `<hr><p>&#10016; &nbsp;${esc(army.name)} &middot; <span id="abColoPts">${army.total_points} / ${army.points_limit}</span> points&nbsp; &#10016;</p>`;
}

function renderRightPlaceholder(){
  return `<div class="ab-rp-empty" data-testid="detail-empty">
      <span class="ab-rp-empty-icon">✦</span>
      <p>Select a unit or a configuration row to edit it here.</p>
    </div>`;
}

/* ---- left rail (points + config + validation + quick list) -------------- */

// Everything about the LIST (as opposed to a unit) lives in the sticky left
// rail: the points HUD, the configuration card, the validation card, the
// add-unit button and the roster quick list -- always visible beside the
// roster instead of stacked above/below it.
function renderLeftRail(army){
  return `
    ${renderPointsHud(army)}
    ${renderContextStrip(army)}
    ${renderValidationCard(army)}
    <button class="ab-adds-btn" type="button" onclick="openUnitPicker()">+ Add Unit</button>
    ${renderQuickList(army)}`;
}

// Points HUD: black plate with the big used total, a progress bar and a
// remaining/over status line. id="ptsUsed"/data-testid="army-points" are kept
// stable so the live-points wiring (updatePointsBar) and the UI test suite
// keep working unchanged. Click jumps to the validation card (scroll math,
// not scrollIntoView -- that breaks the host app).
function renderPointsHud(army){
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  const pct = hudPct(army);
  return `
    <div class="hud-pill ${over?'is-over':''}" id="hudPill" data-testid="points-hud" role="button" tabindex="0" title="Jump to validation"
         onclick="jumpToValidation()">
      <div class="hud-kicker">Points <span class="hud-warn" id="hudWarn" ${hudHasIssues(army)?'':'hidden'}>&#9888;</span></div>
      <div class="hud-line"><b id="ptsUsed" data-testid="army-points">${army.total_points}</b><small>/ <span id="ptsLimit">${army.points_limit}</span> pts</small></div>
      <div class="hud-bar"><span class="hud-bar-fill" id="hudBarFill" style="width:${pct}%"></span></div>
      <div class="hud-note" id="hudNote">${hudNote(army)}</div>
    </div>`;
}

function hudPct(army){
  if(!(army.points_limit>0)) return 0;
  return Math.min(100, Math.round(army.total_points / army.points_limit * 100));
}
function hudNote(army){
  if(!(army.points_limit>0)) return 'No points limit set';
  const d = army.points_limit - army.total_points;
  return d >= 0 ? `${d} pts remaining` : `${-d} pts over the limit`;
}

function hudHasIssues(army){
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  return over || (army.validation||[]).some(v=>v.level==='err'||v.level==='warn');
}

// Jump the sticky left rail to the validation card (container scrollTop math;
// never scrollIntoView) and flash it.
export function jumpToValidation(){
  const card = document.getElementById('validationCard');
  const rail = document.getElementById('leftRail');
  if(!card || !rail) return;
  const cr = card.getBoundingClientRect(), rr = rail.getBoundingClientRect();
  rail.scrollTop += cr.top - rr.top - 12;
  card.classList.remove('rl-flash');
  requestAnimationFrame(()=>card.classList.add('rl-flash'));
  setTimeout(()=>card.classList.remove('rl-flash'), 1700);
}

// Validation card: green (battle-ready) or rust (muster issues) left bar +
// header, with the server validation rows beneath. Keeps the validation-card
// testid and the jump-to-unit row buttons.
function renderValidationCard(army){
  const rows = army.validation || [];
  const issues = rows.filter(v=>v.level==='err'||v.level==='warn').length
    + ((army.points_limit>0 && army.total_points>army.points_limit) ? 0 : 0);
  const clean = !hudHasIssues(army);
  return `
    <div class="ab-validation ${clean?'is-ok':'is-bad'}" id="validationCard" data-testid="validation-card">
      <div class="ab-val-head">
        <span class="ab-val-dot" aria-hidden="true"></span>
        <span class="ab-val-title">${clean?'Battle-Ready':`Muster Issues${issues?` · ${issues}`:''}`}</span>
      </div>
      <div id="validationBody">${renderValidation(army)}</div>
    </div>`;
}

// Roster quick list: every unit as a jump link (name + Warlord star + pts).
function renderQuickList(army){
  const units = army.units || [];
  const models = units.reduce((s,u)=>s+(u.squad_size||0), 0);
  const rows = units.map(u=>{
    const pts = (u.points||0)+(u.enhancement_cost||0);
    return `<a class="ab-ql-row" href="#" onclick="event.preventDefault();jumpToUnit('${u.id}')">
        <span class="ab-ql-name">${esc(u.name)}${u.is_warlord?' <span class="ab-ql-star" title="Warlord">★</span>':''}</span>
        <span class="ab-ql-pts">${pts}</span>
      </a>`;
  }).join('');
  return `<div class="ab-card ab-quicklist" id="abQuickList">
      <div class="ab-card-head"><span>Roster</span><span id="abQlModels">${models} models</span></div>
      <nav class="ab-ql-list">${rows || '<p class="ab-ql-empty">No units mustered yet.</p>'}</nav>
    </div>`;
}

export function refreshQuickList(){
  const el = document.getElementById('abQuickList');
  if(el && state.army) el.outerHTML = renderQuickList(state.army);
}

/* ---- quick strip (Battle Roster chrome) ----------------------------------
   FOC-section jump chips with live counts + the points readout, rendered into
   the sticky strip in the template (outside #view, so it survives roster
   re-renders only via explicit calls). */

function renderAbStrip(army){
  const labelEl = document.getElementById('abStripLabel');
  if(labelEl) labelEl.textContent = 'Battle Roster';
  const chipsEl = document.getElementById('abStripChips');
  if(!chipsEl) return;
  const counts = {};
  FOC_ORDER.forEach(c=>counts[c]=0);
  (army.units||[]).forEach(u=>{
    const cat = counts[u.foc_category] != null ? u.foc_category : 'Other Datasheets';
    counts[cat]++;
  });
  const label = {Characters:'Characters', Battleline:'Battleline',
    'Dedicated Transports':'Transports', 'Other Datasheets':'Other'};
  // Strip chip order per the design: Characters / Battleline / Other /
  // Transports (the roster sections themselves keep FOC_ORDER).
  const stripOrder = ['Characters', 'Battleline', 'Other Datasheets', 'Dedicated Transports'];
  chipsEl.innerHTML = stripOrder.map(cat=>
    `<a class="rl-chip" href="#foc-${focSlug(cat)}" onclick="event.preventDefault();jumpToFoc('${focSlug(cat)}')">${esc(label[cat]||cat)}<b id="abChip-${focSlug(cat)}">${counts[cat]}</b></a>`).join('');
  updateStripPts(army);
}

function updateStripPts(army){
  const el = document.getElementById('abStripPts');
  if(!el) return;
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  el.classList.toggle('is-over', over);
  el.innerHTML = `<b>${army.total_points}</b> / ${army.points_limit} pts`;
}

function refreshStripChips(){
  if(state.army) renderAbStrip(state.army);
}

// Jump the window to a Force-Org section, offset below the sticky chrome.
export function jumpToFoc(slug){
  const el = document.getElementById('foc-'+slug);
  if(!el) return;
  const chrome = document.querySelector('.rl-chrome');
  const y = el.getBoundingClientRect().top + window.scrollY - ((chrome?chrome.offsetHeight:122) + 8);
  window.scrollTo({top:Math.max(0,y), behavior:'smooth'});
  el.classList.remove('rl-flash');
  requestAnimationFrame(()=>el.classList.add('rl-flash'));
  setTimeout(()=>el.classList.remove('rl-flash'), 1700);
}

// Masthead: small BATTLE ROSTER plate + faction/detachment meta, the army
// name as an editable input styled as the page title (wired to the existing
// saveArmyMeta flow), a stats sub-line, and the existing action cluster
// (Command Bunker badge, kebab menu, exports) -- all behaviors unchanged.
function renderRosterHeader(army){
  const dets = (army.detachments||[]).map(d=>esc(d.name)).join(' + ') || 'No detachment';
  return `
    <div class="ab-mast">
      <div class="ab-mast-top">
        <span class="ab-mast-plate">Battle Roster</span>
        <span class="ab-mast-meta" id="abMastMeta">${esc(army.faction_display_name||army.faction_name||'')} &middot; ${dets}</span>
        <span class="ab-mast-actions">
          <button class="cb-open-btn" type="button" data-testid="open-command-bunker" onclick="openCommandBunker()" title="Command Bunker">${army.icon_url?`<img src="${esc(army.icon_url)}" alt="">`:'&#9879;'}</button>
          <div class="uc-kebab-wrap" onclick="event.stopPropagation()">
            <button class="uc-kebab rh-kebab" type="button" title="More actions" data-testid="roster-kebab" onclick="toggleKebabMenu(this)">&#8942;</button>
            <div class="uc-kebab-menu" hidden>
              <button type="button" data-testid="menu-edit-roster" onclick="openEditRoster()">Edit Roster</button>
              <button type="button" data-testid="menu-duplicate-roster" onclick="duplicateRoster()">Duplicate Roster</button>
            </div>
          </div>
          <div class="ab-export-btns">
            <button class="ab-export-btn" type="button" data-testid="export-button" onclick="exportArmy('copy', this)">Copy list</button>
            <button class="ab-export-btn" type="button" onclick="exportArmy('txt', this)">.txt</button>
            <button class="ab-export-btn" type="button" onclick="exportArmy('json', this)">.json</button>
            <button class="ab-export-btn" type="button" data-testid="export-cards-pdf" onclick="exportDatasheetsPdf(this)">Cards PDF</button>
          </div>
        </span>
      </div>
      <input class="ab-army-title" data-testid="army-title" value="${esc(army.name)}"
             aria-label="Army name" spellcheck="false" placeholder="Army name" onchange="saveArmyMeta()">
      <div class="ab-mast-sub">
        <span id="abMastStats">${esc(army.battle_size||'Custom')} &middot; ${army.points_limit} pts &nbsp;&middot;&nbsp; ${mastStats(army)}</span>
        <span class="ab-mast-hint">Click a unit name for its datasheet</span>
      </div>
    </div>`;
}

function mastStats(army){
  const units = army.units || [];
  const models = units.reduce((s,u)=>s+(u.squad_size||0), 0);
  return `${units.length} unit${units.length===1?'':'s'} &middot; ${models} model${models===1?'':'s'}`;
}

function refreshMastStats(){
  const el = document.getElementById('abMastStats');
  if(el && state.army) el.innerHTML =
    `${esc(state.army.battle_size||'Custom')} &middot; ${state.army.points_limit} pts &nbsp;&middot;&nbsp; ${mastStats(state.army)}`;
}

/* ---- configuration card ---------------------------------------------------
   Always-visible summary of the list's configuration (faction / battle size /
   detachments / enhancement budget), each row a shortcut to where it's
   changed. All the ctx-* testids and their click behaviors are unchanged --
   this is the same context strip, reskinned as the rail's Configuration card
   (battle-size editing itself stays in the Edit Roster sub-screen: the rail
   row deep-links there, avoiding a duplicate #abBattleSize select). */

function renderContextStrip(army){
  const dets     = army.detachments || [];
  const dpBudget = army.detachment_points_limit;   // null = Custom, no cap
  const dpUsed   = army.detachment_points_used || 0;
  const dpOver   = dpBudget != null && dpUsed > dpBudget;
  const dpBadge  = dpBudget != null ? `${dpUsed} / ${dpBudget} DP` : `${dpUsed} DP`;
  const enhLimit = army.enhancement_limit;
  const enhUsed  = (army.units||[]).filter(u=>u.enhancement_id).length;
  // army.detachments rows don't carry points_cost -- read it from the
  // faction's detachment cache (warmed by wireCentreInputs).
  const costOf = d => d.points_cost
    ?? (state.detachCache[army.faction_id]||[]).find(x=>x.id===d.id)?.points_cost
    ?? 0;
  const detRows = dets.length ? dets.map(d=>`
      <div class="ab-cfg-det">
        <span class="ab-cfg-det-name">${esc(d.name)}</span>
        <span class="ab-cfg-det-dp">${costOf(d)} DP</span>
        <button type="button" class="ab-cfg-det-x" title="Remove detachment" onclick="removeDetachment('${esc(d.id)}')">&#10005;</button>
      </div>`).join('')
    : `<div class="ab-cfg-none">None selected</div>`;
  return `<div class="ab-card ab-cfg" id="ctxStrip" data-testid="context-strip">
      <div class="ab-card-head"><span>Configuration</span></div>
      <div class="ab-cfg-body">
        <button class="ab-cfg-row" type="button" data-testid="ctx-faction" onclick="openCommandBunker()">
          <span class="ab-cfg-label">Faction</span>
          <span class="ab-cfg-value">${esc(army.faction_display_name||army.faction_name||'')} <span class="ab-cfg-hint">rules &#9656;</span></span>
        </button>
        <label class="ab-cfg-select-wrap">
          <span class="ab-cfg-label">Battle size</span>
          <select class="ab-cfg-select" id="abBattleSizeRail" data-testid="ctx-battlesize" onchange="onRailBattleSize()">${railBattleSizeOptions(army)}</select>
        </label>
        <div class="ab-cfg-block">
          <div class="ab-cfg-block-head">
            <span class="ab-cfg-label">Detachments</span>
            <span class="ab-cfg-dp ${dpOver?'is-over':''}" title="Detachment Points">${dpBadge}</span>
          </div>
          ${detRows}
          <button class="ab-cfg-choose ${dets.length?'':'is-missing'}" type="button" data-testid="ctx-detachment" onclick="openEditRoster('detachment')">${dets.length?'Choose Detachments':'⚠ Choose a Detachment'}</button>
        </div>
        ${enhLimit != null ? `<div class="ab-cfg-line" data-testid="ctx-enhancements">
            <span class="ab-cfg-label">Enhancements</span>
            <span class="ab-cfg-count ${enhUsed>enhLimit?'is-over':''}">${enhUsed} / ${enhLimit}</span>
          </div>` : ''}
        <div class="ab-cfg-line">
          <span class="ab-cfg-label">Units</span>
          <span class="ab-cfg-count">${(army.units||[]).length}</span>
        </div>
      </div>
    </div>`;
}

export function refreshContextStrip(){
  const el = document.getElementById('ctxStrip');
  if(el && state.army) el.outerHTML = renderContextStrip(state.army);
}

// Options for the rail's Battle Size select. state.battleSizes is fetched
// async (wireCentreInputs warms it, then refreshes the config card); until
// it lands, render just the current value so the select is never empty.
function railBattleSizeOptions(army){
  const cur = army.battle_size || 'Custom';
  const sizes = state.battleSizes || [];
  if(!sizes.length) return `<option value="${esc(cur)}" selected>${esc(cur)}${cur!=='Custom'?` · ${army.points_limit} pts`:''}</option>`;
  return sizes.map(b=>
      `<option value="${esc(b.name)}" ${b.name===cur?'selected':''}>${esc(b.name)} · ${b.points_limit} pts</option>`).join('')
    + `<option value="Custom" ${cur==='Custom'?'selected':''}>Custom</option>`;
}

// Rail battle-size change: same save path as the Edit Roster sub-screen's
// select (the server re-derives the points limit + DP budget and may trim
// detachments; saveArmyMeta refetches when that happens).
export function onRailBattleSize(){
  saveArmyMeta();
}

/* ---- sidebar ------------------------------------------------------------ */

// Battle Size body (select + custom-points input): shared by the Edit Roster
// sub-screen below. Options are filled on open (fillBattleSizeSelect).
function renderBattleSizePanel(army){
  const isCustom = (army.battle_size||'Custom') === 'Custom';
  return `
    <div class="ab-meta-item">
      <label>Battle Size</label>
      <select id="abBattleSize" onchange="onAbBattleSize()"></select>
    </div>
    <div class="ab-meta-item ab-custom-pts" id="abPtsField" ${isCustom?'':'hidden'}>
      <label>Points Limit</label>
      <input type="number" id="abPtsLimit" value="${army.points_limit}" min="0" step="100" onchange="saveArmyMeta()">
    </div>`;
}

// "**word**" markdown bold -> <b>, applied to already-escaped text (the `**`
// markers survive esc() since they aren't HTML-special, and the tags this
// injects are ours, not user input, so this is safe to run post-escape).
function mdBold(escaped){
  return escaped.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}

// DP-budget card list (matches the reference app's "Choose Detachments"
// screen): every faction detachment is its own card, selected ones outlined,
// unaffordable ones dimmed, and a chevron expands the detachment's
// `restrictions` blurb text when it has any. Clicking a card's name toggles
// it on/off directly -- no separate add control.
function renderDetachmentPanel(army){
  const budget = army.detachment_points_limit;          // null = Custom (no cap)
  const used   = army.detachment_points_used || 0;
  const over   = budget != null && used > budget;
  const budgetLabel = budget == null ? `${used} DP` : `${used} / ${budget} DP`;
  const have = new Set(army.detachment_ids || []);
  const remaining = budget == null ? Infinity : budget - used;
  const dispositionFor = {};
  (army.detachments||[]).forEach(d=>{ dispositionFor[d.id] = d.disposition; });

  // Selected detachments float to the top of the list (per the design
  // captures), alphabetical within each group.
  const all = (state.detachCache[army.faction_id] || []).slice()
    .sort((a,b)=>(have.has(b.id)?1:0)-(have.has(a.id)?1:0)
      || (a.name||'').localeCompare(b.name||''));
  const cards = all.length ? all.map(d=>{
    const selected = have.has(d.id);
    const affordable = selected || (d.points_cost||0) <= remaining;
    const restrictions = d.restrictions || [];
    const rules = d.rules || [];
    const hasDetails = restrictions.length || rules.length;
    const expandId = `dpExpand-${esc(d.id)}`;
    const disposition = dispositionFor[d.id];
    // Expand = the detachment's rule text (what taking it actually does) +
    // any restrictions -- readable before committing the pick, not only from
    // the Command Bunker after the fact.
    const detailHtml = [
      rules.map(r=>`${r.name?`<h4>${esc(r.name)}</h4>`:''}<p class="dp-rule-text">${mdBold(esc(r.description||''))}</p>`).join(''),
      restrictions.map(r=>`${r.title?`<h4>${esc(r.title)}</h4>`:''}${(r.bullets||[]).map(b=>`<p>${mdBold(esc(b))}</p>`).join('')}`).join(''),
    ].join('');
    // The affordability contract the UI tests read: an affordable card's name
    // carries onclick + style="cursor:pointer"; an unaffordable one has no
    // style attribute at all (and a rust "not enough DP" line instead).
    return `<div class="dp-card ${selected?'is-selected':''} ${affordable?'':'is-locked'}">
        <span class="dp-tick" aria-hidden="true">${selected?'&#10003;':''}</span>
        <span class="dp-card-name" data-testid="detachment-chip" ${affordable?`onclick="toggleDetachmentCard('${esc(d.id)}')" style="cursor:pointer"`:''}>${esc(d.name)}${selected&&disposition?` <span class="ab-detach-chip-disp" data-testid="detachment-disposition" title="Force Disposition">&#11043; ${esc(disposition)}</span>`:''}</span>
        <span class="dp-card-cost">${d.points_cost||0} DP</span>
        ${hasDetails?`<button type="button" class="dp-card-chev" onclick="event.stopPropagation();toggleDpExpand('${expandId}')" title="Show rules">&#9656;</button>`:'<span class="dp-card-chev"></span>'}
      </div>
      ${!affordable && !selected?`<div class="dp-need">Not enough DP remaining</div>`:''}
      ${hasDetails?`<div class="dp-card-expand" id="${expandId}" hidden>${detailHtml}</div>`:''}`;
  }).join('') : `<p class="po-empty">No detachments available for this faction.</p>`;

  return `
    <div class="dp-budget-head" data-testid="detachment-panel">
      <span class="dp-budget-label">Available Detachment Points (DP)</span>
      <span class="dp-budget-pill ${over?'is-over':''}" id="abDpBudget" data-testid="dp-budget">${budgetLabel}</span>
    </div>
    <p class="dp-intro">Each detachment costs DP from your battle-size budget &mdash; stack as many as you can afford. Every detachment brings its own rules, enhancements and stratagems.</p>
    <div id="abDetachList">${cards}</div>`;
}

export function toggleDpExpand(id){
  const el = document.getElementById(id);
  if(el) el.hidden = !el.hidden;
}

/* ---- Edit Roster: name + Battle Size + Detachments, consolidated into one
   overlay with the latter two as tap-through sub-screens (matches the
   reference app's Edit Roster screen; previously these were 3 separate
   always-visible/right-panel surfaces on the roster page). ------------------ */

export function openEditRoster(view){
  if(!state.army) return;
  state.editRosterView = view || 'main';   // context-strip chips deep-link a sub-screen
  renderEditRosterInto(state.army);
  const overlay = document.getElementById('editRosterModal');
  if(overlay) overlay.hidden = false;
  syncOverlayScrim();
}

export function closeEditRoster(){
  const overlay = document.getElementById('editRosterModal');
  if(overlay) overlay.hidden = true;
  syncOverlayScrim();
}

export function editRosterShow(view){
  state.editRosterView = view;
  renderEditRosterInto(state.army);
}

function renderEditRosterInto(army){
  const overlay = document.getElementById('editRosterModal');
  if(!overlay) return;
  // The Detachments sub-screen is a manual (paper) drawer; the main screen
  // and the Battle Size sub-screen keep the dark overlay styling.
  overlay.classList.toggle('po-manual', state.editRosterView === 'detachment');
  overlay.innerHTML = renderEditRoster(army);
  if(state.editRosterView === 'battlesize') fillBattleSizeSelect(army);
}

function renderEditRoster(army){
  const view = state.editRosterView || 'main';
  if(view === 'battlesize') return erSubScreen('Battle Size', renderBattleSizePanel(army));
  if(view === 'detachment')
    return erSubScreen('Choose Detachments', renderDetachmentPanel(army),
                       army.faction_display_name || army.faction_name || '');
  return renderEditRosterMain(army);
}

function erSubScreen(title, bodyHtml, factionTag){
  return `
    <div class="po-overlay-head">
      <button class="cb-back" type="button" onclick="editRosterShow('main')" aria-label="Back" title="Back">&#10094;</button>
      <h2 class="po-overlay-title">${esc(title)}</h2>
      ${factionTag?`<span class="po-head-tag">${esc(factionTag)}</span>`:''}
    </div>
    <div class="po-body">${bodyHtml}</div>`;
}

function renderEditRosterMain(army){
  const bs = army.battle_size || 'Custom';
  const dets = army.detachments || [];
  const dpBudget = army.detachment_points_limit;
  const dpTag = dets.length && dpBudget != null
    ? ` &middot; ${army.detachment_points_used||0}/${dpBudget} DP` : '';
  const detSummary = dets.length
    ? dets.map(d=>esc(d.name)).join(', ') + dpTag : 'None selected';
  return `
    <div class="po-overlay-head">
      <h2 class="po-overlay-title">Edit Roster</h2>
      <button class="po-close cb-back" type="button" onclick="closeEditRoster()" aria-label="Close" title="Close">&times;</button>
    </div>
    <div class="po-body er-body">
      <p class="er-label">Name</p>
      <input class="er-name-input" id="erName" value="${esc(army.name)}" placeholder="Army name" onchange="saveArmyMeta()">
      <p class="er-label">Army</p>
      <div class="er-faction-row">${esc(army.faction_display_name||army.faction_name||'')}</div>
      <p class="er-label">Battle Size</p>
      <button class="er-config-row" type="button" data-testid="er-row-battlesize" onclick="editRosterShow('battlesize')">
        <span>${esc(bs)}${army.points_limit?` &middot; ${army.points_limit} pts`:''}</span><span class="er-config-chev">&#9656;</span>
      </button>
      <p class="er-label">Detachments</p>
      <button class="er-config-row" type="button" data-testid="er-row-detachment" onclick="editRosterShow('detachment')">
        <span>${detSummary}</span><span class="er-config-chev">&#9656;</span>
      </button>
    </div>`;
}

// Re-POST the army's own export as a fresh import -- reuses the existing
// export/import endpoints rather than adding a dedicated duplicate route.
export async function duplicateRoster(){
  if(!state.army) return;
  let res;
  try{
    const data = await (await fetch(`/api/armies/${state.army.id}/export?fmt=json`)).json();
    res = await (await fetch('/api/armies/import', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(data)})).json();
  }catch(e){ return; }
  if(res && res.ok && res.id) location.hash = '/army/' + res.id;
}

/* ---- drawer scrim + datasheet card overlay ------------------------------- */

// The three drawers (unit picker / Command Bunker / Edit Roster) share one
// scrim: visible while any of them is open, click closes everything.
const DRAWER_IDS = ['unitPickerModal', 'commandBunker', 'editRosterModal'];

export function syncOverlayScrim(){
  const scrim = document.getElementById('poScrim');
  if(!scrim) return;
  const noneOpen = DRAWER_IDS.every(id=>document.getElementById(id)?.hidden !== false);
  scrim.hidden = noneOpen;
  // Drawers lock body scroll while open (released when the last one closes).
  document.body.style.overflow = noneOpen ? '' : 'hidden';
}

export function closeAllOverlays(){
  DRAWER_IDS.concat('dsCardOverlay').forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.hidden = true;
  });
  syncOverlayScrim();
}

// Full datasheet card overlaid like an image lightbox -- reached by clicking a
// unit's name in the roster or a Command Bunker datasheet row. Same cached
// /api/units/<did> payload the profiles sections use.
export async function openDatasheetCard(did){
  const overlay = document.getElementById('dsCardOverlay');
  const body = document.getElementById('dsCardBody');
  if(!overlay || !body) return;
  body.innerHTML = `<p class="dsc-overlay-loading">Loading datasheet&hellip;</p>`;
  overlay.hidden = false;
  let detail = state.unitDetailCache[did];
  if(!detail){
    try{ detail = await api(`/api/units/${did}`); state.unitDetailCache[did] = detail; }
    catch(e){ body.innerHTML = `<p class="dsc-overlay-loading">Could not load the datasheet.</p>`; return; }
  }
  body.innerHTML = renderDatasheetCard(detail);
  body.scrollTop = 0;
}

export function closeDatasheetCard(){
  const overlay = document.getElementById('dsCardOverlay');
  if(overlay) overlay.hidden = true;
}

const STRAT_CAT = {battleTactic:'Battle Tactic', strategicPloy:'Strategic Ploy',
  epicDeed:'Epic Deed', wargear:'Wargear'};
const STRAT_PILL_CLASS = {battleTactic:'strat-pill-battleTactic', strategicPloy:'strat-pill-strategicPloy',
  epicDeed:'strat-pill-epicDeed', wargear:'strat-pill-wargear'};
const STRAT_PHASE_ORDER = ['Command','Movement','Shooting','Charge','Fight','Any','Other'];

/* ---- Command Bunker: faction/army reference overlay (Datasheets,
   Stratagems, Detachment Rules, Army Rules) -- a dedicated screen reached
   from the roster's faction badge, not inline content on the roster page. */

export async function openCommandBunker(){
  if(!state.army) return;
  const overlay = document.getElementById('commandBunker');
  if(!overlay) return;
  overlay.innerHTML = renderCommandBunker(state.army);
  overlay.hidden = false;
  syncOverlayScrim();
  loadCbDatasheets(state.army);
}

export function closeCommandBunker(){
  const overlay = document.getElementById('commandBunker');
  if(overlay) overlay.hidden = true;
  syncOverlayScrim();
}

function renderCommandBunker(army){
  const unlocks  = army.detachment_unlocks  || [];
  const excludes = army.detachment_excludes || [];
  const list = (label, arr)=> arr.length
    ? `<div class="ab-detlist"><span class="ab-detlist-label">${label}:</span> ${arr.map(esc).join(', ')}</div>` : '';
  const detRulesBody = renderCbRuleList(army.detachment_rules)
    + ((unlocks.length||excludes.length) ? `<div class="ab-detrule-meta">${list('Unlocks',unlocks)}${list('Excludes',excludes)}</div>` : '');
  return `
    <div class="po-overlay-head">
      <h2 class="po-overlay-title">Command Bunker</h2>
      <button class="po-close" type="button" onclick="closeCommandBunker()" aria-label="Close" title="Close">&times;</button>
    </div>
    <div class="po-body">
      ${cbSection('Datasheets', 'cbDatasheets', `<div id="cbDatasheetsBody"><p class="ab-rp-hint">Loading&hellip;</p></div>`, true)}
      ${cbSection('Stratagems', 'cbStratagems', renderCbStratagems(army))}
      ${cbSection('Detachment Rules', 'cbDetRules', detRulesBody)}
      ${cbSection('Army Rules', 'cbArmyRules', renderCbRuleList((army.army_rules||[]).map(r=>({name:r.name, description:r.body_text}))))}
    </div>`;
}

function cbSection(title, id, bodyHtml, openByDefault){
  return `<div>
      <button class="cb-head" type="button" onclick="toggleCbSection(this)">
        <span>${esc(title)}</span><span class="cb-chev">${openByDefault?'&#9652;':'&#9662;'}</span>
      </button>
      <div class="cb-section" id="${id}" ${openByDefault?'':'hidden'}>${bodyHtml}</div>
    </div>`;
}

export function toggleCbSection(btn){
  const body = btn.nextElementSibling;
  const chev = btn.querySelector('.cb-chev');
  if(!body) return;
  const opening = body.hidden;
  body.hidden = !opening;
  if(chev) chev.innerHTML = opening ? '&#9652;' : '&#9662;';
}

function renderCbRuleList(rules){
  if(!rules || !rules.length) return `<p class="ab-rp-hint">None.</p>`;
  return `<div class="ab-card ab-detrule-card" style="padding:14px 16px">
      ${rules.map(r=>`<div class="ab-detrule">
          ${r.name?`<div class="ab-detrule-name">${esc(r.name)}</div>`:''}
          <div class="ab-detrule-body">${esc(r.description||'')}</div>
        </div>`).join('')}
    </div>`;
}

// `phases` is a JSON array string (e.g. '["Command","Fight"]'); a stratagem
// renders under every phase it lists, not just the first, since that's how
// it'd actually be looked up mid-game.
function stratPhases(s){
  try{ const p = JSON.parse(s.phases||'[]'); return Array.isArray(p) && p.length ? p : ['Other']; }
  catch(e){ return ['Other']; }
}

function renderCbStratagems(army){
  const all = [...(army.stratagems||[]), ...(army.core_stratagems||[])];
  if(!all.length) return `<p class="ab-rp-hint">No stratagems available.</p>`;
  const byPhase = {};
  all.forEach(s=>{ stratPhases(s).forEach(p=>{ (byPhase[p]=byPhase[p]||[]).push(s); }); });
  const phases = Object.keys(byPhase).sort((a,b)=>{
    const ia = STRAT_PHASE_ORDER.indexOf(a), ib = STRAT_PHASE_ORDER.indexOf(b);
    return (ia<0?99:ia) - (ib<0?99:ib);
  });
  return phases.map(p=>`
    <div class="cb-phase-head">${esc(p)} Phase</div>
    ${byPhase[p].map(s=>cbStratPill(s,p)).join('')}`).join('');
}

function cbStratPill(s, phase){
  const catClass = STRAT_PILL_CLASS[s.category] || 'strat-pill-wargear';
  const uid = ('cbStrat-'+s.id+'-'+phase).replace(/[^a-zA-Z0-9-]/g,'');
  const meta = [STRAT_CAT[s.category]||'', s.detachment_name||'Core'].filter(Boolean).join(' · ');
  const lines = [
    s.when_text?`<p><b>When:</b> ${esc(s.when_text)}</p>`:'',
    s.target_text?`<p><b>Target:</b> ${esc(s.target_text)}</p>`:'',
    s.effect_text?`<p><b>Effect:</b> ${esc(s.effect_text)}</p>`:'',
    s.restriction_text?`<p><b>Restrictions:</b> ${esc(s.restriction_text)}</p>`:'',
  ].join('');
  return `<div class="strat-pill ${catClass}" onclick="toggleStratPill(this)">
      <span class="strat-pill-name">${esc(s.name||'')}</span>
      ${s.cp_cost?`<span class="strat-pill-cp">${esc(String(s.cp_cost))}CP</span>`:''}
      <span class="strat-pill-chev">&#9662;</span>
    </div>
    <div class="strat-pill-body" id="${uid}" hidden>${meta?`<p><em>${esc(meta)}</em></p>`:''}${lines}</div>`;
}

export function toggleStratPill(el){
  const body = el.nextElementSibling;
  if(body) body.hidden = !body.hidden;
}

async function loadCbDatasheets(army){
  const box = document.getElementById('cbDatasheetsBody');
  if(!box) return;
  let units = state.unitsCache[army.faction_id];
  if(!units){
    try{ const data = await api(`/api/factions/${army.faction_id}/units?for=army-builder`); units = data.units || []; }
    catch(e){ units = []; }
    state.unitsCache[army.faction_id] = units;
  }
  const native = units.filter(u=>!u.is_ally);
  box.innerHTML = native.length ? native.map(cbDatasheetRow).join('') : `<p class="ab-rp-hint">No datasheets found.</p>`;
}

// Clicking a datasheet row opens the full card overlay (same one the roster's
// unit names open), not an inline profile expand.
function cbDatasheetRow(u){
  return `<div class="cb-ds-row" onclick="openDatasheetCard('${esc(u.id)}')" title="View datasheet card">
      <img class="uc-thumb" src="/api/units/${esc(u.id)}/image" alt="" loading="lazy">
      <span class="cb-ds-name">${esc(u.name)}</span>
      <span class="cb-ds-chev">&#9656;</span>
    </div>`;
}

export async function exportArmy(mode, btn){
  const id = state.army && state.army.id;
  if(!id) return;
  if(mode === 'copy'){
    try {
      const txt = await (await fetch(`/api/armies/${id}/export?fmt=text`)).text();
      await navigator.clipboard.writeText(txt);
      if(btn){ const o = btn.textContent; btn.textContent = 'Copied!'; setTimeout(()=>{ btn.textContent = o; }, 1500); }
    } catch(e){ alert('Copy failed: ' + e); }
    return;
  }
  const fmt = mode === 'json' ? 'json' : 'text';
  const a = document.createElement('a');
  a.href = `/api/armies/${id}/export?fmt=${fmt}`;
  a.download = '';
  document.body.appendChild(a); a.click(); a.remove();
}

/* ---- datasheet cards PDF --------------------------------------------------
   "Cards PDF" renders every distinct datasheet in the roster with the same
   renderDatasheetCard markup the lightbox uses, lays them out one-per-A4-page
   in a hidden same-origin iframe, and opens the browser's print dialog --
   "Save as PDF" there produces the card pack with crisp vector text, reusing
   style.css's .dsc-* rules rather than a second card renderer. */

export async function exportDatasheetsPdf(btn){
  if(!state.army) return;
  const units = state.army.units || [];
  if(!units.length){ alert('Add some units first — there are no datasheets to print.'); return; }
  // Distinct datasheets in roster reading order (the Force-Org section order),
  // so the printed pack matches the on-screen list top to bottom.
  const buckets = {}; FOC_ORDER.forEach(c=>buckets[c]=[]);
  units.forEach(u=>{ (buckets[u.foc_category] || buckets['Other Datasheets']).push(u); });
  const seen = new Set(), dids = [];
  FOC_ORDER.flatMap(c=>buckets[c]).forEach(u=>{
    if(u.datasheet_id && !seen.has(u.datasheet_id)){ seen.add(u.datasheet_id); dids.push(u.datasheet_id); }
  });
  const orig = btn && btn.textContent;
  if(btn){ btn.disabled = true; btn.textContent = 'Preparing…'; }
  try{
    const details = await Promise.all(dids.map(async did=>{
      if(!state.unitDetailCache[did]) state.unitDetailCache[did] = await api(`/api/units/${did}`);
      return state.unitDetailCache[did];
    }));
    await printDatasheetCards(details, state.army.name);
  }catch(e){
    alert('Could not prepare the datasheet cards: ' + (e && e.message || e));
  }finally{
    if(btn){ btn.disabled = false; btn.textContent = orig; }
  }
}

// The print document pins the card's DESKTOP layout: style.css's
// @media(max-width:760px) rules would otherwise kick in during print
// relayout (an A4 page box is ~718 CSS px wide) and reflow the card to one
// column after the fit-to-page scale was measured against two.
const PDF_DESKTOP_PIN = `
  .dsc-body{grid-template-columns:1.45fr 1fr;}
  .dsc-col-left{border-right:2px solid color-mix(in srgb,var(--dsc-primary) 58%,#8f8f8f);border-bottom:none;}
  .dsc-stat-val{width:42px;height:42px;}
  .dsc-stat-in{width:38px;height:38px;font-size:21px;}
  .dsc-name{font-size:28px;}
  .dsc-hdr{flex-direction:row;}
  .dsc-legend{position:absolute;top:68px;right:20px;transform:translateY(-50%);max-width:42%;margin-top:0;}`;

async function printDatasheetCards(details, armyName){
  document.getElementById('dsPdfFrame')?.remove();
  const frame = document.createElement('iframe');
  frame.id = 'dsPdfFrame';
  // Off-screen but with a desktop-width viewport, so the on-screen layout the
  // scale factors are measured from matches the pinned print layout.
  frame.style.cssText = 'position:fixed;right:100%;bottom:100%;width:1400px;height:1000px;visibility:hidden;';
  document.body.appendChild(frame);

  const pages = details.map(d=>
    `<div class="pdf-page"><div class="pdf-card">${renderDatasheetCard(d)}</div></div>`).join('');
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>${esc(armyName)} — Datasheets</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=EB+Garamond:ital@0;1&family=Oswald:wght@300;400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
      @page{size:A4 portrait;margin:10mm;}
      html,body{margin:0;padding:0;background:#fff;}
      *{-webkit-print-color-adjust:exact !important;print-color-adjust:exact !important;}
      /* 1mm under the 277mm printable height: at exactly 277mm, sub-pixel
         rounding overflows the page box and every card gains a blank page. */
      .pdf-page{width:190mm;height:276mm;overflow:hidden;break-after:page;margin:0 auto;display:flex;align-items:center;justify-content:center;}
      .pdf-page:last-child{break-after:auto;}
      .pdf-card{width:1160px;flex:0 0 auto;}
      .pdf-card .dsc-card{box-shadow:none;max-width:none;}
      ${PDF_DESKTOP_PIN}
    </style></head><body>${pages}</body></html>`;

  await new Promise(resolve=>{
    frame.onload = resolve;
    setTimeout(resolve, 8000);   // never hang the button if a subresource stalls
    frame.srcdoc = html;
  });
  const win = frame.contentWindow, doc = frame.contentDocument;
  try{ await doc.fonts.ready; }catch(e){ /* fonts blocked: print with fallbacks */ }
  await new Promise(r=>setTimeout(r, 300));   // let CSS masks/textures paint

  // Fit each card to its page (never upscale), centred by the page's flexbox.
  // Scaling uses `zoom` rather than transform:scale -- Chrome's print pipeline
  // drops grid content (.dsc-body/.dsc-footer) inside transformed subtrees,
  // whereas zoom participates in layout and prints faithfully.
  doc.querySelectorAll('.pdf-card').forEach(el=>{
    const pg = el.parentElement;
    el.style.zoom = Math.min(pg.clientWidth/el.offsetWidth, pg.clientHeight/el.offsetHeight, 1);
  });

  win.addEventListener('afterprint', ()=>setTimeout(()=>frame.remove(), 500));
  win.focus();
  win.print();
}

async function wireCentreInputs(army){
  // Warm the caches the Edit Roster sub-screens need (this faction's
  // detachments + the battle sizes), so they're ready the first time
  // openEditRoster() renders them.
  let dts = state.detachCache[army.faction_id];
  try{
    const [d] = await Promise.all([
      dts ? Promise.resolve(dts) : api(`/api/factions/${encodeURIComponent(army.faction_id)}/detachments`),
      ensureBattleSizes(),
    ]);
    dts = d;
  }catch(e){ dts = dts || []; }
  state.detachCache[army.faction_id] = dts;
  // The rail's Battle Size select rendered before the sizes were cached --
  // re-render the config card so it carries the full option list.
  refreshContextStrip();
}

// Fill the battle-size <select> in the right panel when its config row opens.
function fillBattleSizeSelect(army){
  const sel = document.getElementById('abBattleSize');
  if(!sel) return;
  const sizes = state.battleSizes || [];
  const cur = army.battle_size || 'Custom';
  sel.innerHTML = sizes.map(b=>
      `<option value="${esc(b.name)}" ${b.name===cur?'selected':''}>${esc(b.name)} · ${b.points_limit} pts</option>`).join('')
    + `<option value="Custom" ${cur==='Custom'?'selected':''}>Custom</option>`;
}


/* ---- right panel orchestration ------------------------------------------ */

// The right panel only ever shows a unit now -- Battle Size and Detachment
// editing moved into the Edit Roster overlay's own sub-screens.
export function selectUnit(auid){
  if(!state.army) return;
  const u = state.army.units.find(x=>x.id===auid);
  if(!u) return;
  state.rightSel = {id:auid};
  markActiveSelection();
  const rp = document.getElementById('rightPanel');
  if(rp){ rp.innerHTML = renderUnitDetail(u); wireUnitDetail(u); }
}

export function clearRight(){
  state.rightSel = null;
  markActiveSelection();
  const rp = document.getElementById('rightPanel');
  if(rp) rp.innerHTML = renderRightPlaceholder();
}

// Re-open whatever unit was selected before a full re-render (showArmy refetch).
function restoreRight(){
  const sel = state.rightSel;
  if(!sel) return clearRight();
  if(state.army.units.some(u=>u.id===sel.id)) selectUnit(sel.id);
  else clearRight();
}

function markActiveSelection(){
  const sel = state.rightSel;
  document.querySelectorAll('.uc-row').forEach(r=>r.classList.remove('is-selected'));
  if(sel) document.getElementById('au-'+sel.id)?.classList.add('is-selected');
}

/* ---- right panel: unit detail ------------------------------------------- */

// "3rd" for step_at=3 -- the ordinal a repeat selection starts paying its
// duplicate-selection surcharge from.
function ordinalWord(n){
  return n===1?'1st':n===2?'2nd':n===3?'3rd':`${n}th`;
}

function renderUnitDetail(u){
  const pts = u.points + (u.enhancement_cost||0);
  const hasWg = u.wargear_schema && u.wargear_schema.length;
  return `
    <div class="ab-rp-head">
      <h3 class="ab-rp-title">${esc(u.name)}${u.is_warlord?' <span class="au-warlord" title="Warlord">★</span>':''}</h3>
      <button class="ab-rp-close" type="button" onclick="clearRight()" title="Close">&times;</button>
    </div>
    <div class="ab-rp-body">
      <div class="ab-rp-pts"><b>${pts}</b> pts · <span class="ab-rp-role">${esc(u.role||'')}</span>${u.is_ally?` · <span class="au-ally">⚔ ${esc(u.ally_faction)}</span>`:''}</div>
      ${u.points_step_added?`<p class="ab-rp-step-note">Includes +${u.points_step_added} pts — repeat selection of this unit (from the ${ordinalWord(u.points_step.step_at)} onward each costs +${u.points_step.step_points} pts).</p>`:''}
      ${renderStatControls(u)}
      ${u.is_character?`<label class="uo-warlord-row"><span>Warlord</span><input type="checkbox" class="opt-check" data-testid="unit-warlord-toggle" ${u.is_warlord?'checked':''} onchange="toggleWarlord('${u.id}')"></label>`:''}
      ${u.can_have_enhancement?accordionSection('Enhancements', `<div id="rpEnh" data-testid="unit-enhancement-editor"></div>`):''}
      ${hasWg?accordionSection('Wargear Options', `<div class="opt-theme" data-testid="wargear-editor" id="rpWargear">${renderWargearEditor(u)}</div>`):''}
      ${renderLeaderSection(u)}
      <div class="ab-rp-section">
        <button class="ab-rp-collapse" type="button" data-testid="unit-profiles-toggle" onclick="toggleUnitProfiles('${u.datasheet_id}', this)">
          <span class="ab-rp-sec-head" style="margin:0">Profiles</span><span class="ab-rp-collapse-chev">▸</span></button>
        <div id="rpProfiles" hidden></div>
      </div>
    </div>`;
}

// Grey collapsible accordion (Enhancements / Wargear Options), open by
// default. bodyHtml owns its own ids, so this is just the chrome around it.
function accordionSection(title, bodyHtml){
  return `<div class="ab-rp-section" style="border-top:none;margin-top:0;padding-top:0">
      <button class="uo-accordion-head" type="button" onclick="toggleAccordion(this)">
        <span>${esc(title)}</span><span class="uo-accordion-chev">▾</span>
      </button>
      <div class="uo-accordion-body">${bodyHtml}</div>
    </div>`;
}

export function toggleAccordion(btn){
  const body = btn.nextElementSibling;
  const chev = btn.querySelector('.uo-accordion-chev');
  if(!body) return;
  const opening = body.hidden;
  body.hidden = !opening;
  if(chev) chev.textContent = opening ? '▾' : '▸';
}

// Squad size + an owned-from-collection reference. Ownership is informational
// only -- lists are not managed against the collection (no assignment).
function renderStatControls(u){
  const squadMin = u.squad_min || 1;
  const squadMax = u.squad_max || '';
  return `<div class="uo-squad-box">
      <label class="uo-squad-row">
        <span class="uo-squad-label">Squad Size${squadMax&&squadMax!==squadMin?` <span class="uo-squad-range">${squadMin}–${squadMax}</span>`:''}</span>
        <input class="au-size-input" data-testid="unit-size-input" type="number" min="${squadMin}" ${squadMax?`max="${squadMax}"`:''} value="${u.squad_size}"
               onchange="updateSquadSize('${u.id}',this.value)" title="Squad size">
      </label>
      <div class="au-ownership" id="au-own-${u.id}">${ownershipText(u)}</div>
    </div>`;
}

// Lazy-load the datasheet statline + weapon profiles on first expand (cached).
export async function toggleUnitProfiles(did, btn){
  const box = document.getElementById('rpProfiles');
  if(!box) return;
  const opening = box.hidden;
  box.hidden = !opening;
  const chev = btn && btn.querySelector('.ab-rp-collapse-chev');
  if(chev) chev.textContent = opening ? '▾' : '▸';
  if(opening && !box.dataset.loaded){
    box.innerHTML = `<p class="ab-rp-hint">Loading profiles…</p>`;
    let detail = state.unitDetailCache[did];
    if(!detail){
      try{ detail = await api(`/api/units/${did}`); state.unitDetailCache[did] = detail; }
      catch(e){ box.innerHTML = `<p class="ab-rp-hint">Could not load profiles.</p>`; return; }
    }
    box.innerHTML = renderProfiles(detail);
    box.dataset.loaded = '1';
  }
}

export function renderProfiles(detail){
  const models = Array.isArray(detail.models) ? detail.models
               : (detail.models && detail.models.name ? [detail.models] : []);
  const g = (m, ...ks)=>{ for(const k of ks){ if(m[k]!=null && m[k]!=='') return m[k]; } return '—'; };
  const statRow = m=>`<tr><td class="wp-nm">${esc(m.name||'')}</td>
    <td>${esc(g(m,'M'))}</td><td>${esc(g(m,'T'))}</td><td>${esc(g(m,'SV','Sv'))}</td>
    <td>${esc(g(m,'W'))}</td><td>${esc(g(m,'LD','Ld'))}</td><td>${esc(g(m,'OC'))}</td>
    <td>${esc(g(m,'INV','Inv'))}</td></tr>`;
  const statTable = models.length ? `
    <table class="wp-table"><thead><tr><th>Model</th><th>M</th><th>T</th><th>SV</th><th>W</th><th>LD</th><th>OC</th><th>INV</th></tr></thead>
    <tbody>${models.map(statRow).join('')}</tbody></table>` : '';
  const wpnRow = w=>`<tr><td class="wp-nm">${esc(w.name||'')}${w.keywords?`<span class="wp-kw">${esc(w.keywords)}</span>`:''}</td>
    <td>${esc(w.range||'')}</td><td>${esc(w.A||'')}</td><td>${esc(w.BS_WS||'')}</td>
    <td>${esc(w.S||'')}</td><td>${esc(w.AP||'')}</td><td>${esc(w.D||'')}</td></tr>`;
  const wpnTable = (title, arr)=> arr && arr.length ? `
    <div class="wp-grp">${title}</div>
    <table class="wp-table"><thead><tr><th>Weapon</th><th>Rng</th><th>A</th><th>BS/WS</th><th>S</th><th>AP</th><th>D</th></tr></thead>
    <tbody>${arr.map(wpnRow).join('')}</tbody></table>` : '';
  return (statTable + wpnTable('Ranged Weapons', detail.ranged) + wpnTable('Melee Weapons', detail.melee))
    || `<p class="ab-rp-hint">No profile data.</p>`;
}

function renderLeaderSection(u){
  let html = '';
  if(u.attached_leader_name) html += `<p class="ab-rp-hint">⮡ Led by ${esc(u.attached_leader_name)}</p>`;
  if(u.attached_to){
    html += `<button class="ab-rp-btn" type="button" onclick="detachLeader('${u.id}')">Detach from bodyguard</button>`;
  } else if(u.attach_targets && u.attach_targets.length){
    html += `<select class="ab-rp-select" data-testid="unit-leader-attach" onchange="attachLeader('${u.id}',this.value)">
        <option value="">Attach to&hellip;</option>
        ${u.attach_targets.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('')}
      </select>`;
  }
  return html ? `<div class="ab-rp-section"><div class="ab-rp-sec-head">Leader</div>${html}</div>` : '';
}

function wireUnitDetail(u){
  if(u.can_have_enhancement) fillUnitEnhancement(u);
}

async function fillUnitEnhancement(u){
  const box = document.getElementById('rpEnh');
  if(!box) return;
  let enhs = [];
  if((state.army.detachment_ids||[]).length){
    try{ enhs = await api(`/api/army-units/${u.id}/enhancements`); }catch(e){ enhs = []; }
  }
  if(!enhs.length){
    box.innerHTML = `<p class="ab-rp-hint">${(state.army.detachment_ids||[]).length?'No eligible enhancements for this unit.':'Select a detachment first.'}</p>`;
    return;
  }
  // Each enhancement is its own expand-for-rules-text card with a trailing
  // checkbox (radio-like: choosing one clears any other via chooseEnhancement).
  box.innerHTML = enhs.map(e=>{
    const checked = String(e.id)===String(u.enhancement_id);
    return `<div class="opt-row">
        <button type="button" class="opt-chev" onclick="toggleOptBody(this)">▸</button>
        <span class="opt-name">${esc(e.name)}</span>
        <span class="opt-pts">${e.cost} Points</span>
        <input type="checkbox" class="opt-check" data-enh-id="${esc(e.id)}" ${checked?'checked':''} onchange="chooseEnhancement('${u.id}',this)">
      </div>
      <div class="opt-body" hidden>${esc(e.description||'')}</div>`;
  }).join('');
}

// Radio-like selection over the enhancement .opt-row checkboxes: unchecking
// clears the enhancement, checking one clears any sibling immediately (so the
// UI never shows two ticked while the save request is in flight).
export function chooseEnhancement(auid, cb){
  const id = cb.checked ? cb.dataset.enhId : '';
  cb.closest('#rpEnh')?.querySelectorAll('.opt-check').forEach(o=>{ if(o!==cb) o.checked=false; });
  saveEnhancement(auid, id);
}

export function toggleOptBody(btn){
  const body = btn.parentElement.nextElementSibling;
  if(!body) return;
  const opening = body.hidden;
  body.hidden = !opening;
  btn.textContent = opening ? '▾' : '▸';
}

// Re-render the right panel's unit detail if `auid` is the one on screen (after a
// squad/loadout/enhancement change). NOTE: state.rightSel is `{id}` -- an old
// `.type === 'unit'` guard here never matched, so the panel silently kept stale
// points/size after every edit.
function refreshUnitDetailIfSelected(auid){
  const sel = state.rightSel;
  if(sel && sel.id === auid){
    const u = state.army.units.find(x=>x.id===auid);
    const rp = document.getElementById('rightPanel');
    if(u && rp){ rp.innerHTML = renderUnitDetail(u); wireUnitDetail(u); }
  }
}

// The army name is editable in two places: the masthead title input (always
// on screen) and the Edit Roster overlay's name field. The overlay wins while
// it's open (the masthead is behind the scrim then); note the overlay's
// content persists hidden after close, so visibility must be checked --
// reading #erName unconditionally would resurrect a stale name.
function currentArmyName(){
  const erOpen = document.getElementById('editRosterModal')?.hidden === false;
  const src = (erOpen && document.getElementById('erName'))
    || document.querySelector('input[data-testid="army-title"]');
  return (src?.value || '').trim();
}

// Battle size is editable in two places too: the rail's Configuration select
// and the Edit Roster sub-screen's select. The overlay wins while it's open;
// note #abBattleSize persists hidden after the overlay closes (same overlay-
// persistence caveat as the name field), so visibility must be checked.
function currentBattleSize(){
  const erOpen = document.getElementById('editRosterModal')?.hidden === false;
  const src = (erOpen && document.getElementById('abBattleSize'))
    || document.getElementById('abBattleSizeRail')
    || document.getElementById('abBattleSize');
  return src?.value || '';
}

export async function saveArmyMeta(){
  if(!state.army) return;
  const prevBs = state.army.battle_size || 'Custom';
  const name  = currentArmyName() || state.army.name;
  const bs    = currentBattleSize() || state.army.battle_size || 'Custom';
  const pts   = intOr(document.getElementById('abPtsLimit')?.value, state.army.points_limit);
  const dtids = state.army.detachment_ids || [];
  let res;
  try{
    res = await api(`/api/armies/${state.army.id}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, detachment_ids:dtids, battle_size:bs, points_limit:pts})});
  }catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }

  // The server is authoritative: it derives the points limit from the battle
  // size and may trim the detachment set to fit a downgraded DP budget.
  const before = JSON.stringify(state.army.detachment_ids||[]);
  const after  = JSON.stringify(res.detachment_ids||[]);
  const detachmentChanged = before !== after;
  state.army.name                    = name;
  state.army.battle_size             = res.battle_size;
  state.army.points_limit            = res.points_limit;
  state.army.detachment_ids          = res.detachment_ids || [];
  state.army.detachment_id           = res.detachment_id || '';
  state.army.detachment_points_used  = res.detachment_points_used || 0;
  state.army.enhancement_limit       = res.enhancement_limit;
  state.army.duplicate_unit_limit    = res.duplicate_unit_limit;
  state.army.detachment_points_limit = res.detachment_points_limit;
  state.army.total_points            = res.total_points;
  state.army.validation              = res.validation;
  breadcrumb.querySelector('.cur').textContent = name;

  if(detachmentChanged || res.battle_size !== prevBs){
    // Detachment set trimmed on a downgrade, or the battle size changed (which
    // moves the points limit + DP budget) — refetch so the roster, rule/
    // stratagem content, chips and any stripped enhancements all stay consistent.
    await showArmy(state.army.id);
    refreshEditRosterIfOpen();
    return;
  }
  const titleEl = document.querySelector('[data-testid="army-title"]');
  if(titleEl){ if('value' in titleEl) titleEl.value = name; else titleEl.textContent = name; }
  const coloEl = document.getElementById('abColophon');
  if(coloEl) coloEl.innerHTML = renderColophon(state.army);
  const limEl = document.getElementById('ptsLimit');
  if(limEl) limEl.textContent = state.army.points_limit;
  updatePointsBar();
  refreshValidation();
  refreshContextStrip();   // battle-size row + pts limit live in the config card
  refreshMastStats();
}

// Sidebar battle-size change: reveal the points input only for Custom, then
// persist. The server re-derives the DP budget and trims the detachment set if
// it no longer fits; saveArmyMeta refetches when that happens.
export function onAbBattleSize(){
  const bs = document.getElementById('abBattleSize')?.value || 'Custom';
  const ptsField = document.getElementById('abPtsField');
  if(ptsField) ptsField.hidden = bs !== 'Custom';
  saveArmyMeta();
}

/* ---- detachment set (Detachment Points) --------------------------------- */

// Add / remove mutate the in-memory set then persist. Because a detachment
// brings its own rules, enhancements and stratagems, the whole army is
// re-fetched and re-rendered after the change.
// Click a detachment card's name to toggle it on/off (replaces the old
// "+ Add detachment" <select>, which had no on-card way to remove one either).
export function toggleDetachmentCard(id){
  if(!id || !state.army) return;
  const ids = state.army.detachment_ids || (state.army.detachment_ids = []);
  if(ids.includes(id)) return removeDetachment(id);
  ids.push(id);
  commitDetachments();
}

export function removeDetachment(id){
  if(!state.army) return;
  state.army.detachment_ids = (state.army.detachment_ids||[]).filter(x=>x!==id);
  commitDetachments();
}

// showArmy() rebuilds #view, which #editRosterModal lives outside of (it's a
// separate overlay so its own sub-screen survives a roster refetch) -- so
// every caller that triggers a refetch while the modal might be open also
// re-renders it in place, on whatever sub-screen the user was on.
function refreshEditRosterIfOpen(){
  const overlay = document.getElementById('editRosterModal');
  if(overlay && !overlay.hidden) renderEditRosterInto(state.army);
}

async function commitDetachments(){
  if(!state.army) return;
  let res;
  try{
    res = await api(`/api/armies/${state.army.id}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({detachment_ids: state.army.detachment_ids})});
  }catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }
  await showArmy(state.army.id);
  refreshEditRosterIfOpen();
}

/* ---- validation --------------------------------------------------------- */

const VAL_META = {
  ok:   {cls:'ab-val-ok',   icon:'✓'},
  warn: {cls:'ab-val-warn', icon:'⚠'},
  err:  {cls:'ab-val-err',  icon:'✗'},
  info: {cls:'ab-val-info', icon:''},
};

// Render the server-computed validation rows ({level, code, message, auid?}).
// The renderer keys off `level` only, so later phases add new codes without
// changes. Unit-scoped rows carry `auid` and render as jump-to-unit buttons,
// so a problem at the bottom of the page navigates to the row that caused it.
export function renderValidation(army){
  const rows = army.validation || [];
  if(!rows.length) return `<div class="ab-val-clean">This roster is legal for matched play.</div>`;
  return rows.map(r=>{
    const m = VAL_META[r.level] || VAL_META.info;
    const inner = `${m.icon?m.icon+' ':''}${esc(r.message)}`;
    if(r.auid && (state.army?.units||[]).some(u=>u.id===r.auid))
      return `<button type="button" class="ab-val-row ab-val-link ${m.cls}" title="Go to unit" onclick="jumpToUnit('${esc(r.auid)}')">${inner}<span class="ab-val-go">&#8599;</span></button>`;
    return `<div class="ab-val-row ${m.cls}">${inner}</div>`;
  }).join('');
}

// Select the unit in the right panel and scroll the window to its roster row
// (scroll math offset below the sticky chrome; never scrollIntoView).
export function jumpToUnit(auid){
  selectUnit(auid);
  const el = document.getElementById('au-'+auid);
  if(!el) return;
  const chrome = document.querySelector('.rl-chrome');
  const y = el.getBoundingClientRect().top + window.scrollY - ((chrome?chrome.offsetHeight:122) + 8);
  window.scrollTo({top:Math.max(0,y), behavior:'smooth'});
  el.classList.remove('rl-flash');
  requestAnimationFrame(()=>el.classList.add('rl-flash'));
  setTimeout(()=>el.classList.remove('rl-flash'), 1700);
}

export function refreshValidation(){
  // Re-render the whole card (not just the rows): the Battle-Ready / Muster
  // Issues header and its green/rust state track the row levels.
  const card = document.getElementById('validationCard');
  if(card && state.army) card.outerHTML = renderValidationCard(state.army);
}

/* ---- points helpers ----------------------------------------------------- */

export function refreshPointsTotal(){
  if(!state.army) return;
  const total = state.army.units.reduce((s,u)=>(u.points||0)+(u.enhancement_cost||0)+s, 0);
  state.army.total_points = total;
  updatePointsBar();
}

export function updatePointsBar(){
  if(!state.army) return;
  const army = state.army;
  const usedEl = document.getElementById('ptsUsed');
  if(usedEl) usedEl.textContent = army.total_points;
  const limEl = document.getElementById('ptsLimit');
  if(limEl) limEl.textContent = army.points_limit;
  const warnEl = document.getElementById('hudWarn');
  if(warnEl) warnEl.hidden = !hudHasIssues(army);
  // Manual HUD extras: over-limit tint, progress-bar width, status line, the
  // strip readout and the roster colophon all track the same totals live.
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  document.getElementById('hudPill')?.classList.toggle('is-over', over);
  const fillEl = document.getElementById('hudBarFill');
  if(fillEl) fillEl.style.width = hudPct(army) + '%';
  const noteEl = document.getElementById('hudNote');
  if(noteEl) noteEl.textContent = hudNote(army);
  updateStripPts(army);
  const coloEl = document.getElementById('abColoPts');
  if(coloEl) coloEl.textContent = `${army.total_points} / ${army.points_limit}`;
}

// Apply the {total_points, validation} a mutation endpoint returns, then repaint
// the points bar and validation card from that authoritative server state.
export function applyServerState(res){
  if(!state.army || !res) return;
  if(res.total_points !== undefined && res.total_points !== null)
    state.army.total_points = res.total_points;
  if(res.validation) state.army.validation = res.validation;
  updatePointsBar();
  refreshValidation();
  refreshContextStrip();   // live budgets (enhancements used, detachment DP)
  refreshQuickList();      // rail quick list tracks add/remove/size/warlord
  refreshStripChips();     // FOC chip counts in the sticky strip
  refreshMastStats();      // masthead "N units · M models" sub-line
}

/* ---- roster rendering --------------------------------------------------- */

function focSlug(cat){ return cat.replace(/\s+/g,'-').toLowerCase(); }

// All 4 Force-Org sections always render (matching the reference app, which
// shows e.g. an empty "Dedicated Transports" with just a "+" rather than
// hiding the section). Each section's "+" opens the picker pre-scoped to
// that category; a unit's category is never a player choice.
export function renderRoster(units, accent){
  units = units || [];
  // Attached characters render nested under their bodyguard, not as standalone
  // rows - a Leader plus any number of support characters, so a list each.
  const leaderFor = {};
  units.forEach(u=>{ if(u.attached_to) (leaderFor[u.attached_to] = leaderFor[u.attached_to] || []).push(u); });
  const standalone = units.filter(u=>!u.attached_to);
  const groups = {};
  FOC_ORDER.forEach(cat=>groups[cat]=[]);
  standalone.forEach(u=>{ const cat=u.foc_category||'Other Datasheets'; (groups[cat]=groups[cat]||groups['Other Datasheets']).push(u); });
  return FOC_ORDER.map((cat, i)=>{
    const list = groups[cat];
    const pts = list.reduce((s,u)=>s+(u.points||0)+(u.enhancement_cost||0), 0);
    const empty = !list.length
      ? `<div class="foc-empty">Nothing mustered here yet &mdash; <a href="#" onclick="event.preventDefault();openUnitPicker('${esc(cat)}')">add a unit</a>.</div>` : '';
    return `
    <div class="foc-section" id="foc-${focSlug(cat)}" data-testid="foc-section-${focSlug(cat)}">
      <div class="foc-section-head">
        <span class="foc-section-num">0${i+1}</span>
        <span class="foc-section-name">${esc(cat)}</span>
        <span class="foc-section-pts">${pts?`${pts} points`:''}</span>
        <button class="foc-add-btn" type="button" data-testid="foc-add-${focSlug(cat)}" title="Add to ${esc(cat)}" onclick="openUnitPicker('${esc(cat)}')">+</button>
      </div>
      ${empty}
      ${list.map(u=>armyUnitRow(u,accent)
        + (leaderFor[u.id]||[]).map(l=>`<div class="au-nested">${armyUnitRow(l,accent)}</div>`).join('')).join('')}
    </div>`;
  }).join('');
}

function compLine(comp){
  if(!comp || !comp.length) return '';
  // Smallest count first → the single leader/character reads before the troops,
  // and the order stays stable across brackets (tiers list models inconsistently).
  return [...comp].sort((a,b)=>a.count-b.count)
    .map(c=>`${c.count}× ${esc(c.model)}`).join(' · ');
}

// "Aspiring Champion — Bolt pistol, Boltgun · Legionary — 9 Boltgun, Chaos Icon"
// -> one bullet per "·"-separated mini-group (resolved_loadout() in wargear.py
// already groups by miniature, so this needs no further structuring).
function summaryBullets(summary){
  return (summary||'').split(' · ').map(s=>s.trim()).filter(Boolean);
}

// Ownership is a reference, not an allocation: how many of this model are in
// the collection vs. the squad size fielded here.
function ownershipDot(u){
  if(u.owned_count===0) return 'is-none';
  if(u.owned_count<u.squad_size) return 'is-warn';
  return '';
}

function ownershipText(u){
  if(u.owned_count===0) return `<span class="own-none">None in collection</span>`;
  if(u.owned_count>=u.squad_size) return `<span class="own-ok">✓ ${u.owned_count} in collection</span>`;
  return `<span class="own-warn">⚠ ${u.owned_count} in collection — ${u.squad_size-u.owned_count} short of this squad</span>`;
}

// Inline ⚠ on a roster row whose wargear selection is currently illegal --
// previously the only trace was a message in the validation card at the very
// bottom of the page, with nothing marking the unit itself.
function unitWarnBadge(u){
  const v = u.wargear_violations || [];
  if(!v.length) return '';
  const tip = v.map(x=>x.message||'').filter(Boolean).join('\n');
  return `<span class="uc-row-warn" title="${esc(tip)}">⚠</span>`;
}

function kebabMenu(u){
  const auid = u.id;
  return `<div class="uc-kebab-wrap" onclick="event.stopPropagation()">
      <button class="uc-kebab" type="button" title="More actions" onclick="toggleKebabMenu(this)">&#8942;</button>
      <div class="uc-kebab-menu" hidden>
        <button type="button" onclick="duplicateArmyUnit('${auid}')">Duplicate</button>
        ${u.attached_to?`<button type="button" onclick="detachLeader('${auid}')">Remove from attached unit</button>`:''}
        <button type="button" class="is-danger" onclick="removeArmyUnit('${auid}')">Delete</button>
      </div>
    </div>`;
}

export function toggleKebabMenu(btn){
  const menu = btn.nextElementSibling;
  const opening = menu.hidden;
  closeAllKebabMenus();
  if(menu) menu.hidden = !opening;
}

function closeAllKebabMenus(){
  document.querySelectorAll('.uc-kebab-menu').forEach(m=>m.hidden=true);
}
document.addEventListener('click', closeAllKebabMenus);

// NOTE: squad-size / assigned-from-collection stay inline here for now (the
// reference app has no collection-tracking equivalent, so there's no screen
// of theirs to place them in) -- they move into the unit-options right panel
// once it grows Enhancements/Wargear Options accordions of its own.
// Squad size / assigned-from-collection live in the unit-options right panel
// (renderStatControls) now, reached via this row's body click -- the row
// itself only needs a lightweight ownership indicator (the dot), not the
// full controls.
// Manual "roster sheet" unit card: an olive header band (name button -> the
// datasheet-card overlay, warlord/leader/ally chips, green pts pill) over a
// paper body (thumb + role/composition + wargear bullets). Every id the
// mergeUnit updater targets (au-, au-pts-, au-warn-, au-comp-, au-role-,
// au-enh-line-) and the unit-row/ally-badge testids are unchanged; the body
// click still opens the unit in the right options panel.
export function armyUnitRow(u, accent){
  const auid = u.id;
  const pts  = u.points + (u.enhancement_cost||0);
  const bodyguard = u.attached_to && state.army?.units.find(x=>x.id===u.attached_to);

  return `<div class="uc-row" data-testid="unit-row" id="au-${auid}">
    <div class="uc-band">
      <span class="uc-owned-dot ${ownershipDot(u)}" title="${esc(ownershipText(u).replace(/<[^>]+>/g,''))}"></span>
      <span class="uc-name">
        <span class="uc-name-link" title="View datasheet card" onclick="event.stopPropagation();openDatasheetCard('${u.datasheet_id}')">${esc(u.name)}</span>${u.is_warlord?' <span class="au-warlord" title="Warlord">★ Warlord</span>':''}${u.is_ally?` <span class="au-ally" data-testid="ally-badge" title="Allied: ${esc(u.ally_faction)}">⚔ ${esc(u.ally_faction)}</span>`:''}${u.attached_leader_name?` <span class="au-ledby" title="Led by ${esc(u.attached_leader_name)}">⮡ Led by ${esc(u.attached_leader_name)}</span>`:''}
        <span id="au-warn-${auid}">${unitWarnBadge(u)}</span>
      </span>
      <span class="uc-pts-pill" id="au-pts-${auid}">${pts} pts</span>
      ${kebabMenu(u)}
    </div>
    <div class="uc-body" onclick="selectUnit('${auid}')" title="Edit this unit's options">
      <img class="uc-thumb" src="/api/units/${u.datasheet_id}/image" alt="" loading="lazy">
      <div class="uc-body-text">
        <div class="au-role" id="au-role-${auid}">${esc(u.role)}${u.composition&&u.composition.length>1?` · ${compLine(u.composition)}`:''}</div>
        <span class="uc-wg-kicker">Wargear</span>
        <ul class="uc-bullets" id="au-comp-${auid}">${summaryBullets(u.loadout_summary).map(b=>`<li>${esc(b)}</li>`).join('')}</ul>
        ${bodyguard?`<div class="uc-attached-tag">Attached to <b>${esc(bodyguard.name)}</b></div>`:''}
        <div id="au-enh-line-${auid}">${u.enhancement_name?`<div class="uc-attached-tag">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>`:''}</div>
      </div>
    </div>
  </div>`;
}

// Re-add the same datasheet at the same squad size, then copy its loadout (if
// customized) onto the new copy. Reuses the existing add/patch endpoints --
// no backend change needed for "Duplicate".
export async function duplicateArmyUnit(auid){
  const u = state.army?.units.find(x=>x.id===auid);
  if(!u) return;
  let res;
  try{ res = await api(`/api/armies/${state.army.id}/units`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({datasheet_id:u.datasheet_id, squad_size:u.squad_size})}); }
  catch(e){ return; }
  if(!res || !res.ok) return;
  let unit = res.unit;
  if(u.loadout && Object.keys(u.loadout).length){
    let res2;
    try{ res2 = await api(`/api/army-units/${unit.id}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({loadout:u.loadout})}); }
    catch(e){ res2 = null; }
    if(res2 && res2.ok) unit = res2.unit;
  }
  state.army.units.push(unit);
  const body = document.getElementById('rosterBody');
  if(body) body.innerHTML = renderRoster(state.army.units, state.army.accent);
  applyServerState(res);
}

/* ---- squad / assign updates --------------------------------------------- */

export async function updateSquadSize(auid, val){
  const size = Math.max(1, intOr(val, 1));
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({squad_size:size})}); }
  catch(e){ return; }
  if(!res || !res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
  refreshUnitDetailIfSelected(auid);   // squad size rescales bulk wargear in the editor
}

/* ---- enhancement editor ------------------------------------------------- */

export async function saveEnhancement(auid, enhId){
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({enhancement_id:enhId})}); }
  catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }
  mergeUnit(auid, res.unit);   // updates the centre row's enhancement line + points
  applyServerState(res);
  refreshUnitDetailIfSelected(auid);
}

/* ---- warlord ------------------------------------------------------------ */

// Toggle Warlord on a Character. The server keeps a single Warlord per army and
// reports `cleared_warlord_auid` so we can drop the previous ★ without a re-fetch.
export async function toggleWarlord(auid){
  const u = state.army?.units.find(x=>x.id===auid);
  if(!u) return;
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({is_warlord: !u.is_warlord})}); }
  catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }
  if(res.cleared_warlord_auid){
    const prev = state.army.units.find(x=>x.id===res.cleared_warlord_auid);
    if(prev) prev.is_warlord = false;
    setWarlordVisual(res.cleared_warlord_auid, false);
    refreshUnitDetailIfSelected(res.cleared_warlord_auid);
  }
  u.is_warlord = !!res.unit.is_warlord;
  setWarlordVisual(auid, u.is_warlord);
  applyServerState(res);
  refreshUnitDetailIfSelected(auid);
}

function setWarlordVisual(auid, on){
  const row = document.getElementById(`au-${auid}`);
  if(!row) return;
  const nameEl = row.querySelector('.uc-name');
  const badge = nameEl && nameEl.querySelector('.au-warlord');
  if(on && nameEl && !badge) nameEl.insertAdjacentHTML('beforeend', ' <span class="au-warlord" title="Warlord">★</span>');
  else if(!on && badge) badge.remove();
}

/* ---- leader attachment -------------------------------------------------- */

// Attach / detach changes nesting and every other leader's eligible targets, so we
// re-fetch + re-render the whole army rather than patch individual rows.
export async function attachLeader(auid, bodyguardAuid){
  if(!bodyguardAuid) return;
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({attached_to: bodyguardAuid})}); }
  catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }
  showArmy(state.army.id);
}

export async function detachLeader(auid){
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({attached_to: ''})}); }
  catch(e){ return; }
  if(!res || !res.ok) return;
  showArmy(state.army.id);
}

/* ---- wargear editor ----------------------------------------------------- */

// Option label: name + points delta. (Weapon stats deliberately NOT shown
// here -- the Profiles section below and the picker's inline preview cover
// that; the owner wants the option list itself lean.)
function wgOptLabel(did, label, points){
  return `<span class="wg-opt-label">${esc(label)}${points?` <em>+${points} pts</em>`:''}</span>`;
}

// The −/N/+ count control that replaces bare <input type=number> spinners:
// big tap-target buttons either side of a (still typeable) number. The input
// keeps its original classes/data-*/onchange, so every existing handler path
// (setWargearStep / setWargearSlot / setWargearBundleCount) works unchanged --
// wgNudge just edits the value and fires the same change event.
function wgCount(cls, attrs, value, min, max){
  return `<span class="wg-count">
    <button type="button" class="wg-nudge" onclick="wgNudge(this,-1)" aria-label="Fewer">&minus;</button>
    <input type="number" class="wg-num ${cls}" min="${min}" ${max!=null&&max!==''?`max="${max}"`:''} value="${value}" ${attrs}>
    <button type="button" class="wg-nudge" onclick="wgNudge(this,1)" aria-label="More">+</button>
  </span>`;
}

export function wgNudge(btn, d){
  const input = btn.parentElement.querySelector('input.wg-num');
  if(!input) return;
  const min = input.min !== '' ? parseInt(input.min,10) : 0;
  const max = input.max !== '' ? parseInt(input.max,10) : Infinity;
  const cur = parseInt(input.value,10) || 0;
  const v = Math.max(min, Math.min(max, cur + d));
  if(v === cur) return;
  input.value = v;
  input.dispatchEvent(new Event('change'));   // runs the input's own onchange handler
}

function limitedCap(limits, size){
  const app = (limits||[]).filter(l=>(l.per_models||0) <= size);
  if(!app.length) return 0;
  return app.reduce((b,l)=>((l.per_models||0) >= (b.per_models||0) ? l : b)).max_choices || 0;
}

// ---- weapon arrays (replace_any) -----------------------------------------
// A sub-pool is one miniature's set of weapon mounts. slot_count = the sum of the
// current counts over its options (the server keeps pool+alternatives balanced to
// the number of mounts). Small pools render as per-slot <select>s (the user picks
// each mount); large pools render alternative steppers + a derived-pool readout.
function renderArraySub(u, g, sub, sel){
  const opts   = sub.options || [];
  const counts = {}; opts.forEach(o=>counts[o.key] = sel[o.key]||0);
  const slots  = opts.reduce((s,o)=>s+counts[o.key], 0);
  const keysAttr  = esc(JSON.stringify(opts.map(o=>o.key)));
  const miniLabel = (g.minis||[]).length>1 ? `<div class="wg-array-mini">${esc(sub.miniature)}</div>` : '';
  let body;
  if(slots<=6){
    // lay the counts across slots in a stable option order, then a <select> each
    const layout = [];
    opts.forEach(o=>{ for(let i=0;i<counts[o.key];i++) layout.push(o.key); });
    const optTags = sk => opts.map(o=>
      `<option value="${esc(o.key)}" ${o.key===sk?'selected':''}>${esc(o.item)}${o.points?` (+${o.points})`:''}</option>`).join('');
    const selects = layout.map(sk=>
      `<select class="wg-slot" data-keys='${keysAttr}' onchange="setWargearSlot('${u.id}',this)">${optTags(sk)}</select>`).join('');
    body = `<div class="wg-slots">${selects||'<span class="wg-cap">no mounts</span>'}</div>`;
  }else{
    const alts  = opts.filter(o=>!o.is_pool);
    const pools = opts.filter(o=>o.is_pool);
    const steppers = alts.map(o=>
      `<div class="wg-stepper">${wgOptLabel(u.datasheet_id, o.item, o.points)}`+
      wgCount('wg-arr-step', `data-key="${esc(o.key)}" data-keys='${keysAttr}' onchange="setWargearSlot('${u.id}',this)"`,
              counts[o.key], 0, slots)+
      `</div>`).join('');
    const poolTxt = pools.map(o=>`${counts[o.key]} ${esc(o.item)}`).join(' · ');
    body = `<div class="wg-cap">${slots} mounts — ${poolTxt||'—'}</div>${steppers}`;
  }
  return `<div class="wg-array-sub">${miniLabel}${body}</div>`;
}

// Multi-item arrays: each model of the type independently owns a whole-loadout
// bundle-index key (@b|spec|mini|model), but nothing about that mechanism
// actually requires showing it per-model -- a model's *bundle index* is all
// that matters, regardless of how many weapon keys that bundle sets, so this
// aggregates to one 0..N stepper per surviving bundle (summing to the squad's
// model count) instead of N near-identical dropdowns, matching the reference
// app's "N models w/ X" controls. Some bundle options duplicate a weapon that
// already has its own capped card elsewhere (wargear_schema flags these
// `redundant`); those are omitted as *new* picks so the same weapon isn't
// offered in two places, but a model's current pick stays visible (its own
// stepper) even if it's since become redundant, so an existing selection never
// silently disappears.
function renderModelsSub(u, g, sub){
  const sel  = u.loadout || {};
  const comp = {}; (u.composition||[]).forEach(c=>comp[c.model]=c.count);
  const n = comp[sub.miniature] || 0;
  const defIdx = sub.default_idx;
  const bk = i => '@b|'+g.spec_idx+'|'+sub.miniature+'|'+i;
  const curs = []; for(let i=0;i<n;i++){ const v = parseInt(sel[bk(i)],10); curs.push(isNaN(v)?defIdx:v); }
  const counts = {}; curs.forEach(c=>counts[c]=(counts[c]||0)+1);
  // A linked capped card ("For every 5 models… boltgun can be replaced…")
  // consumes pool weapons during server settlement WITHOUT touching the @b
  // picks -- the consumed models still read as default-bundle picks here.
  // Compare the pool count the picks imply (Σ pool_uses) against the settled
  // selection: the shortfall is how many models that card has spoken for.
  // Show them as gone from the default row and cap every stepper at the
  // models genuinely available to this array.
  const byIdx = {}; sub.bundles.forEach(b=>{ byIdx[b.idx]=b; });
  const implied = {};
  curs.forEach(c=>Object.entries((byIdx[c]||{}).pool_uses||{})
    .forEach(([k,q])=>{ implied[k]=(implied[k]||0)+q; }));
  let consumed = 0;
  Object.entries(implied).forEach(([k,q])=>{ consumed = Math.max(consumed, q-(sel[k]||0)); });
  consumed = Math.min(consumed, counts[defIdx]||0);
  if(consumed) counts[defIdx] -= consumed;
  const avail = n - consumed;
  const keepable = sub.bundles.filter(b=>!b.redundant || (counts[b.idx]||0)>0);
  if(keepable.length<=1) return '';
  const idxList = esc(JSON.stringify(keepable.map(b=>b.idx)));
  const label = (g.minis||[]).length>1 ? `<div class="wg-array-mini">${esc(sub.miniature)}</div>` : '';
  const rows = keepable.map(b=>
    `<div class="wg-stepper">${wgOptLabel(u.datasheet_id, wgCap(b.label), 0)}`+
    wgCount('wg-bundle-step',
            `data-spec="${esc(g.spec_idx)}" data-mini="${esc(sub.miniature)}" data-idx="${b.idx}" `+
            `data-default-idx="${defIdx}" data-n="${n}" data-consumed="${consumed}" data-siblings='${idxList}' `+
            `onchange="setWargearBundleCount('${u.id}',this)"`,
            counts[b.idx]||0, 0, avail)+
    `</div>`).join('');
  return `<div class="wg-array-sub">${label}${rows}</div>`;
}

// A stepper's value is "how many models have bundle X"; the underlying data is
// still one bundle-index key per model, so a count change resolves to picking
// *which* models flip. Increases pull from the default bundle first (the
// flexible pool), falling back to any other non-target bundle if the default
// runs out; decreases return freed models to the default (or, when the
// default itself is the one being decreased, to the first sibling bundle).
export function setWargearBundleCount(auid, input){
  const u = state.army.units.find(x=>x.id===auid);
  if(!u) return;
  const sel = u.loadout || {};
  const specIdx = input.dataset.spec, mini = input.dataset.mini;
  const n = parseInt(input.dataset.n,10);
  const defIdx = parseInt(input.dataset.defaultIdx,10);
  const targetIdx = parseInt(input.dataset.idx,10);
  const siblings = JSON.parse(input.dataset.siblings || '[]');
  const bk = i => '@b|'+specIdx+'|'+mini+'|'+i;
  const cur = []; for(let i=0;i<n;i++){ const v = parseInt(sel[bk(i)],10); cur.push(isNaN(v)?defIdx:v); }
  // Models a linked capped card consumed still read as default-bundle @b
  // picks (renderModelsSub subtracts them from the displayed default count) --
  // mirror that here so a minus on the default row frees exactly one model.
  const consumed = parseInt(input.dataset.consumed,10)||0;
  let have = cur.filter(c=>c===targetIdx).length;
  if(targetIdx===defIdx) have = Math.max(0, have - consumed);
  const want = Math.max(0, Math.min(n - consumed, parseInt(input.value,10)||0));
  const patch = {};
  if(want > have){
    let need = want - have;
    for(let i=0;i<n && need>0;i++){
      if(cur[i]===defIdx && targetIdx!==defIdx){ cur[i]=targetIdx; patch[bk(i)]=targetIdx; need--; }
    }
    for(let i=0;i<n && need>0;i++){
      if(cur[i]!==targetIdx){ cur[i]=targetIdx; patch[bk(i)]=targetIdx; need--; }
    }
  }else if(want < have){
    let free = have - want;
    const fallback = targetIdx===defIdx ? (siblings.find(idx=>idx!==defIdx) ?? defIdx) : defIdx;
    for(let i=0;i<n && free>0;i++){
      if(cur[i]===targetIdx){ cur[i]=fallback; patch[bk(i)]=fallback; free--; }
    }
  }
  if(Object.keys(patch).length) postLoadout(auid, patch);
}

function renderArrayGroup(u, g, sel){
  const subs = g.mode==='models'
    ? (g.minis||[]).map(sub=>renderModelsSub(u, g, sub)).join('')
    : (g.minis||[]).map(sub=>renderArraySub(u, g, sub, sel)).join('');
  return subs;
}

// "The Aspiring Champion's boltgun can be replaced with..." / "...have their
// boltgun replaced with..." -> "Boltgun". Falls back to the first item's name
// so every card still gets a usable title.
function wgCap(s){ s = (s||'').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }

// Item names can repeat within one card when a shared cap spans several
// miniatures (e.g. "Chaos Icon" once for the sergeant, once for the squad) --
// disambiguate only the labels that actually collide, so single-miniature
// groups (the common case) render unchanged.
function wgItemLabels(items){
  const counts = {};
  items.forEach(i=>{ counts[i.item] = (counts[i.item]||0)+1; });
  return items.map(i=> counts[i.item]>1 ? `${i.item} (${i.miniature})` : i.item);
}
function wgGroupTitle(g){
  const instr = g.instruction || '';
  // Weapon phrases are not just [a-z ]: "multi-melta", "2 heavy bolters",
  // "Harlequin's blade", "master-crafted power weapon and storm shield" (with
  // unicode hyphens). Capture lazily up to the verb instead of enumerating
  // characters; the possessive can also be plural ("3 models' combi-bolters").
  let m = /(?:['’]s|s['’])\s+([^.:\n]+?)\s+can (?:each )?be replaced/i.exec(instr);
  if(m) return 'Replace ' + wgCap(m[1]);
  m = /have (?:its|their)\s+([^.:\n]+?)\s+replaced with/i.exec(instr);
  if(m) return 'Replace ' + wgCap(m[1]);
  const first = (g.items && g.items[0]) || (g.minis && g.minis[0] && (g.minis[0].bundles||[])[0]);
  if(first) return 'Equip ' + wgCap(first.item || first.label || '');
  return 'Wargear Option';
}

// The rule sentence lists its weapon choices as "◦" bullets that collapse
// into one unreadable run-on line -- break each choice onto its own bulleted
// line, keeping non-bullet lines (the lead-in sentence, "* Maximum 1 per
// model." footnotes) as plain text in source order.
function wgSubMarkup(sub){
  const lines = String(sub).replace(/\r\n?/g,'\n').split('\n')
    .map(l=>l.trim()).filter(Boolean);
  const out = [];
  let inList = false;
  for(const line of lines){
    const parts = line.split(/\s*[◦○]\s*/);
    const lead = parts.shift().trim();
    if(lead){
      if(inList){ out.push('</ul>'); inList = false; }
      out.push(`<div>${esc(lead)}</div>`);
    }
    for(const p of parts){
      if(!p.trim()) continue;
      if(!inList){ out.push('<ul class="wg-sub-list">'); inList = true; }
      out.push(`<li>${esc(p.trim())}</li>`);
    }
  }
  if(inList) out.push('</ul>');
  return out.join('');
}

// Bold header + collapsible body, no per-mechanic icon/tag chrome -- matches
// the reference app's flat list style (a card's *mechanic* is obvious from
// its controls, not a decorative pill). `sub` is the verbatim rule sentence
// the card was derived from -- it's what disambiguates the three different
// "Replace Boltgun" cards a unit like Legionaries produces.
function wgCard(title, badge, contentHtml, sub){
  if(!contentHtml) return '';
  return `<div class="wg-card">
    <button type="button" class="wg-card-toggle" onclick="toggleWgCard(this)" aria-expanded="true">
      <span class="wg-card-title">${esc(title)}${badge?` <span class="wg-card-badge">${esc(badge)}</span>`:''}</span>
      <span class="wg-card-chev">▾</span>
    </button>
    <div class="wg-card-content">${sub?`<div class="wg-card-sub">${wgSubMarkup(sub)}</div>`:''}${contentHtml}</div>
  </div>`;
}

// English pluralization is unreliable in general, but the common 40k-name
// shapes are covered: "Legionary" -> "Legionaries", "Termagant" -> "Termagants".
function wgPlural(name){
  if(/[^aeiou]y$/i.test(name)) return name.slice(0,-1)+'ies';
  if(/(s|x|z|ch|sh)$/i.test(name)) return name+'es';
  return name+'s';
}

export function toggleWgCard(btn){
  const content = btn.parentElement.querySelector('.wg-card-content');
  const chev    = btn.querySelector('.wg-card-chev');
  if(!content) return;
  content.hidden = !content.hidden;
  if(chev) chev.textContent = content.hidden ? '▸' : '▾';
  btn.setAttribute('aria-expanded', String(!content.hidden));
}

// (The old renderDefaultBucket "always equipped" checkbox/Default rows are
// gone -- fixed items are reported once in the "Always equipped" note at the
// bottom of the editor, per the server's loadout_setups.fixed.)

// How many "picks" a group currently accounts for, for the squad tally. A
// models-mode array always accounts for exactly one bundle per model (that's
// the whole squad, by construction); everything else is a sum of its own
// item counts. Mounts-mode arrays (vehicle hardpoints, not squads-of-models)
// are excluded -- their own mount-count readout is already self-consistent.
function groupTally(g, sel, comp){
  if(g.type==='array'){
    if(g.mode!=='models') return 0;
    return (g.minis||[]).reduce((s,m)=>s+(comp[m.miniature]||0), 0);
  }
  // A limited card linked to an array pool (linked_default_keys) swaps weapons
  // the array bucket already tallies -- the server decrements the pool weapon
  // one-for-one -- so its picks add no models of their own.
  if(g.type==='limited_per_n' && (g.linked_default_keys||[]).length) return 0;
  // A multi-item bundle ("plasma pistol AND chainsword") is one pick on one
  // model, however many weapons it grants.
  const bundles = g.option_bundles || [];
  if(bundles.length){
    const bkeys = new Set(bundles.flatMap(b=>Object.keys(b.keys)));
    const picks = bundles.reduce((n,b)=>{
      const c = (b.anchors||[]).length ? (sel[b.anchors[0]]||0)
        : Math.min(...Object.entries(b.keys).map(([k,q])=>Math.floor((sel[k]||0)/q)));
      return n + c;
    }, 0);
    return picks + (g.items||[]).reduce((s,i)=>s+(bkeys.has(i.key)?0:(sel[i.key]||0)), 0);
  }
  return (g.items||[]).reduce((s,i)=>s+(sel[i.key]||0), 0);
}

function renderGroupHtml(u, g, sel, comp, size){
  if(g.type==='array'){
    return wgCard(wgGroupTitle(g), '', renderArrayGroup(u, g, sel), g.instruction);
  }
  if(g.type==='replace_one' || g.type==='all_model'){
    const nm = ('wg'+u.id+g.items[0].key).replace(/[^a-zA-Z0-9]/g,'');
    // data-keys must also cover the Default-group item this swap displaces, or
    // setWargearRadio's zero-out patch leaves it behind alongside the new pick.
    // It also covers RIVAL groups' picks -- two swap cards can displace the
    // same default (Boss Nob: power klaw vs the kombi-weapon bundle both take
    // the big choppa), and without this the server keeps the OLD pick and
    // bounces the new one. Any row click asserts the whole contested slot.
    const linked = g.linked_default_keys||[];
    const rivalKeys = (u.wargear_schema||[]).flatMap(o =>
      o!==g && (o.type==='replace_one'||o.type==='all_model') &&
      (o.linked_default_keys||[]).some(k=>linked.includes(k))
        ? o.items.map(i=>i.key) : []);
    const gk = esc(JSON.stringify(g.items.map(i=>i.key).concat(linked, rivalKeys)));
    const title = wgGroupTitle(g);
    // The keep-default row is named after what picking it gives you back: the
    // displaced Default-group item(s) (linked_default_keys, ground truth when
    // the server resolved the link), else the weapon parsed from the title.
    // A group that displaces nothing (an additive "can be equipped with" rule,
    // e.g. the Helbrute's fist-mounted combi-bolter) gets "None" -- echoing
    // the "Equip X" fallback title here read as a duplicate weapon option.
    const defNames = {};
    (u.wargear_schema||[]).forEach(o=>{ if(o.type==='default') (o.items||[]).forEach(i=>{ defNames[i.key]=i.item; }); });
    const linkedNames = linked.map(k=>defNames[k]).filter(Boolean);
    const defaultLabel = linked.length && linkedNames.length===linked.length
      ? linkedNames.join(' and ')
      : (/^Replace\s/.test(title) ? title.replace(/^Replace\s+/, '') : 'None');
    const labels = wgItemLabels(g.items);
    const ptsOf = {}; g.items.forEach(i=>ptsOf[i.key]=i.points||0);
    const perModel = k => g.type==='all_model'
      ? (comp[(g.items.find(i=>i.key===k)||{}).miniature]||size) : 1;
    // A pick is either a single item or a multi-item bundle ("1 lascannon AND
    // 1 twin heavy bolter" is one choice); each row carries the full {key:
    // count} map it sets, so a bundle's weapons select and deselect together.
    const bundles = g.option_bundles || [];
    const bkeys = new Set(bundles.flatMap(b=>Object.keys(b.keys)));
    const rows = [{set:{}, label:defaultLabel, points:0}]
      .concat(bundles.map(b=>({
        set: Object.fromEntries(Object.entries(b.keys).map(([k,q])=>[k, q*perModel(k)])),
        label: b.label,
        points: Object.entries(b.keys).reduce((s,[k,q])=>s+q*(ptsOf[k]||0), 0),
      })))
      .concat(g.items.filter(i=>!bkeys.has(i.key)).map((i)=>({
        set: {[i.key]: perModel(i.key)},
        label: labels[g.items.indexOf(i)], points: i.points,
      })))
      .sort((a,b)=>a.label.localeCompare(b.label));
    // checked = the row whose keys are all active; default row when none is.
    const anyActive = g.items.some(i=>(sel[i.key]||0)>0);
    rows.forEach(r=>{
      const ks = Object.keys(r.set);
      r.checked = ks.length ? ks.every(k=>(sel[k]||0)>0) : !anyActive;
    });
    // partial overlaps (shared bundle members) could tick two rows -- keep
    // the one with the most keys, matching the server's pick resolution
    const winner = rows.filter(r=>r.checked).sort((a,b)=>Object.keys(b.set).length-Object.keys(a.set).length)[0];
    rows.forEach(r=>{ r.checked = r===winner; });
    const html = rows.map(r=>wgRadio(u, nm, gk, r.set, r.checked, r.label, r.points)).join('');
    // No "1/1" badge: the radio dots already say "pick exactly one", and the
    // badge read as an exhausted budget next to real 0/1-style caps.
    return wgCard(title, '', html, g.instruction);
  }
  if(g.type==='limited_per_n'){
    const cap = limitedCap(g.limits, size);
    const dup = g.duplicate_limit;
    const maxPer = dup!=null ? Math.min(cap, dup) : cap;
    const labels = wgItemLabels(g.items);
    // A cap on a single named item (e.g. "up to 1 Balefire tome") is clearer
    // titled by that item than by what it replaces -- several such cards can
    // all replace the same base weapon, and would otherwise share one title.
    const title = g.items.length===1 ? wgCap(labels[0]) : wgGroupTitle(g);
    // A single ADDITIVE item (a Chaos Icon), possibly offered to several
    // miniature types at once ("1 model can be equipped with 1 Chaos icon"
    // keys one option per miniature): instead of a bare count, list the
    // unit's current model setups and tick the one that carries it, like the
    // reference app. Needs the server's per-model kits (loadout_setups.kits)
    // to know who's who; swaps linked to a default weapon keep their steppers
    // (they change weapons, not carriers).
    if(new Set(g.items.map(i=>i.item)).size===1 && !(g.linked_default_keys||[]).length){
      const kitsMap = (u.loadout_setups||{}).kits||{};
      const totalModels = g.items.reduce((s,i)=>s+(comp[i.miniature]||0), 0);
      const kitsOk = g.items.every(i=>{
        const k = kitsMap[i.miniature];
        return Array.isArray(k) && k.length===(comp[i.miniature]||0);
      });
      if(totalModels>1 && kitsOk){
        const have = g.items.reduce((s,i)=>s+(sel[i.key]||0), 0);
        return wgCard(wgCap(g.items[0].item), `${have}/${cap}`,
                      renderPlacementTicks(u, g, kitsMap, cap, dup, sel), g.instruction);
      }
    }
    if(g.items.length===1 && cap<=1){
      const i = g.items[0];
      const html = `<label class="wg-check"><input type="checkbox" data-key="${esc(i.key)}" ${(sel[i.key]||0)>0?'checked':''} onchange="setWargearStep('${u.id}',this)">${wgOptLabel(u.datasheet_id, labels[0], i.points)}</label>`;
      return wgCard(title, '', html, g.instruction);
    }
    // One stepper per PICK: multi-item bundles ("1 plasma pistol and 1
    // Astartes chainsword") render as a single row whose count drives all of
    // the bundle's keys via its anchors; the shared/partner keys are derived
    // server-side. The badge counts picks, not weapons.
    const bundles = g.option_bundles || [];
    const bkeys = new Set(bundles.flatMap(b=>Object.keys(b.keys)));
    const ptsOf = {}; g.items.forEach(i=>ptsOf[i.key]=i.points||0);
    const count = bundles.reduce((n,b)=>n+(sel[b.anchors[0]]||0), 0)
      + g.items.reduce((n,i)=>n+(bkeys.has(i.key)?0:(sel[i.key]||0)), 0);
    const bundleRows = bundles.map(b=>{
      const pts = Object.entries(b.keys).reduce((s,[k,q])=>s+q*(ptsOf[k]||0), 0);
      return `<div class="wg-stepper">${wgOptLabel(u.datasheet_id, b.label, pts)}`+
        wgCount('', `data-anchors='${esc(JSON.stringify(b.anchors))}' onchange="setWargearStep('${u.id}',this)"`,
                sel[b.anchors[0]]||0, 0, maxPer)+
        `</div>`;
    }).join('');
    const its = g.items.map((i,idx)=> bkeys.has(i.key) ? '' :
      `<div class="wg-stepper">${wgOptLabel(u.datasheet_id, labels[idx], i.points)}`+
      wgCount('', `data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"`, sel[i.key]||0, 0, maxPer)+
      `</div>`).join('');
    return wgCard(title, `${count}/${cap}`, `<div class="wg-cap">up to ${cap} at ${size} models${dup!=null?' · no duplicates':''}</div>${bundleRows}${its}`, g.instruction);
  }
  const fallbackLabels = wgItemLabels(g.items);
  const its = g.items.map((i,idx)=>{
    if(i.input_type==='checkbox'){
      return `<label class="wg-check"><input type="checkbox" data-key="${esc(i.key)}" ${(sel[i.key]||0)>0?'checked':''} onchange="setWargearStep('${u.id}',this)">${wgOptLabel(u.datasheet_id, fallbackLabels[idx], i.points)}</label>`;
    }
    const mc = comp[i.miniature] || size;
    return `<div class="wg-stepper">${wgOptLabel(u.datasheet_id, fallbackLabels[idx], i.points)}`+
      wgCount('', `data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"`, sel[i.key]||0, 0, mc)+
      `</div>`;
  }).join('');
  return wgCard(wgGroupTitle(g), '', its, g.instruction);
}

function renderWargearEditor(u){
  const sel = u.loadout || {};
  const size = u.squad_size;
  const comp = {}; (u.composition||[]).forEach(c=>comp[c.model]=c.count);
  const schema = u.wargear_schema || [];

  // A unit with more than one miniature type (the lone Aspiring Champion AND
  // the 9 Legionaries) gets EVERY card folded under its miniature's header --
  // multi-model minis with a live tally badge -- so the scope of look-alike
  // cards ("Replace Boltgun" x3 at different scopes) is always visible.
  // Single-miniature units (most characters/vehicles) stay a flat list.
  const multiMini = Object.keys(comp).length > 1;
  const miniOf = g => g.type==='array' ? (g.minis||[])[0]?.miniature : g.miniature;
  const bucketMiniFor = g => { const m = miniOf(g); return (multiMini && m && comp[m]) ? m : null; };

  let individualHtml = '';
  const buckets = {}; // miniature -> {html, tally, count}
  const bucket = mini => buckets[mini] || (buckets[mini] = {html:'', tally:0, count:comp[mini]||0});

  schema.forEach(g=>{
    if(g.type==='default') return;   // fixed kit lives in the summary + "Always equipped" note
    const html = renderGroupHtml(u, g, sel, comp, size);
    if(!html) return;
    const bm = bucketMiniFor(g);
    if(bm){
      const b = bucket(bm);
      b.html += html;
      b.tally += groupTally(g, sel, comp);
    } else {
      individualHtml += html;
    }
  });

  // The tally badge only makes sense for multi-model minis, where the picks
  // are spread across the squad; a single model's cards get a plain header.
  // Each miniature group is its own outlined box with a tinted header bar, so
  // the Aspiring Champion's options and the Legionaries' options read as two
  // clearly separate blocks rather than one continuous list.
  const bucketHtml = Object.entries(buckets).map(([mini,b])=>{
    const multi = b.count > 1;
    const over = multi && b.tally > b.count;
    const warn = over ? ` <span class="wg-squad-warn" title="More picks than models in the unit">!</span>` : '';
    const badge = multi ? ` <span class="wg-card-badge${over?' wg-card-badge-bad':''}">${b.tally}/${b.count}</span>` : '';
    return `<div class="wg-mini-group">
      <button type="button" class="wg-card-toggle wg-mini-head" onclick="toggleWgCard(this)" aria-expanded="true">
        <span class="wg-card-title">${esc(multi?wgPlural(mini):mini)}${badge}${warn}</span>
        <span class="wg-card-chev">▾</span>
      </button>
      <div class="wg-card-content wg-mini-body">${b.html}</div>
    </div>`;
  }).join('');

  const violHtml = (u.wargear_violations && u.wargear_violations.length)
    ? `<div class="wg-violation">${u.wargear_violations.map(v=>`<div>⚠ ${esc(v.message||'')}</div>`).join('')}</div>` : '';
  // Current loadout: one line per distinct model setup ("7× Legionary —
  // Boltgun"), so mixed squads read at a glance. Items no option can ever
  // change are summarised once in the "Always equipped" note at the bottom.
  const ls = u.loadout_setups;
  let summaryHtml = '', fixedNote = '';
  if(ls){
    // Render the structured view whenever the server sent one, even with no
    // options ticked (setups empty, all kit fixed): otherwise the card flips
    // between this and the fallback format as the first option is toggled.
    if((ls.setups||[]).length){
      const lines = ls.setups.map(s=>
        `<li><b>${s.count>1?`${s.count}× `:''}${esc(s.miniature||'Model')}</b>${s.items.length?` — ${s.items.map(esc).join(', ')}`:''}</li>`).join('');
      summaryHtml = `<div class="wg-summary"><span class="wg-summary-lbl">Current loadout</span><ul>${lines}</ul></div>`;
    }
    if((ls.fixed||[]).length){
      fixedNote = `<div class="wg-fixed-note"><span class="wg-summary-lbl">Always equipped</span>
        ${ls.fixed.map(f=>`<div>${esc(f.miniature||'All models')} — ${f.items.map(esc).join(', ')}</div>`).join('')}</div>`;
    }
  } else {
    // Fallback (older cached rows without loadout_setups): aggregate bullets.
    const summary = summaryBullets(u.loadout_summary);
    summaryHtml = summary.length
      ? `<div class="wg-summary"><span class="wg-summary-lbl">Current loadout</span><ul>${summary.map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div>` : '';
  }
  return `${summaryHtml}${violHtml}${individualHtml}${bucketHtml}${fixedNote}`;
}

// `set` is the {key: count} map this row applies on top of the zeroed group
// (empty map = the keep-default row). A bundle row sets several keys at once.
function wgRadio(u, name, keysAttr, set, checked, label, points){
  return `<label class="wg-radio">
    <input type="radio" name="${name}" data-keys="${keysAttr}" data-set='${esc(JSON.stringify(set))}' ${checked?'checked':''} onchange="setWargearRadio('${u.id}',this)" class="wg-box-input">
    <span class="wg-box"></span>
    ${wgOptLabel(u.datasheet_id, label, points)}
  </label>`;
}

async function postLoadout(auid, patch){
  const wgElBefore = document.getElementById('rpWargear');
  if(wgElBefore) wgElBefore.classList.add('is-pending');
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({loadout:patch})}); }
  catch(e){ wgElBefore?.classList.remove('is-pending'); return; }
  if(!res || !res.ok){ wgElBefore?.classList.remove('is-pending'); return; }
  mergeUnit(auid, res.unit);
  applyServerState(res);
  const u = state.army.units.find(x=>x.id===auid);
  const wgEl = document.getElementById('rpWargear');   // wargear editor in right panel
  if(wgEl && u && state.rightSel && state.rightSel.id===auid) wgEl.innerHTML = renderWargearEditor(u);
  wgElBefore?.classList.remove('is-pending');
}

export function setWargearStep(auid, input){
  const v = input.type === 'checkbox' ? (input.checked ? 1 : 0) : (parseInt(input.value, 10) || 0);
  // A bundle stepper posts its anchor key(s); the server derives the shared
  // partner counts from the picks, so they're never posted directly.
  if(input.dataset.anchors){
    const patch = {};
    JSON.parse(input.dataset.anchors).forEach(a=>{ patch[a] = v; });
    postLoadout(auid, patch);
    return;
  }
  postLoadout(auid, {[input.dataset.key]: v});
}

export function setWargearRadio(auid, input){
  const keys = JSON.parse(input.dataset.keys || '[]');
  const patch = {};
  keys.forEach(k=>patch[k]=0);
  if(input.dataset.set){
    Object.entries(JSON.parse(input.dataset.set)).forEach(([k,v])=>{ patch[k] = v; });
  } else if(input.dataset.key){   // legacy shape
    patch[input.dataset.key] = parseInt(input.dataset.val||'1', 10);
  }
  postLoadout(auid, patch);
}

// One row per distinct current model setup across every miniature the item is
// offered to ("Aspiring Champion", "Legionary — Boltgun", "Legionary — Plasma
// gun"), tick = a model of that setup carries the item. Rows are built from
// the server's per-model kits, so the ticks always show where the item
// actually sits; a change posts the new count plus an
// @on|<item key>|<model index> placement hint for the model it lands on
// (or leaves).
function renderPlacementTicks(u, g, kitsMap, cap, dup, sel){
  const it = g.items[0].item;
  const eff = dup!=null ? Math.min(cap, dup) : cap;
  const total = g.items.reduce((s,i)=>{
    return s + (kitsMap[i.miniature]||[]).reduce((n,k)=>n+(k[it]||0), 0);
  }, 0);
  const rows = [];
  g.items.forEach(item=>{
    const groups = [], bySig = {};
    (kitsMap[item.miniature]||[]).forEach((kit, idx)=>{
      const rest = Object.entries(kit).filter(([k])=>k!==it)
        .map(([k,q])=>q>1?`${q}× ${k}`:k);
      // Carriers get their own row even when the rest of their kit matches a
      // free model's (an ADDITIVE item leaves the rest identical): folding
      // them together renders one already-ticked row with no way to tick the
      // 2nd+ pick of a cap>1 item.
      const sig = ((kit[it]||0)>0 ? '✓|' : '') + rest.join(', ');
      let grp = bySig[sig];
      if(!grp){ grp = {rest, idxs:[], carriers:[]}; bySig[sig]=grp; groups.push(grp); }
      grp.idxs.push(idx);
      if((kit[it]||0)>0) grp.carriers.push(idx);
    });
    groups.forEach(grp=>{
      const ticked = grp.carriers.length>0;
      const full = !ticked && total>=eff;   // cap reached: only carriers stay toggleable
      const target = ticked ? grp.carriers[0] : grp.idxs.find(i=>!grp.carriers.includes(i));
      const plural = grp.idxs.length>1 ? `${grp.idxs.length}× ` : '';
      const kitTxt = grp.rest.length ? ` <span class="wg-place-kit">— ${esc(grp.rest.join(', '))}</span>` : '';
      rows.push(`<label class="wg-check wg-place${full?' is-off':''}">
        <input type="checkbox" ${ticked?'checked':''} ${full||target==null?'disabled':''}
               data-key="${esc(item.key)}" data-on="${target!=null?target:''}"
               onchange="setWargearPlace('${u.id}',this)">
        <span class="wg-opt-label"><span>${plural}${esc(item.miniature)}${kitTxt}</span>${item.points?` <em>+${item.points} pts</em>`:''}</span>
        ${grp.carriers.length>1?`<span class="wg-card-badge">×${grp.carriers.length}</span>`:''}
      </label>`);
    });
  });
  return rows.join('');
}

// Tick/untick a placement row: bump the item count and pin (or release) the
// placement hint for the clicked row's model.
export function setWargearPlace(auid, input){
  const u = state.army.units.find(x=>x.id===auid);
  if(!u) return;
  const key = input.dataset.key;
  const idx = input.dataset.on;
  const cur = parseInt((u.loadout||{})[key], 10) || 0;
  const patch = {};
  if(input.checked){
    patch[key] = cur + 1;
    if(idx!=='') patch['@on|'+key+'|'+idx] = 1;
  }else{
    patch[key] = Math.max(0, cur - 1);
    if(idx!=='') patch['@on|'+key+'|'+idx] = 0;
  }
  postLoadout(auid, patch);
}

// Weapon-array change. For a <select> grid we re-tally every slot in the sub-pool
// and post absolute counts; for an alternative stepper we post just the changed
// alternatives and let the server re-derive the pool weapon(s).
export function setWargearSlot(auid, el){
  const sub = el.closest('.wg-array-sub');
  if(!sub) return;
  const patch = {};
  if(el.tagName === 'SELECT'){
    JSON.parse(el.dataset.keys || '[]').forEach(k=>patch[k]=0);
    sub.querySelectorAll('select.wg-slot').forEach(s=>{ patch[s.value] = (patch[s.value]||0) + 1; });
  }else{
    sub.querySelectorAll('input.wg-arr-step').forEach(inp=>{ patch[inp.dataset.key] = parseInt(inp.value,10)||0; });
  }
  postLoadout(auid, patch);
}

/* ---- remove army unit --------------------------------------------------- */

export async function removeArmyUnit(auid){
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'DELETE'}); }
  catch(e){ return; }
  const removed = state.army.units.find(u=>u.id===auid);
  state.army.units = state.army.units.filter(u=>u.id!==auid);
  // All 4 Force-Org sections stay visible even when empty (matching the
  // reference app), so a full re-render is simpler and correct here -- no
  // surgical per-row DOM removal / empty-state fallback needed.
  const body = document.getElementById('rosterBody');
  if(body) body.innerHTML = renderRoster(state.army.units, state.army.accent);
  if(state.rightSel && state.rightSel.id===auid) clearRight();
  applyServerState(res);
  // Removing one selection of a stepped datasheet shifts the duplicate-
  // selection surcharge off a remaining sibling -- refetch so the sibling
  // rows repaint with their server-priced points.
  if(removed && removed.points_step &&
     state.army.units.some(u=>u.datasheet_id===removed.datasheet_id)){
    await showArmy(state.army.id);
  }
}

/* ---- merge unit state --------------------------------------------------- */

export function mergeUnit(auid, updated){
  const idx = state.army.units.findIndex(u=>u.id===auid);
  if(idx>=0) state.army.units[idx] = {...state.army.units[idx], ...updated};

  const u   = updated;
  const pts = (u.points||0) + (u.enhancement_cost||0);

  const ptsEl = document.getElementById(`au-pts-${auid}`);
  if(ptsEl) ptsEl.textContent = `${pts} Points`;

  // Squad-size/assigned inputs and the full ownership text now live in the
  // right panel, which a subsequent refreshUnitDetailIfSelected() rebuilds in
  // full -- the row only needs its lightweight ownership dot kept in sync.
  const dotEl = document.querySelector(`#au-${auid} .uc-owned-dot`);
  if(dotEl) dotEl.className = `uc-owned-dot ${ownershipDot(u)}`;

  const warnEl = document.getElementById(`au-warn-${auid}`);
  if(warnEl) warnEl.innerHTML = unitWarnBadge(state.army.units.find(x=>x.id===auid) || u);

  const compEl = document.getElementById(`au-comp-${auid}`);
  if(compEl) compEl.innerHTML = summaryBullets(u.loadout_summary).map(b=>`<li>${esc(b)}</li>`).join('');

  // Squad-size changes move the composition split ("1× Champion · 9× Legionary").
  const roleEl = document.getElementById(`au-role-${auid}`);
  if(roleEl) roleEl.innerHTML = `${esc(u.role)}${u.composition&&u.composition.length>1?` · ${compLine(u.composition)}`:''}`;

  // Enhancement summary tag on the row (empty -> nothing rendered).
  const enhEl = document.getElementById(`au-enh-line-${auid}`);
  if(enhEl) enhEl.innerHTML = u.enhancement_name
    ? `<div class="uc-attached-tag">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>` : '';
}
