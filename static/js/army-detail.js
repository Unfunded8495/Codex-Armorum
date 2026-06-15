import { esc, api, intOr } from './utils.js';
import { state } from './army-state.js';
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
      <p class="ab-card-title">Detachment</p>
      <div class="ab-meta-row">
        <div class="ab-meta-item">
          <label>Detachment</label>
          <select id="abDetachment" onchange="saveArmyMeta()">
            <option value="">— none —</option>
          </select>
        </div>
        <div class="ab-meta-item">
          <label>Points Limit</label>
          <input type="number" id="abPtsLimit" value="${army.points_limit}" min="0" step="100"
                 onchange="saveArmyMeta()">
        </div>
      </div>
    </div>
    <div class="ab-card ab-validation" id="validationCard">
      <p class="ab-card-title">Validation</p>
      <div id="validationBody">${renderValidation(army)}</div>
    </div>`;
}

async function wireSidebarInputs(army){
  let dts = state.detachCache[army.faction_id];
  if(!dts){
    dts = await api(`/api/factions/${army.faction_id}/detachments`);
    state.detachCache[army.faction_id] = dts;
  }
  const sel = document.getElementById('abDetachment');
  if(sel){
    sel.innerHTML = `<option value="">— none —</option>`+
      dts.map(d=>`<option value="${esc(d.id)}" ${d.id===army.detachment_id?'selected':''}>${esc(d.name)}</option>`).join('');
  }
  const nameInput = document.getElementById('abName');
  let nameTimer;
  if(nameInput) nameInput.addEventListener('input', ()=>{
    clearTimeout(nameTimer);
    nameTimer = setTimeout(()=>saveArmyMeta(), 600);
  });
}

export async function saveArmyMeta(){
  if(!state.army) return;
  const name              = (document.getElementById('abName')?.value||'').trim() || state.army.name;
  const dtid              = document.getElementById('abDetachment')?.value || '';
  const pts               = intOr(document.getElementById('abPtsLimit')?.value, state.army.points_limit);
  const detachmentChanged = dtid !== state.army.detachment_id;
  await api(`/api/armies/${state.army.id}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, detachment_id:dtid, points_limit:pts})});
  state.army.name           = name;
  state.army.detachment_id  = dtid;
  state.army.points_limit   = pts;
  if(detachmentChanged){
    state.army.units = state.army.units.map(u=>({...u, enhancement_id:'', enhancement_name:'', enhancement_cost:0}));
    const roster = document.getElementById('rosterBody');
    if(roster) roster.innerHTML = renderRoster(state.army.units, state.army.accent);
    refreshPointsTotal();
  }
  breadcrumb.querySelector('.cur').textContent = name;
  document.getElementById('ptsLimit').textContent = pts;
  updatePointsBar();
  refreshValidation();
}

/* ---- validation --------------------------------------------------------- */

export function renderValidation(army){
  const rows = [];
  const over = army.points_limit>0 && army.total_points>army.points_limit;
  if(over) rows.push(`<div class="ab-val-row ab-val-err">✗ ${army.total_points-army.points_limit} pts over limit</div>`);
  else if(army.points_limit>0) rows.push(`<div class="ab-val-row ab-val-ok">✓ Within points limit</div>`);

  const shortUnits = army.units.filter(u=>u.assigned_count<u.squad_size&&u.owned_count>0);
  shortUnits.forEach(u=>{
    const short = u.squad_size-u.assigned_count;
    rows.push(`<div class="ab-val-row ab-val-warn">⚠ ${esc(u.name)}: assign ${short} more model${short===1?'':'s'}</div>`);
  });

  const overAssigned = army.units.filter(u=>u.assigned_count>u.squad_size);
  overAssigned.forEach(u=>{
    rows.push(`<div class="ab-val-row ab-val-err">✗ ${esc(u.name)}: ${u.assigned_count-u.squad_size} too many assigned</div>`);
  });

  const wishlistUnits = army.units.filter(u=>u.owned_count===0);
  if(wishlistUnits.length>0)
    rows.push(`<div class="ab-val-row ab-val-info">${wishlistUnits.length} unit${wishlistUnits.length===1?'':'s'} not yet owned (wishlist)</div>`);

  if(!rows.length) rows.push(`<div class="ab-val-row ab-val-ok">✓ No issues found</div>`);
  return rows.join('');
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

/* ---- roster rendering --------------------------------------------------- */

export function renderRoster(units, accent){
  if(!units||!units.length) return `
    <div class="ab-empty">
      <span class="ab-empty-icon">✠</span>
      <h3>No units yet</h3>
      <p>Click "Add Unit" to start building your roster.</p>
    </div>`;
  const groups = {};
  units.forEach(u=>{ const role=u.role||'Other'; (groups[role]=groups[role]||[]).push(u); });
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  return ordered.map(role=>`
    <div class="role-section">
      <div class="role-section-head">${esc(role)}</div>
      ${groups[role].map(u=>armyUnitRow(u,accent)).join('')}
    </div>`).join('');
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
      <div class="au-name">${esc(u.name)}</div>
      <div class="au-role">${esc(u.role)}</div>
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
      <button class="au-enh-btn" onclick="toggleEnhEditor('${auid}')">Enhancement</button>
    </div>
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
  refreshPointsTotal();
  refreshValidation();
}

export async function updateAssigned(auid, val){
  const count = Math.max(0, intOr(val, 0));
  const res   = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({assigned_count:count})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  refreshValidation();
}

/* ---- enhancement editor ------------------------------------------------- */

export async function toggleEnhEditor(auid){
  const ed = document.getElementById(`au-enh-ed-${auid}`);
  if(!ed.hidden){ed.hidden=true;ed.innerHTML='';return;}
  if(!state.army) return;
  let enhs = state.enhCache[state.army.detachment_id];
  if(state.army.detachment_id&&!enhs){
    enhs = await api(`/api/detachments/${state.army.detachment_id}/enhancements`);
    state.enhCache[state.army.detachment_id] = enhs;
  }
  const unit = state.army.units.find(u=>u.id===auid) || {};
  if(!enhs||!enhs.length){
    ed.innerHTML = `<p style="font-family:'EB Garamond',serif;font-size:14px;color:var(--parch-dim);margin:0">
      ${state.army.detachment_id?'No enhancements available for this detachment.':'Select a detachment first.'}</p>`;
    ed.hidden = false;
    return;
  }
  ed.innerHTML = `
    <select onchange="saveEnhancement('${auid}',this.value)" style="margin-bottom:8px">
      <option value="">— No enhancement —</option>
      ${enhs.map(e=>`<option value="${esc(e.id)}" ${e.id===unit.enhancement_id?'selected':''}>
        ${esc(e.name)} (+${e.cost} pts)</option>`).join('')}
    </select>`;
  ed.hidden = false;
}

export async function saveEnhancement(auid, enhId){
  const res = await api(`/api/army-units/${auid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({enhancement_id:enhId})});
  if(!res.ok) return;
  mergeUnit(auid, res.unit);
  refreshPointsTotal();
  refreshValidation();
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

/* ---- remove army unit --------------------------------------------------- */

export async function removeArmyUnit(auid){
  await fetch(`/api/army-units/${auid}`, {method:'DELETE'});
  state.army.units = state.army.units.filter(u=>u.id!==auid);
  document.getElementById(`au-${auid}`)?.remove();
  document.querySelectorAll('.role-section').forEach(sec=>{
    if(!sec.querySelector('.au-row')) sec.remove();
  });
  const body = document.getElementById('rosterBody');
  if(body&&!body.querySelector('.au-row'))
    body.innerHTML = `<div class="ab-empty"><span class="ab-empty-icon">✠</span><h3>No units yet</h3><p>Click "Add Unit" to start building your roster.</p></div>`;
  refreshPointsTotal();
  refreshValidation();
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
}
