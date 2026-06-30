import { esc, api, intOr } from './utils.js';
import { state, ensureBattleSizes, detLimitFor, detOptions } from './army-state.js';
import { setBreadcrumb } from './header.js';

const view       = document.getElementById('view');
const breadcrumb = document.getElementById('breadcrumb');

const ROLE_ORDER = ['Epic Hero','Character','Battleline','Infantry','Mounted',
  'Beast','Monster','Vehicle','Swarm','Transport','Fortification','Other','Unaligned'];

export { ROLE_ORDER };

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

  view.innerHTML = `
    <div class="ab-detail">
      <div class="ab-sidebar">
        ${renderSidebar(army)}
      </div>
      <div class="ab-main">
        <div class="ab-roster-head">
          <h2 class="ab-roster-title">Unit Roster</h2>
          <button class="add-unit-btn" onclick="openUnitPicker()">+ Add Unit</button>
        </div>
        <div id="rosterBody">
          ${renderRoster(army.units, army.accent)}
        </div>
      </div>
    </div>`;

  wireSidebarInputs(army);
}

/* ---- sidebar ------------------------------------------------------------ */

function renderSidebar(army){
  const pct  = army.points_limit>0 ? Math.min(100,Math.round(army.total_points/army.points_limit*100)) : 0;
  const over = army.total_points>army.points_limit && army.points_limit>0;
  const isCustom = (army.battle_size||'Custom') === 'Custom';
  return `
    <div class="ab-card">
      <p class="ab-card-title">Army Name</p>
      <input class="ab-name-input" id="abName" value="${esc(army.name)}" placeholder="Army name">
    </div>
    <div class="ab-card">
      <p class="ab-card-title">Points</p>
      <div class="pts-bar-wrap">
        <div class="pts-bar-nums">
          <span class="pts-used ${over?'is-over':''}" id="ptsUsed">${army.total_points}</span>
          <span class="pts-limit-label">/ <span id="ptsLimit">${army.points_limit}</span> pts</span>
        </div>
        <div class="pts-bar-track">
          <div class="pts-bar-fill ${over?'is-over':''}" id="ptsBarFill" style="width:${pct}%"></div>
        </div>
        ${over?`<div class="pts-over-msg" id="ptsOverMsg">⚠ ${army.total_points-army.points_limit} pts over limit</div>`:'<div id="ptsOverMsg"></div>'}
      </div>
    </div>
    <div class="ab-card">
      <p class="ab-card-title">Battle Size &amp; Detachment</p>
      <div class="ab-meta-row">
        <div class="ab-meta-item">
          <label>Battle Size</label>
          <select id="abBattleSize" onchange="onAbBattleSize()"></select>
        </div>
        <div class="ab-meta-item" id="abPtsField" ${isCustom?'':'hidden'}>
          <label>Points Limit</label>
          <input type="number" id="abPtsLimit" value="${army.points_limit}" min="0" step="100" onchange="saveArmyMeta()">
        </div>
        <div class="ab-meta-item">
          <label>Detachment</label>
          <select id="abDetachment" onchange="saveArmyMeta()">
            <option value="">— none —</option>
          </select>
        </div>
      </div>
    </div>
    ${renderArmyRuleCard(army)}
    ${renderDetachmentRuleCard(army)}
    ${renderStratagemsCard(army)}
    <div class="ab-card ab-validation" id="validationCard">
      <p class="ab-card-title">Validation</p>
      <div id="validationBody">${renderValidation(army)}</div>
    </div>
    <div class="ab-card">
      <p class="ab-card-title">Export</p>
      <div class="ab-export-btns">
        <button class="ab-export-btn" type="button" onclick="exportArmy('copy', this)">Copy list</button>
        <button class="ab-export-btn" type="button" onclick="exportArmy('txt', this)">Download .txt</button>
        <button class="ab-export-btn" type="button" onclick="exportArmy('json', this)">Download .json</button>
      </div>
    </div>`;
}

function renderDetachmentRuleCard(army){
  const rules    = army.detachment_rules    || [];
  const unlocks  = army.detachment_unlocks  || [];
  const excludes = army.detachment_excludes || [];
  if(!rules.length && !unlocks.length && !excludes.length) return '';
  const ruleHtml = rules.map(r=>`
    <div class="ab-detrule">
      ${r.name?`<div class="ab-detrule-name">${esc(r.name)}</div>`:''}
      <div class="ab-detrule-body">${esc(r.description||'')}</div>
    </div>`).join('');
  const list = (label, arr)=> arr.length
    ? `<div class="ab-detlist"><span class="ab-detlist-label">${label}:</span> ${arr.map(esc).join(', ')}</div>`
    : '';
  const metaHtml = (unlocks.length||excludes.length)
    ? `<div class="ab-detrule-meta">${list('Unlocks',unlocks)}${list('Excludes',excludes)}</div>` : '';
  return `
    <div class="ab-card ab-detrule-card">
      <button class="ab-detrule-toggle" type="button" onclick="toggleCollapse(this)" aria-expanded="false">
        <span class="ab-card-title" style="margin:0">Detachment Rule${rules.length>1?'s':''}</span>
        <span class="ab-detrule-chevron" id="abDetChevron">▸</span>
      </button>
      <div class="ab-detrule-content" id="abDetRuleContent" hidden>
        ${ruleHtml}${metaHtml}
      </div>
    </div>`;
}

const STRAT_CAT = {battleTactic:'Battle Tactic', strategicPloy:'Strategic Ploy',
  epicDeed:'Epic Deed', wargear:'Wargear'};

function renderArmyRuleCard(army){
  const rules = army.army_rules || [];
  if(!rules.length) return '';
  const body = rules.map(r=>`
    <div class="ab-detrule">
      ${r.name?`<div class="ab-detrule-name">${esc(r.name)}</div>`:''}
      <div class="ab-detrule-body">${esc(r.body_text||'')}</div>
    </div>`).join('');
  return `
    <div class="ab-card ab-detrule-card">
      <button class="ab-detrule-toggle" type="button" onclick="toggleCollapse(this)" aria-expanded="false">
        <span class="ab-card-title" style="margin:0">Army Rule${rules.length>1?'s':''}</span>
        <span class="ab-detrule-chevron">▸</span>
      </button>
      <div class="ab-detrule-content" hidden>${body}</div>
    </div>`;
}

function stratItem(s){
  const meta = [STRAT_CAT[s.category] || '', s.used_when].filter(Boolean).join(' · ');
  return `
    <div class="ab-strat">
      <div class="ab-strat-head">
        <span class="ab-strat-name">${esc(s.name||'')}</span>
        ${s.cp_cost?`<span class="ab-strat-cp">${esc(String(s.cp_cost))}CP</span>`:''}
      </div>
      ${meta?`<div class="ab-strat-cat">${esc(meta)}</div>`:''}
      ${s.when_text?`<div class="ab-strat-line"><b>When:</b> ${esc(s.when_text)}</div>`:''}
      ${s.target_text?`<div class="ab-strat-line"><b>Target:</b> ${esc(s.target_text)}</div>`:''}
      ${s.effect_text?`<div class="ab-strat-line"><b>Effect:</b> ${esc(s.effect_text)}</div>`:''}
      ${s.restriction_text?`<div class="ab-strat-line"><b>Restrictions:</b> ${esc(s.restriction_text)}</div>`:''}
    </div>`;
}

function renderStratagemsCard(army){
  const det  = army.stratagems || [];
  const core = army.core_stratagems || [];
  if(!det.length && !core.length) return '';
  const group = (title, arr)=> arr.length
    ? `<div class="ab-strat-group"><div class="ab-strat-grouphead">${esc(title)}</div>${arr.map(stratItem).join('')}</div>`
    : '';
  return `
    <div class="ab-card ab-detrule-card ab-strat-card">
      <button class="ab-detrule-toggle" type="button" onclick="toggleCollapse(this)" aria-expanded="false">
        <span class="ab-card-title" style="margin:0">Stratagems <span class="ab-count">${det.length+core.length}</span></span>
        <span class="ab-detrule-chevron">▸</span>
      </button>
      <div class="ab-detrule-content" hidden>
        ${group(army.detachment_name||'Detachment', det)}
        ${group('Core', core)}
      </div>
    </div>`;
}

export function toggleCollapse(btn){
  const content = btn.parentElement.querySelector('.ab-detrule-content');
  const chev    = btn.querySelector('.ab-detrule-chevron');
  if(!content) return;
  content.hidden = !content.hidden;
  if(chev) chev.textContent = content.hidden ? '▸' : '▾';
  btn.setAttribute('aria-expanded', String(!content.hidden));
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

async function wireSidebarInputs(army){
  let battleSizes;
  let dts = state.detachCache[army.faction_id];
  try{
    [dts, battleSizes] = await Promise.all([
      dts ? Promise.resolve(dts) : api(`/api/factions/${encodeURIComponent(army.faction_id)}/detachments`),
      ensureBattleSizes(),
    ]);
  }catch(e){ dts = dts || []; battleSizes = state.battleSizes || []; }
  state.detachCache[army.faction_id] = dts;

  const bsSel = document.getElementById('abBattleSize');
  if(bsSel){
    const cur = army.battle_size || 'Custom';
    bsSel.innerHTML = battleSizes.map(b=>
        `<option value="${esc(b.name)}" ${b.name===cur?'selected':''}>${esc(b.name)} · ${b.points_limit} pts</option>`).join('')
      + `<option value="Custom" ${cur==='Custom'?'selected':''}>Custom</option>`;
  }
  const sel = document.getElementById('abDetachment');
  if(sel) sel.innerHTML = `<option value="">— none —</option>`+
    detOptions(dts, army.detachment_id, detLimitFor(army.battle_size));

  const nameInput = document.getElementById('abName');
  let nameTimer;
  if(nameInput) nameInput.addEventListener('input', ()=>{
    clearTimeout(nameTimer);
    nameTimer = setTimeout(()=>saveArmyMeta(), 600);
  });
}

export async function saveArmyMeta(){
  if(!state.army) return;
  const name = (document.getElementById('abName')?.value||'').trim() || state.army.name;
  const dtid = document.getElementById('abDetachment')?.value || '';
  const bs   = document.getElementById('abBattleSize')?.value || state.army.battle_size || 'Custom';
  const pts  = intOr(document.getElementById('abPtsLimit')?.value, state.army.points_limit);
  let res;
  try{
    res = await api(`/api/armies/${state.army.id}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, detachment_id:dtid, battle_size:bs, points_limit:pts})});
  }catch(e){ return; }
  if(!res || !res.ok){ if(res&&res.error) alert(res.error); return; }

  // The server is authoritative: it derives the points limit from the battle
  // size and may auto-clear an over-cost detachment on a downgrade.
  const detachmentChanged = (res.detachment_id||'') !== (state.army.detachment_id||'');
  state.army.name                    = name;
  state.army.battle_size             = res.battle_size;
  state.army.points_limit            = res.points_limit;
  state.army.detachment_id           = res.detachment_id || '';
  state.army.enhancement_limit       = res.enhancement_limit;
  state.army.duplicate_unit_limit    = res.duplicate_unit_limit;
  state.army.detachment_points_limit = res.detachment_points_limit;
  state.army.total_points            = res.total_points;
  state.army.validation              = res.validation;
  breadcrumb.querySelector('.cur').textContent = name;

  if(detachmentChanged){
    // Detachment changed (possibly auto-cleared) — refetch so the rule card,
    // detachment select and stripped enhancements all stay consistent.
    showArmy(state.army.id);
    return;
  }
  const limEl = document.getElementById('ptsLimit');
  if(limEl) limEl.textContent = state.army.points_limit;
  updatePointsBar();
  refreshValidation();
}

// Sidebar battle-size change: reveal the points input only for Custom, re-filter
// detachments against the new cost limit (clearing one that no longer fits),
// then persist via saveArmyMeta.
export function onAbBattleSize(){
  const bs = document.getElementById('abBattleSize')?.value || 'Custom';
  const ptsField = document.getElementById('abPtsField');
  if(ptsField) ptsField.hidden = bs !== 'Custom';
  const sel = document.getElementById('abDetachment');
  const dts = state.detachCache[state.army?.faction_id] || [];
  if(sel){
    const limit = detLimitFor(bs);
    const cur = sel.value;
    const stillValid = dts.some(d=>d.id===cur && (limit==null || (d.points_cost||0)<=limit));
    sel.innerHTML = `<option value="">— none —</option>`+ detOptions(dts, stillValid?cur:'', limit);
  }
  saveArmyMeta();
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
  const total = state.army.total_points;
  const limit = state.army.points_limit;
  const over  = limit>0 && total>limit;
  const pct   = limit>0 ? Math.min(100,Math.round(total/limit*100)) : 0;
  const usedEl = document.getElementById('ptsUsed');
  if(usedEl){usedEl.textContent=total;usedEl.classList.toggle('is-over',over);}
  const fillEl = document.getElementById('ptsBarFill');
  if(fillEl){fillEl.style.width=pct+'%';fillEl.classList.toggle('is-over',over);}
  const overEl = document.getElementById('ptsOverMsg');
  if(overEl) overEl.textContent = over ? `⚠ ${total-limit} pts over limit` : '';
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

export function renderRoster(units, accent){
  if(!units||!units.length) return `
    <div class="ab-empty">
      <span class="ab-empty-icon">✠</span>
      <h3>No units yet</h3>
      <p>Click "Add Unit" to start building your roster.</p>
    </div>`;
  // Attached leaders render nested under their bodyguard, not as standalone rows.
  const leaderFor = {};
  units.forEach(u=>{ if(u.attached_to) leaderFor[u.attached_to] = u; });
  const standalone = units.filter(u=>!u.attached_to);
  const groups = {};
  standalone.forEach(u=>{ const role=u.role||'Other'; (groups[role]=groups[role]||[]).push(u); });
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  return ordered.map(role=>`
    <div class="role-section">
      <div class="role-section-head">${esc(role)}<span class="role-count">${groups[role].length}</span></div>
      ${groups[role].map(u=>armyUnitRow(u,accent)
        + (leaderFor[u.id]?`<div class="au-nested">${armyUnitRow(leaderFor[u.id],accent)}</div>`:'')).join('')}
    </div>`).join('');
}

function compLine(comp){
  if(!comp || !comp.length) return '';
  // Smallest count first → the single leader/character reads before the troops,
  // and the order stays stable across brackets (tiers list models inconsistently).
  return [...comp].sort((a,b)=>a.count-b.count)
    .map(c=>`${c.count}× ${esc(c.model)}`).join(' · ');
}

export function armyUnitRow(u, accent){
  const auid     = u.id;
  const owned    = u.owned_count;
  const avail    = u.available_count;
  const assigned = u.assigned_count;
  const squad    = u.squad_size;
  const pts      = u.points + (u.enhancement_cost||0);
  const squadMin = u.squad_min || 1;
  const squadMax = u.squad_max || '';

  let ownHtml = '';
  if(owned===0){
    ownHtml = `<span class="own-none">Not owned — wishlist</span>`;
  }else if(assigned>=squad){
    ownHtml = `<span class="own-ok">✓ ${assigned} of ${squad} assigned</span>`;
  }else{
    const short = squad-assigned;
    ownHtml = `<span class="own-warn">⚠ ${assigned}/${squad} assigned — need ${short} more (${avail} available)</span>`;
  }

  return `<div class="au-row faction-surface" id="au-${auid}" style="--cardarmy:${state.army?.primary||'var(--panel)'};--cardaccent:${accent||'var(--gold)'};--cardglow:${accent||'var(--gold)'};--au-accent:${accent||'var(--gold)'}">
    <div>
      <div class="au-name">${esc(u.name)}${u.is_warlord?' <span class="au-warlord" title="Warlord">★</span>':''}${u.is_ally?` <span class="au-ally" title="Allied: ${esc(u.ally_faction)}">⚔ ${esc(u.ally_faction)}</span>`:''}${u.attached_leader_name?` <span class="au-ledby" title="Led by ${esc(u.attached_leader_name)}">⮡ ${esc(u.attached_leader_name)}</span>`:''}</div>
      <div class="au-role">${esc(u.role)}</div>
      <div class="au-comp" id="au-comp-${auid}">${compLine(u.composition)}</div>
      <div class="au-controls">
        <div class="au-size-wrap">
          <label>Squad</label>
          <input class="au-size-input" type="number" min="${squadMin}" ${squadMax?`max="${squadMax}"`:''} value="${squad}"
                 onchange="updateSquadSize('${auid}',this.value)" title="Squad size">
        </div>
        <div class="au-pts" id="au-pts-${auid}">${pts} pts</div>
        ${owned>0?`<div class="au-assign-wrap">
          <label>Assign</label>
          <input class="au-assign-input" type="number" min="0" max="${avail+assigned}" value="${assigned}"
                 onchange="updateAssigned('${auid}',this.value)" title="Assigned models from collection">
          <span style="font-family:'Oswald',sans-serif;font-size:11px;color:var(--parch-dim)">/ ${owned} owned</span>
        </div>`:''}
      </div>
      <div class="au-ownership" id="au-own-${auid}">${ownHtml}</div>
      ${u.enhancement_name?`<div class="au-enh">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>`:''}
    </div>
    <div class="au-actions">
      <button class="au-del" onclick="removeArmyUnit('${auid}')">Remove</button>
      ${u.is_character?`<button class="au-enh-btn au-warlord-btn ${u.is_warlord?'is-on':''}" onclick="toggleWarlord('${auid}')">${u.is_warlord?'★ Warlord':'☆ Warlord'}</button>`:''}
      ${u.wargear_schema&&u.wargear_schema.length?`<button class="au-enh-btn" onclick="toggleWargear('${auid}')">Wargear</button>`:''}
      ${u.can_have_enhancement?`<button class="au-enh-btn" onclick="toggleEnhEditor('${auid}')">Enhancement</button>`:''}
      ${u.attached_to?`<button class="au-enh-btn" onclick="detachLeader('${auid}')">Detach</button>`
        :(u.attach_targets&&u.attach_targets.length?`<select class="au-attach" onchange="attachLeader('${auid}',this.value)"><option value="">Attach to…</option>${u.attach_targets.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('')}</select>`:'')}
    </div>
    <div class="au-wargear-editor" id="au-wg-ed-${auid}" hidden></div>
    <div class="au-enh-editor" id="au-enh-ed-${auid}" hidden></div>
  </div>`;
}

/* ---- squad / assign updates --------------------------------------------- */

export async function updateSquadSize(auid, val){
  const size = Math.max(1, intOr(val, 1));
  const res  = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({squad_size:size})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
}

export async function updateAssigned(auid, val){
  const count = Math.max(0, intOr(val, 0));
  const res   = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({assigned_count:count})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
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
  mergeUnit(auid, res.unit);
  applyServerState(res);
  const row = document.getElementById(`au-${auid}`);
  if(row){
    let enhDiv = row.querySelector('.au-enh');
    const u    = state.army.units.find(u=>u.id===auid) || {};
    if(u.enhancement_name){
      const html = `<div class="au-enh">Enhancement: ${esc(u.enhancement_name)} (+${u.enhancement_cost||0} pts)</div>`;
      if(enhDiv) enhDiv.outerHTML = html;
      else document.getElementById(`au-own-${auid}`).insertAdjacentHTML('afterend', html);
    }else{
      if(enhDiv) enhDiv.remove();
    }
  }
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
  }
  u.is_warlord = !!res.unit.is_warlord;
  setWarlordVisual(auid, u.is_warlord);
  applyServerState(res);
}

function setWarlordVisual(auid, on){
  const row = document.getElementById(`au-${auid}`);
  if(!row) return;
  const nameEl = row.querySelector('.au-name');
  const badge = nameEl && nameEl.querySelector('.au-warlord');
  if(on && nameEl && !badge) nameEl.insertAdjacentHTML('beforeend', ' <span class="au-warlord" title="Warlord">★</span>');
  else if(!on && badge) badge.remove();
  const btn = row.querySelector('.au-warlord-btn');
  if(btn){ btn.classList.toggle('is-on', on); btn.textContent = on ? '★ Warlord' : '☆ Warlord'; }
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
  const head = `<div class="wg-group-head">${esc(g.instruction)}</div>`;
  const subs = g.mode==='models'
    ? (g.minis||[]).map(sub=>renderModelsSub(u, g, sub)).join('')
    : (g.minis||[]).map(sub=>renderArraySub(u.id, g, sub, sel)).join('');
  return `<div class="wg-group wg-array">${head}${subs}</div>`;
}

function renderWargearEditor(u){
  const sel = u.loadout || {};
  const size = u.squad_size;
  const comp = {}; (u.composition||[]).forEach(c=>comp[c.model]=c.count);
  const groups = (u.wargear_schema||[]).map(g=>{
    const head = `<div class="wg-group-head">${esc(g.instruction)}</div>`;
    if(g.type==='default'){
      const list = g.items.filter(i=>(sel[i.key]||0)>0)
        .map(i=>`${(sel[i.key]||0)>1?(sel[i.key]+'× '):''}${esc(i.item)}`).join(', ');
      return list ? `<div class="wg-group wg-default"><span class="wg-default-lbl">Default</span> ${list}</div>` : '';
    }
    if(g.type==='array'){
      return renderArrayGroup(u, g, sel);
    }
    if(g.type==='replace_one' || g.type==='all_model'){
      const nm = ('wg'+u.id+g.items[0].key).replace(/[^a-zA-Z0-9]/g,'');
      const gk = esc(JSON.stringify(g.items.map(i=>i.key)));
      const chosen = g.items.find(i=>(sel[i.key]||0)>0);
      let html = `<label class="wg-radio"><input type="radio" name="${nm}" data-keys="${gk}" data-key="" ${!chosen?'checked':''} onchange="setWargearRadio('${u.id}',this)"><span>Default</span></label>`;
      g.items.forEach(i=>{
        const val = g.type==='all_model' ? (comp[i.miniature]||size) : 1;
        html += `<label class="wg-radio"><input type="radio" name="${nm}" data-keys="${gk}" data-key="${esc(i.key)}" data-val="${val}" ${chosen&&chosen.key===i.key?'checked':''} onchange="setWargearRadio('${u.id}',this)"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span></label>`;
      });
      return `<div class="wg-group">${head}${html}</div>`;
    }
    if(g.type==='limited_per_n'){
      const cap = limitedCap(g.limits, size);
      const its = g.items.map(i=>`<div class="wg-stepper"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span><input type="number" min="0" max="${cap}" value="${sel[i.key]||0}" data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"></div>`).join('');
      return `<div class="wg-group">${head}<div class="wg-cap">up to ${cap} at ${size} models</div>${its}</div>`;
    }
    const its = g.items.map(i=>{
      if(i.input_type==='checkbox'){
        return `<label class="wg-check"><input type="checkbox" data-key="${esc(i.key)}" ${(sel[i.key]||0)>0?'checked':''} onchange="setWargearStep('${u.id}',this)"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span></label>`;
      }
      const mc = comp[i.miniature] || size;
      return `<div class="wg-stepper"><span>${esc(i.item)}${i.points?` <em>+${i.points}</em>`:''}</span><input type="number" min="0" max="${mc}" value="${sel[i.key]||0}" data-key="${esc(i.key)}" onchange="setWargearStep('${u.id}',this)"></div>`;
    }).join('');
    return its ? `<div class="wg-group">${head}${its}</div>` : '';
  }).join('');
  return `<div class="wg-summary">${esc(u.loadout_summary||'')}</div>${groups}`;
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
  let res;
  try{ res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({loadout:patch})}); }
  catch(e){ return; }
  if(!res || !res.ok) return;
  mergeUnit(auid, res.unit);
  applyServerState(res);
  const u = state.army.units.find(x=>x.id===auid);
  const ed = document.getElementById(`au-wg-ed-${auid}`);
  if(ed && !ed.hidden && u) ed.innerHTML = renderWargearEditor(u);
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
  document.getElementById(`au-${auid}`)?.remove();
  document.querySelectorAll('.role-section').forEach(sec=>{
    if(!sec.querySelector('.au-row')) sec.remove();
  });
  const body = document.getElementById('rosterBody');
  if(body&&!body.querySelector('.au-row'))
    body.innerHTML = `<div class="ab-empty"><span class="ab-empty-icon">✠</span><h3>No units yet</h3><p>Click "Add Unit" to start building your roster.</p></div>`;
  applyServerState(res);
}

/* ---- merge unit state --------------------------------------------------- */

export function mergeUnit(auid, updated){
  const idx = state.army.units.findIndex(u=>u.id===auid);
  if(idx>=0) state.army.units[idx] = {...state.army.units[idx], ...updated};

  const u        = updated;
  const owned    = u.owned_count;
  const assigned = u.assigned_count;
  const squad    = u.squad_size;
  const avail    = u.available_count;
  const pts      = (u.points||0) + (u.enhancement_cost||0);

  const ptsEl = document.getElementById(`au-pts-${auid}`);
  if(ptsEl) ptsEl.textContent = `${pts} pts`;

  const ownEl = document.getElementById(`au-own-${auid}`);
  if(ownEl){
    let html = '';
    if(owned===0)          html = `<span class="own-none">Not owned — wishlist</span>`;
    else if(assigned>=squad) html = `<span class="own-ok">✓ ${assigned} of ${squad} assigned</span>`;
    else{
      const short = squad-assigned;
      html = `<span class="own-warn">⚠ ${assigned}/${squad} assigned — need ${short} more (${avail} available)</span>`;
    }
    ownEl.innerHTML = html;
  }

  const assignInput = document.querySelector(`#au-${auid} .au-assign-input`);
  if(assignInput){ assignInput.max = avail+assigned; assignInput.value = assigned; }
  const sizeInput = document.querySelector(`#au-${auid} .au-size-input`);
  if(sizeInput){
    sizeInput.min = u.squad_min || 1;
    if(u.squad_max) sizeInput.max = u.squad_max;
    else sizeInput.removeAttribute('max');
    sizeInput.value = squad;
  }
  const compEl = document.getElementById(`au-comp-${auid}`);
  if(compEl) compEl.innerHTML = compLine(u.composition);
}
