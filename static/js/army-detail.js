import { esc, api, intOr } from './utils.js';
import { state, ensureBattleSizes } from './army-state.js';
import { setBreadcrumb } from './header.js';

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

  // Two-panel layout: roster + config (centre), context-sensitive unit-options
  // detail (right). The unit picker is no longer a persistent third column --
  // it's the full-screen overlay in #unitPickerModal (unit-picker.js), opened
  // on demand from a Force-Org section's "+".
  view.innerHTML = `
    <div class="ab-detail ab-2panel" data-testid="army-detail">
      <section class="ab-centre" id="centrePanel">${renderCentre(army)}</section>
      <aside class="ab-rightpanel" id="rightPanel" data-testid="detail-panel">${renderRightPlaceholder()}</aside>
    </div>
    <div class="ab-rp-scrim" id="rpScrim" onclick="clearRight()"></div>`;

  wireCentreInputs(army);
  restoreRight();           // re-open a prior right-panel selection after a refetch
}

function renderRightPlaceholder(){
  return `<div class="ab-rp-empty" data-testid="detail-empty">
      <span class="ab-rp-empty-icon">✦</span>
      <p>Select a unit or a configuration row to edit it here.</p>
    </div>`;
}

/* ---- centre panel (roster + config) ------------------------------------- */

function renderCentre(army){
  return `
    ${renderRosterHeader(army)}
    <div id="rosterBody">${renderRoster(army.units, army.accent)}</div>
    ${renderPointsHud(army)}
    <div class="ab-card ab-validation" id="validationCard" data-testid="validation-card">
      <p class="ab-card-title">Validation</p>
      <div id="validationBody">${renderValidation(army)}</div>
    </div>`;
}

// Persistent points/validity HUD pill: sticks to the bottom of the viewport
// while the roster above it scrolls, and shows a warning half whenever the
// list has ANY validation issue (not just over points), matching the
// reference app. id="ptsUsed"/data-testid="army-points" are kept stable so
// existing live-points-update wiring (updatePointsBar) and the UI test suite
// keep working unchanged.
function renderPointsHud(army){
  const hasIssues = hudHasIssues(army);
  return `
    <div class="hud-pill" data-testid="points-hud">
      <span class="hud-warn" id="hudWarn" ${hasIssues?'':'hidden'}>&#9888;</span>
      <span class="hud-pts"><b id="ptsUsed" data-testid="army-points">${army.total_points}</b><small>/ <span id="ptsLimit">${army.points_limit}</span> POINTS</small></span>
    </div>`;
}

function hudHasIssues(army){
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  return over || (army.validation||[]).some(v=>v.level==='err'||v.level==='warn');
}

function renderRosterHeader(army){
  return `
    <div class="ab-centre-head">
      <h2 class="ab-army-title" data-testid="army-title">${esc(army.name)}</h2>
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
      </div>
    </div>`;
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

  const all = (state.detachCache[army.faction_id] || []).slice()
    .sort((a,b)=>(a.name||'').localeCompare(b.name||''));
  const cards = all.length ? all.map(d=>{
    const selected = have.has(d.id);
    const affordable = selected || (d.points_cost||0) <= remaining;
    const restrictions = d.restrictions || [];
    const expandId = `dpExpand-${esc(d.id)}`;
    const disposition = dispositionFor[d.id];
    // No per-detachment art exists -- the faction banner is the documented
    // substitute, same image bled into every card per the reference app's look.
    const artStyle = army.banner_url
      ? `style="background-image:url('${esc(army.banner_url)}')${affordable?'':';opacity:.45'}"`
      : (affordable?'':'style="opacity:.45"');
    return `<div class="dp-card ${selected?'is-selected':''}" ${artStyle}>
        ${restrictions.length?`<button type="button" class="dp-card-chev" onclick="event.stopPropagation();toggleDpExpand('${expandId}')" title="Show details">&#9662;</button>`:'<span class="dp-card-chev"></span>'}
        <span class="dp-card-name" data-testid="detachment-chip" ${affordable?`onclick="toggleDetachmentCard('${esc(d.id)}')" style="cursor:pointer"`:''}>${esc(d.name)}${selected&&disposition?` <span class="ab-detach-chip-disp" data-testid="detachment-disposition" title="Force Disposition">&#11043; ${esc(disposition)}</span>`:''}</span>
        <span class="dp-card-cost">${d.points_cost||0} DP</span>
      </div>
      ${restrictions.length?`<div class="dp-card-expand" id="${expandId}" hidden>${restrictions.map(r=>`${r.title?`<h4>${esc(r.title)}</h4>`:''}${(r.bullets||[]).map(b=>`<p>${mdBold(esc(b))}</p>`).join('')}`).join('')}</div>`:''}`;
  }).join('') : `<p class="po-empty">No detachments available for this faction.</p>`;

  return `
    <div class="dp-budget-head" data-testid="detachment-panel">
      <span class="dp-budget-label">Available Detachment Points (DP)</span>
      <span class="dp-budget-pill ${over?'is-over':''}" id="abDpBudget" data-testid="dp-budget">${budgetLabel}</span>
    </div>
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

export function openEditRoster(){
  if(!state.army) return;
  state.editRosterView = 'main';
  renderEditRosterInto(state.army);
  const overlay = document.getElementById('editRosterModal');
  if(overlay) overlay.hidden = false;
}

export function closeEditRoster(){
  const overlay = document.getElementById('editRosterModal');
  if(overlay) overlay.hidden = true;
}

export function editRosterShow(view){
  state.editRosterView = view;
  renderEditRosterInto(state.army);
}

function renderEditRosterInto(army){
  const overlay = document.getElementById('editRosterModal');
  if(!overlay) return;
  overlay.innerHTML = renderEditRoster(army);
  if(state.editRosterView === 'battlesize') fillBattleSizeSelect(army);
}

function renderEditRoster(army){
  const view = state.editRosterView || 'main';
  if(view === 'battlesize') return erSubScreen('Battle Size', renderBattleSizePanel(army));
  if(view === 'detachment') return erSubScreen('Choose Detachments', renderDetachmentPanel(army));
  return renderEditRosterMain(army);
}

function erSubScreen(title, bodyHtml){
  return `
    <div class="po-overlay-head">
      <button class="cb-back" type="button" onclick="editRosterShow('main')" aria-label="Back" title="Back">&#10094;</button>
      <h2 class="po-overlay-title">${esc(title)}</h2>
    </div>
    <div class="po-body">${bodyHtml}</div>`;
}

function renderEditRosterMain(army){
  const bs = army.battle_size || 'Custom';
  const dets = army.detachments || [];
  const detSummary = dets.length ? dets.map(d=>esc(d.name)).join(', ') : 'None selected';
  return `
    <div class="po-overlay-head">
      <button class="cb-back" type="button" onclick="closeEditRoster()" aria-label="Back" title="Back">&#10094;</button>
      <h2 class="po-overlay-title">Edit Roster</h2>
    </div>
    <div class="po-body er-body">
      <p class="er-label">Name</p>
      <input class="er-name-input" id="erName" value="${esc(army.name)}" placeholder="Army name" onchange="saveArmyMeta()">
      <p class="er-label">Army</p>
      <div class="er-faction-row">${esc(army.faction_display_name||army.faction_name||'')}</div>
      <button class="er-config-row" type="button" data-testid="er-row-battlesize" onclick="editRosterShow('battlesize')">
        <span>${esc(bs)}${army.points_limit?` &middot; ${army.points_limit} pts`:''}</span><span class="er-config-chev">&#9656;</span>
      </button>
      <button class="er-config-row" type="button" data-testid="er-row-detachment" onclick="editRosterShow('detachment')">
        <span>${esc(detSummary)}</span><span class="er-config-chev">&#9656;</span>
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
  loadCbDatasheets(state.army);
}

export function closeCommandBunker(){
  const overlay = document.getElementById('commandBunker');
  if(overlay) overlay.hidden = true;
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
      <button class="cb-back" type="button" onclick="closeCommandBunker()" aria-label="Back" title="Back">&#10094;</button>
      <h2 class="po-overlay-title">Command Bunker</h2>
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

function cbDatasheetRow(u){
  return `<div class="cb-ds-row" onclick="toggleCbDatasheet('${esc(u.id)}')">
      <img class="uc-thumb" src="/api/units/${esc(u.id)}/image" alt="" loading="lazy">
      <span class="cb-ds-name">${esc(u.name)}</span>
      <span class="cb-ds-chev">&#9656;</span>
    </div>
    <div class="cb-section" id="cbDs-${esc(u.id)}" hidden></div>`;
}

// Lazy-load the datasheet statline + weapon profiles on first expand
// (reuses the same cache + renderProfiles() the unit-options panel's
// Profiles section uses).
export async function toggleCbDatasheet(did){
  const box = document.getElementById(`cbDs-${did}`);
  if(!box) return;
  const opening = box.hidden;
  box.hidden = !opening;
  if(opening && !box.dataset.loaded){
    box.innerHTML = `<p class="ab-rp-hint">Loading&hellip;</p>`;
    let detail = state.unitDetailCache[did];
    if(!detail){
      try{ detail = await api(`/api/units/${did}`); state.unitDetailCache[did] = detail; }
      catch(e){ box.innerHTML = `<p class="ab-rp-hint">Could not load profiles.</p>`; return; }
    }
    box.innerHTML = renderProfiles(detail);
    box.dataset.loaded = '1';
  }
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
  if(rp){ rp.innerHTML = renderUnitDetail(u); wireUnitDetail(u); rp.classList.add('is-open'); }
  document.getElementById('rpScrim')?.classList.add('is-open');
}

export function clearRight(){
  state.rightSel = null;
  markActiveSelection();
  const rp = document.getElementById('rightPanel');
  if(rp) rp.innerHTML = renderRightPlaceholder();
  rp?.classList.remove('is-open'); document.getElementById('rpScrim')?.classList.remove('is-open');
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
      ${u.is_character?`<label class="uo-warlord-row"><span>Warlord</span><input type="checkbox" class="opt-check" data-testid="unit-warlord-toggle" ${u.is_warlord?'checked':''} onchange="toggleWarlord('${u.id}')"></label>`:''}
      ${u.can_have_enhancement?accordionSection('Enhancements', `<div id="rpEnh" data-testid="unit-enhancement-editor"></div>`):''}
      ${hasWg?accordionSection('Wargear Options', `<div class="opt-theme" data-testid="wargear-editor" id="rpWargear">${renderWargearEditor(u)}</div>`):''}
      ${renderStatControls(u)}
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

// Squad size + assigned-from-collection: this project's collection tracking,
// which the reference app has no equivalent screen for, so it lives here
// rather than mapping to one of the app's own sections.
function renderStatControls(u){
  const squadMin = u.squad_min || 1;
  const squadMax = u.squad_max || '';
  const owned = u.owned_count, avail = u.available_count, assigned = u.assigned_count;
  return `<div class="ab-rp-section">
      <div class="ab-rp-sec-head">Squad &amp; Collection</div>
      <div class="uo-stat-row">
        <label>Squad Size</label>
        <input class="au-size-input" data-testid="unit-size-input" type="number" min="${squadMin}" ${squadMax?`max="${squadMax}"`:''} value="${u.squad_size}"
               onchange="updateSquadSize('${u.id}',this.value)" title="Squad size">
      </div>
      ${owned>0?`<div class="uo-stat-row">
        <label>Assigned</label>
        <input class="au-assign-input" type="number" min="0" max="${avail+assigned}" value="${assigned}"
               onchange="updateAssigned('${u.id}',this.value)" title="Assigned models from collection">
        <span style="font-family:'Oswald',sans-serif;font-size:11px;color:var(--parch-dim)">/ ${owned} owned</span>
      </div>`:''}
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

function renderProfiles(detail){
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
// squad/loadout/enhancement change).
function refreshUnitDetailIfSelected(auid){
  const sel = state.rightSel;
  if(sel && sel.type === 'unit' && sel.id === auid){
    const u = state.army.units.find(x=>x.id===auid);
    const rp = document.getElementById('rightPanel');
    if(u && rp){ rp.innerHTML = renderUnitDetail(u); wireUnitDetail(u); }
  }
}

export async function saveArmyMeta(){
  if(!state.army) return;
  const prevBs = state.army.battle_size || 'Custom';
  const name  = (document.getElementById('erName')?.value||'').trim() || state.army.name;
  const bs    = document.getElementById('abBattleSize')?.value || state.army.battle_size || 'Custom';
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
  if(titleEl) titleEl.textContent = name;
  const limEl = document.getElementById('ptsLimit');
  if(limEl) limEl.textContent = state.army.points_limit;
  updatePointsBar();
  refreshValidation();
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

// Render the server-computed validation rows ({level, code, message}). The
// renderer keys off `level` only, so later phases add new codes without changes.
export function renderValidation(army){
  const rows = army.validation || [];
  if(!rows.length) return `<div class="ab-val-row ab-val-ok">✓ No issues found</div>`;
  return rows.map(r=>{
    const m = VAL_META[r.level] || VAL_META.info;
    return `<div class="ab-val-row ${m.cls}">${m.icon?m.icon+' ':''}${esc(r.message)}</div>`;
  }).join('');
}

export function refreshValidation(){
  const el = document.getElementById('validationBody');
  if(el&&state.army) el.innerHTML = renderValidation(state.army);
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
  const usedEl = document.getElementById('ptsUsed');
  if(usedEl) usedEl.textContent = state.army.total_points;
  const limEl = document.getElementById('ptsLimit');
  if(limEl) limEl.textContent = state.army.points_limit;
  const warnEl = document.getElementById('hudWarn');
  if(warnEl) warnEl.hidden = !hudHasIssues(state.army);
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
}

/* ---- roster rendering --------------------------------------------------- */

function focSlug(cat){ return cat.replace(/\s+/g,'-').toLowerCase(); }

// All 4 Force-Org sections always render (matching the reference app, which
// shows e.g. an empty "Dedicated Transports" with just a "+" rather than
// hiding the section). Each section's "+" opens the picker pre-scoped to
// that category; a unit's category is never a player choice.
export function renderRoster(units, accent){
  units = units || [];
  // Attached leaders render nested under their bodyguard, not as standalone rows.
  const leaderFor = {};
  units.forEach(u=>{ if(u.attached_to) leaderFor[u.attached_to] = u; });
  const standalone = units.filter(u=>!u.attached_to);
  const groups = {};
  FOC_ORDER.forEach(cat=>groups[cat]=[]);
  standalone.forEach(u=>{ const cat=u.foc_category||'Other Datasheets'; (groups[cat]=groups[cat]||groups['Other Datasheets']).push(u); });
  return FOC_ORDER.map(cat=>{
    const list = groups[cat];
    const pts = list.reduce((s,u)=>s+(u.points||0)+(u.enhancement_cost||0), 0);
    return `
    <div class="foc-section" data-testid="foc-section-${focSlug(cat)}">
      <div class="foc-section-head">
        <span class="foc-section-name">${esc(cat)}</span>
        ${pts?`<span class="foc-section-pts">${pts} Points</span>`:''}
        <button class="foc-add-btn" type="button" data-testid="foc-add-${focSlug(cat)}" title="Add to ${esc(cat)}" onclick="openUnitPicker('${esc(cat)}')">+</button>
      </div>
      ${list.map(u=>armyUnitRow(u,accent)
        + (leaderFor[u.id]?`<div class="au-nested">${armyUnitRow(leaderFor[u.id],accent)}</div>`:'')).join('')}
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

function ownershipDot(u){
  if(u.owned_count===0) return 'is-none';
  if(u.assigned_count<u.squad_size) return 'is-warn';
  return '';
}

function ownershipText(u){
  if(u.owned_count===0) return `<span class="own-none">Not owned — wishlist</span>`;
  if(u.assigned_count>=u.squad_size) return `<span class="own-ok">✓ ${u.assigned_count} of ${u.squad_size} assigned</span>`;
  const short = u.squad_size-u.assigned_count;
  return `<span class="own-warn">⚠ ${u.assigned_count}/${u.squad_size} assigned — need ${short} more (${u.available_count} available)</span>`;
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
export function armyUnitRow(u, accent){
  const auid = u.id;
  const pts  = u.points + (u.enhancement_cost||0);
  const bodyguard = u.attached_to && state.army?.units.find(x=>x.id===u.attached_to);

  return `<div class="uc-row" data-testid="unit-row" id="au-${auid}" style="--cardarmy:${state.army?.primary||'var(--panel)'};--cardaccent:${accent||'var(--gold)'};--cardglow:${accent||'var(--gold)'}">
    <img class="uc-thumb" src="/api/units/${u.datasheet_id}/image" alt="" loading="lazy" onclick="selectUnit('${auid}')">
    <div class="uc-body" onclick="selectUnit('${auid}')">
      <div class="uc-name">
        <span class="uc-owned-dot ${ownershipDot(u)}" title="${esc(ownershipText(u).replace(/<[^>]+>/g,''))}"></span>
        ${esc(u.name)}${u.is_warlord?' <span class="au-warlord" title="Warlord">★</span>':''}${u.is_ally?` <span class="au-ally" data-testid="ally-badge" title="Allied: ${esc(u.ally_faction)}">⚔ ${esc(u.ally_faction)}</span>`:''}${u.attached_leader_name?` <span class="au-ledby" title="Led by ${esc(u.attached_leader_name)}">⮡ ${esc(u.attached_leader_name)}</span>`:''}
      </div>
      <div class="au-role">${esc(u.role)}${u.composition&&u.composition.length>1?` · ${compLine(u.composition)}`:''}</div>
      <ul class="uc-bullets" id="au-comp-${auid}">${summaryBullets(u.loadout_summary).map(b=>`<li>${esc(b)}</li>`).join('')}</ul>
      ${bodyguard?`<div class="uc-attached-tag">Attached to <b>${esc(bodyguard.name)}</b></div>`:''}
      <div id="au-enh-line-${auid}">${u.enhancement_name?`<div class="uc-attached-tag">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>`:''}</div>
    </div>
    <div class="uc-side">
      <span class="uc-pts-pill" id="au-pts-${auid}">${pts} Points</span>
      ${kebabMenu(u)}
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
  const res  = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({squad_size:size})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
  refreshUnitDetailIfSelected(auid);   // squad size rescales bulk wargear in the editor
}

export async function updateAssigned(auid, val){
  const count = Math.max(0, intOr(val, 0));
  const res   = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({assigned_count:count})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
  refreshUnitDetailIfSelected(auid);   // assigned_count may be server-clamped
}

/* ---- enhancement editor ------------------------------------------------- */

export async function toggleEnhEditor(auid){
  const ed = document.getElementById(`au-enh-ed-${auid}`);
  if(!ed.hidden){ed.hidden=true;ed.innerHTML='';return;}
  if(!state.army) return;
  const unit = state.army.units.find(u=>u.id===auid) || {};
  // Per-unit eligible list (eligibility + uniqueness, current pick always included).
  let enhs = [];
  if(state.army.detachment_id){
    try{ enhs = await api(`/api/army-units/${auid}/enhancements`); }catch(e){ enhs = []; }
  }
  if(!enhs||!enhs.length){
    ed.innerHTML = `<p style="font-family:'EB Garamond',serif;font-size:14px;color:var(--parch-dim);margin:0">
      ${state.army.detachment_id?'No eligible enhancements for this unit.':'Select a detachment first.'}</p>`;
    ed.hidden = false;
    return;
  }
  ed.innerHTML = `
    <select onchange="saveEnhancement('${auid}',this.value)" style="margin-bottom:8px">
      <option value="">— No enhancement —</option>
      ${enhs.map(e=>`<option value="${esc(e.id)}" ${String(e.id)===String(unit.enhancement_id)?'selected':''}>
        ${esc(e.name)} (+${e.cost} pts)</option>`).join('')}
    </select>`;
  ed.hidden = false;
}

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
function renderArraySub(uid, g, sub, sel){
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
      `<select class="wg-slot" data-keys='${keysAttr}' onchange="setWargearSlot('${uid}',this)">${optTags(sk)}</select>`).join('');
    body = `<div class="wg-slots">${selects||'<span class="wg-cap">no mounts</span>'}</div>`;
  }else{
    const alts  = opts.filter(o=>!o.is_pool);
    const pools = opts.filter(o=>o.is_pool);
    const steppers = alts.map(o=>
      `<div class="wg-stepper"><span>${esc(o.item)}${o.points?` <em>+${o.points}</em>`:''}</span>`+
      `<input type="number" class="wg-arr-step" min="0" max="${slots}" value="${counts[o.key]}" `+
      `data-key="${esc(o.key)}" data-keys='${keysAttr}' onchange="setWargearSlot('${uid}',this)"></div>`).join('');
    const poolTxt = pools.map(o=>`${counts[o.key]} ${esc(o.item)}`).join(' · ');
    body = `<div class="wg-cap">${slots} mounts — ${poolTxt||'—'}</div>${steppers}`;
  }
  return `<div class="wg-array-sub">${miniLabel}${body}</div>`;
}

// Multi-item arrays: each model of the type picks a whole loadout (bundle). One
// <select> of bundle labels per model, bound to its @b|spec|mini|model key.
function renderModelsSub(u, g, sub){
  const sel  = u.loadout || {};
  const comp = {}; (u.composition||[]).forEach(c=>comp[c.model]=c.count);
  const n = comp[sub.miniature] || 0;
  const multi = (g.minis||[]).length>1;
  // No per-bundle points: the cost is a delta from the loadout it replaces, so an
  // absolute figure would mislead. The points bar reflects the true total.
  const optTags = cur => sub.bundles.map(b=>
    `<option value="${b.idx}" ${b.idx===cur?'selected':''}>${esc(b.label)}</option>`).join('');
  let rows = '';
  for(let i=0;i<n;i++){
    const bk = '@b|'+g.spec_idx+'|'+sub.miniature+'|'+i;
    const cur = parseInt(sel[bk],10)||0;
    rows += `<div class="wg-model-row"><span class="wg-model-lbl">${esc(sub.miniature)} ${i+1}</span>`+
      `<select class="wg-slot" data-key="${esc(bk)}" data-mode="models" onchange="setWargearSlot('${u.id}',this)">${optTags(cur)}</select></div>`;
  }
  return rows ? `<div class="wg-array-sub">${multi?`<div class="wg-array-mini">${esc(sub.miniature)}</div>`:''}${rows}</div>` : '';
}

function renderArrayGroup(u, g, sel){
  const subs = g.mode==='models'
    ? (g.minis||[]).map(sub=>renderModelsSub(u, g, sub)).join('')
    : (g.minis||[]).map(sub=>renderArraySub(u.id, g, sub, sel)).join('');
  return subs;
}

// "The Aspiring Champion's boltgun can be replaced with..." / "...have their
// boltgun replaced with..." -> "Boltgun". Falls back to the first item's name
// so every card still gets a usable title.
function wgCap(s){ s = (s||'').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }
function wgGroupTitle(g){
  const instr = g.instruction || '';
  let m = /['’]s\s+([a-z][a-z\s]*?)\s+can be replaced/i.exec(instr);
  if(m) return 'Replace ' + wgCap(m[1]);
  m = /have (?:its|their)\s+([a-z][a-z\s]*?)\s+replaced with/i.exec(instr);
  if(m) return 'Replace ' + wgCap(m[1]);
  const first = (g.items && g.items[0]) || (g.minis && g.minis[0] && (g.minis[0].bundles||[])[0]);
  if(first) return 'Equip ' + wgCap(first.item || first.label || '');
  return 'Wargear Option';
}

const WG_MECH = {
  replace_one:  { tag:'Either/Or Swap',  icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13l-3-3"/><path d="M20 16H7l3 3"/></svg>' },
  all_model:    { tag:'Unit-wide Swap',  icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/></svg>' },
  limited_per_n:{ tag:'Capped Option',   icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="12" cy="12" r="8.5" stroke-opacity=".3"/><circle cx="12" cy="12" r="8.5" stroke-dasharray="27 53" stroke-linecap="round" transform="rotate(-90 12 12)"/></svg>' },
  array_mounts: { tag:'Weapon Array',    icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><rect x="3" y="9" width="4" height="12" rx="1"/><rect x="10" y="4" width="4" height="17" rx="1"/><rect x="17" y="12" width="4" height="9" rx="1"/></svg>' },
  array_models: { tag:'Loadout Bundle',  icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"><path d="M12 3 21 8 12 13 3 8z"/><path d="M3 13l9 5 9-5"/></svg>' },
  choice:       { tag:'Optional',        icon:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>' },
};
function wgMechMeta(g){
  if(g.type==='array') return WG_MECH[g.mode==='models' ? 'array_models' : 'array_mounts'];
  return WG_MECH[g.type] || WG_MECH.choice;
}
function wgCard(g, title, badge, contentHtml){
  if(!contentHtml) return '';
  const meta = wgMechMeta(g);
  return `<div class="wg-card">
    <button type="button" class="wg-card-toggle" onclick="toggleWgCard(this)" aria-expanded="true">
      <span class="wg-card-title"><span class="wg-card-icon">${meta.icon}</span>${esc(title)}<span class="wg-card-tag">${esc(meta.tag)}</span>${badge?` <span class="wg-card-badge">${esc(badge)}</span>`:''}</span>
      <span class="wg-card-chev">▾</span>
    </button>
    <div class="wg-card-content">${contentHtml}</div>
  </div>`;
}

export function toggleWgCard(btn){
  const content = btn.parentElement.querySelector('.wg-card-content');
  const chev    = btn.querySelector('.wg-card-chev');
  if(!content) return;
  content.hidden = !content.hidden;
  if(chev) chev.textContent = content.hidden ? '▸' : '▾';
  btn.setAttribute('aria-expanded', String(!content.hidden));
}

function renderWargearEditor(u){
  const sel = u.loadout || {};
  const size = u.squad_size;
  const comp = {}; (u.composition||[]).forEach(c=>comp[c.model]=c.count);
  const schema = u.wargear_schema || [];
  const defaultGroup = schema.find(g=>g.type==='default');
  const defaultItems = defaultGroup ? defaultGroup.items : [];
  // Replace-one/all-model groups fold their default item into the card itself
  // (as the pre-checked option), so drop it from the plain "Default:" summary
  // to avoid listing the same weapon twice.
  const coveredKeys = new Set();
  schema.forEach(g=>{
    if(g.type!=='replace_one' && g.type!=='all_model') return;
    const label = wgGroupTitle(g).replace(/^Replace\s+/, '');
    const match = defaultItems.find(i=>i.miniature===g.miniature && i.item.toLowerCase()===label.toLowerCase());
    if(match) coveredKeys.add(match.key);
  });

  const groups = schema.map(g=>{
    if(g.type==='default'){
      const remaining = g.items.filter(i=>!coveredKeys.has(i.key) && (sel[i.key]||0)>0);
      const singles = remaining.filter(i=>(sel[i.key]||0)===1 && (i.default_value||0)<=1);
      const multi   = remaining.filter(i=>!singles.includes(i));
      const singleHtml = singles.map(i=>`<label class="wg-fixed"><input type="checkbox" checked disabled><span>${esc(i.item)}</span></label>`).join('');
      const multiText = multi.map(i=>`${(sel[i.key]||0)>1?(sel[i.key]+'× '):''}${esc(i.item)}`).join(', ');
      const multiHtml = multiText ? `<div class="wg-group wg-default"><span class="wg-default-lbl">Default</span> ${multiText}</div>` : '';
      return `${singleHtml}${multiHtml}`;
    }
    if(g.type==='array'){
      return wgCard(g, wgGroupTitle(g), '', renderArrayGroup(u, g, sel));
    }
    if(g.type==='replace_one' || g.type==='all_model'){
      const nm = ('wg'+u.id+g.items[0].key).replace(/[^a-zA-Z0-9]/g,'');
      // data-keys must also cover the Default-group item this swap displaces, or
      // setWargearRadio's zero-out patch leaves it behind alongside the new pick.
      const gk = esc(JSON.stringify(g.items.map(i=>i.key).concat(g.linked_default_keys||[])));
      const chosen = g.items.find(i=>(sel[i.key]||0)>0);
      const title = wgGroupTitle(g);
      const defaultLabel = title.replace(/^Replace\s+/, '');
      let html = wgRadio(u.id, nm, gk, '', !chosen, defaultLabel, '');
      g.items.forEach(i=>{
        const val = g.type==='all_model' ? (comp[i.miniature]||size) : 1;
        html += wgRadio(u.id, nm, gk, i.key, !!(chosen&&chosen.key===i.key), i.item, i.points, val);
      });
      return wgCard(g, title, '1/1', html);
    }
    if(g.type==='limited_per_n'){
      const cap = limitedCap(g.limits, size);
      const count = g.items.reduce((n,i)=>n+(sel[i.key]||0), 0);
      const its = g.items.map(i=>`<div class="wg-stepper"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span><input type="number" min="0" max="${cap}" value="${sel[i.key]||0}" data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"></div>`).join('');
      return wgCard(g, wgGroupTitle(g), `${count}/${cap}`, `<div class="wg-cap">up to ${cap} at ${size} models</div>${its}`);
    }
    const its = g.items.map(i=>{
      if(i.input_type==='checkbox'){
        return `<label class="wg-check"><input type="checkbox" data-key="${esc(i.key)}" ${(sel[i.key]||0)>0?'checked':''} onchange="setWargearStep('${u.id}',this)"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span></label>`;
      }
      const mc = comp[i.miniature] || size;
      return `<div class="wg-stepper"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span><input type="number" min="0" max="${mc}" value="${sel[i.key]||0}" data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"></div>`;
    }).join('');
    return wgCard(g, wgGroupTitle(g), '', its);
  }).join('');
  const violHtml = (u.wargear_violations && u.wargear_violations.length)
    ? `<div class="wg-violation">${u.wargear_violations.map(v=>`<div>⚠ ${esc(v.message||'')}</div>`).join('')}</div>` : '';
  return `<div class="wg-summary">${esc(u.loadout_summary||'')}</div>${violHtml}${groups}`;
}

function wgRadio(auid, name, keysAttr, key, checked, label, points, val){
  const valAttr = val!=null ? ` data-val="${val}"` : '';
  return `<label class="wg-radio">
    <input type="radio" name="${name}" data-keys="${keysAttr}" data-key="${esc(key)}"${valAttr} ${checked?'checked':''} onchange="setWargearRadio('${auid}',this)" class="wg-box-input">
    <span class="wg-box"></span>
    <span>${esc(label)}${points?` <em>+${points}</em>`:''}</span>
  </label>`;
}

export function toggleWargear(auid){
  const ed = document.getElementById(`au-wg-ed-${auid}`);
  if(!ed) return;
  if(!ed.hidden){ ed.hidden=true; ed.innerHTML=''; return; }
  const u = state.army.units.find(x=>x.id===auid);
  if(!u) return;
  ed.innerHTML = renderWargearEditor(u);
  ed.hidden = false;
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
  postLoadout(auid, {[input.dataset.key]: v});
}

export function setWargearRadio(auid, input){
  const keys = JSON.parse(input.dataset.keys || '[]');
  const patch = {};
  keys.forEach(k=>patch[k]=0);
  if(input.dataset.key) patch[input.dataset.key] = parseInt(input.dataset.val||'1', 10);
  postLoadout(auid, patch);
}

// Weapon-array change. For a <select> grid we re-tally every slot in the sub-pool
// and post absolute counts; for an alternative stepper we post just the changed
// alternatives and let the server re-derive the pool weapon(s).
export function setWargearSlot(auid, el){
  // Multi-item model picker: each select owns one model's bundle index.
  if(el.tagName === 'SELECT' && el.dataset.mode === 'models'){
    postLoadout(auid, {[el.dataset.key]: parseInt(el.value,10)||0});
    return;
  }
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
  state.army.units = state.army.units.filter(u=>u.id!==auid);
  // All 4 Force-Org sections stay visible even when empty (matching the
  // reference app), so a full re-render is simpler and correct here -- no
  // surgical per-row DOM removal / empty-state fallback needed.
  const body = document.getElementById('rosterBody');
  if(body) body.innerHTML = renderRoster(state.army.units, state.army.accent);
  if(state.rightSel && state.rightSel.type==='unit' && state.rightSel.id===auid) clearRight();
  applyServerState(res);
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

  const compEl = document.getElementById(`au-comp-${auid}`);
  if(compEl) compEl.innerHTML = summaryBullets(u.loadout_summary).map(b=>`<li>${esc(b)}</li>`).join('');

  // Enhancement summary tag on the row (empty -> nothing rendered).
  const enhEl = document.getElementById(`au-enh-line-${auid}`);
  if(enhEl) enhEl.innerHTML = u.enhancement_name
    ? `<div class="uc-attached-tag">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>` : '';
}
