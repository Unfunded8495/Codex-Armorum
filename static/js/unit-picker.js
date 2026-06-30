import { esc, api } from './utils.js';
import { state } from './army-state.js';
import { ROLE_ORDER, armyUnitRow, applyServerState } from './army-detail.js';

/* ---- persistent left-panel picker --------------------------------------- */

// Render the always-visible unit picker into #leftPanel. Units are cached per
// faction. Each row shows points, name, a count of how many are already in the
// list, and a + button.
export async function renderLeftPicker(army){
  const panel = document.getElementById('leftPanel');
  if(!panel) return;
  panel.innerHTML = `
    <div class="lp-head">
      <h3 class="lp-title">Units</h3>
      <input class="lp-search" id="lpSearch" placeholder="Search units&hellip;"
             oninput="filterLeftPicker(this.value)" autocomplete="off">
    </div>
    <div class="lp-body" id="lpBody"><div class="lp-loading">Loading&hellip;</div></div>`;
  let units = state.unitsCache[army.faction_id];
  if(!units){
    try{ const data = await api(`/api/factions/${army.faction_id}/units?for=army-builder`); units = data.units || []; }
    catch(e){ units = []; }
    state.unitsCache[army.faction_id] = units;
  }
  state.picker = {units, owned: Object.fromEntries(units.map(u=>[u.id,u.owned]))};
  renderLeftPickerList(units);
}

function unitUsedCount(did){
  return (state.army?.units || []).filter(u=>u.datasheet_id===did).length;
}

export function renderLeftPickerList(units){
  const body = document.getElementById('lpBody');
  if(!body) return;
  if(!units || !units.length){ body.innerHTML = `<p class="lp-empty">No units found.</p>`; return; }
  const row = u=>{
    const used = unitUsedCount(u.id);
    return `<div class="lp-unit" data-testid="picker-unit-${esc(u.name)}" onclick="addUnitToArmy('${u.id}')" title="Add to roster">
      <button class="lp-add" type="button" aria-label="Add ${esc(u.name)}" onclick="event.stopPropagation();addUnitToArmy('${u.id}')">+</button>
      <span class="lp-unit-name">${esc(u.name)}${u.is_ally?` <span class="modal-ally-tag">${esc(u.ally_faction)}</span>`:''}</span>
      ${used?`<span class="lp-used" title="${used} in list">${used}</span>`:''}
      ${u.points?`<span class="lp-pts">${u.points}+</span>`:''}
    </div>`;
  };
  const groups = {};
  units.filter(u=>!u.is_ally).forEach(u=>{(groups[u.role]=groups[u.role]||[]).push(u);});
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  let html = ordered.map(role=>`<div class="lp-role">${esc(role)}<span class="lp-role-n">${groups[role].length}</span></div>${groups[role].map(row).join('')}`).join('');
  const allyGroups = {};
  units.filter(u=>u.is_ally).forEach(u=>{(allyGroups[u.ally_faction]=allyGroups[u.ally_faction]||[]).push(u);});
  html += Object.keys(allyGroups).sort().map(f=>
    `<div class="lp-role lp-role-ally">Allies · ${esc(f)}</div>${allyGroups[f].map(row).join('')}`).join('');
  body.innerHTML = html;
}

export function filterLeftPicker(q){
  if(!state.picker) return;
  const f = state.picker.units.filter(u=>u.name.toLowerCase().includes((q||'').toLowerCase()));
  renderLeftPickerList(f);
}

// Re-render the left list preserving the current search, to refresh used-counts
// after an add/remove.
export function refreshLeftPicker(){
  if(!state.picker) return;
  filterLeftPicker(document.getElementById('lpSearch')?.value || '');
}

// Mobile: toggle the slide-in left picker drawer.
export function toggleLeftPanel(){
  document.getElementById('leftPanel')?.classList.toggle('is-open');
}

export async function openUnitPicker(){
  if(!state.army) return;
  const modal = document.getElementById('unitPickerModal');
  const body  = document.getElementById('pickerBody');
  body.innerHTML = `<div style="padding:24px;text-align:center;color:var(--parch-dim);font-family:'Oswald',sans-serif;letter-spacing:1px;text-transform:uppercase;font-size:12px">Loading…</div>`;
  modal.hidden = false;
  document.getElementById('pickerSearch').value = '';

  let units = state.unitsCache[state.army.faction_id];
  if(!units){
    const data = await api(`/api/factions/${state.army.faction_id}/units?for=army-builder`);
    units = data.units || [];
    state.unitsCache[state.army.faction_id] = units;
  }
  state.picker = {units, owned: Object.fromEntries(units.map(u=>[u.id,u.owned]))};
  renderPicker(units);
}

export function renderPicker(units){
  const body = document.getElementById('pickerBody');
  if(!units||!units.length){body.innerHTML=`<p style="padding:20px;color:var(--parch-dim);font-style:italic">No units found.</p>`;return;}
  const row = u=>`
      <div class="modal-unit-row" data-testid="picker-unit-${esc(u.name)}" onclick="addUnitToArmy('${u.id}')">
        <img class="modal-unit-thumb" src="/api/units/${u.id}/image" alt="${esc(u.name)}" loading="lazy">
        <span class="modal-unit-name">${esc(u.name)}${u.is_ally?` <span class="modal-ally-tag">${esc(u.ally_faction)}</span>`:''}</span>
        <span class="modal-unit-owned">${u.owned>0?`${u.owned} owned`:''}</span>
        ${u.points?`<span class="modal-unit-pts">${u.points}+ pts</span>`:''}
      </div>`;
  // Native units by role, then allied units grouped by ally faction.
  const groups = {};
  units.filter(u=>!u.is_ally).forEach(u=>{(groups[u.role]=groups[u.role]||[]).push(u);});
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  let html = ordered.map(role=>`<div class="modal-role-head">${esc(role)}</div>${groups[role].map(row).join('')}`).join('');
  const allyGroups = {};
  units.filter(u=>u.is_ally).forEach(u=>{(allyGroups[u.ally_faction]=allyGroups[u.ally_faction]||[]).push(u);});
  html += Object.keys(allyGroups).sort().map(f=>
    `<div class="modal-role-head modal-ally-head">Allies · ${esc(f)}</div>${allyGroups[f].map(row).join('')}`).join('');
  body.innerHTML = html;
}

export function filterPicker(q){
  if(!state.picker) return;
  const filtered = state.picker.units.filter(u=>u.name.toLowerCase().includes(q.toLowerCase()));
  renderPicker(filtered);
}

export function closeUnitPicker(){
  document.getElementById('unitPickerModal').hidden = true;
}

export async function addUnitToArmy(did){
  closeUnitPicker();
  if(!state.army) return;
  const res = await api(`/api/armies/${state.army.id}/units`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({datasheet_id:did})});
  if(!res.ok) return;
  const unit = res.unit;
  state.army.units.push(unit);

  const body = document.getElementById('rosterBody');
  body.querySelector('.ab-empty')?.remove();

  const role = unit.role || 'Other';
  let roleSection = null;
  body.querySelectorAll('.role-section').forEach(sec=>{
    if(sec.querySelector('.role-section-head')?.textContent===role) roleSection=sec;
  });
  if(!roleSection){
    roleSection = document.createElement('div');
    roleSection.className = 'role-section';
    roleSection.innerHTML = `<div class="role-section-head">${esc(role)}</div>`;
    const roleIdx = ROLE_ORDER.indexOf(role);
    let inserted  = false;
    body.querySelectorAll('.role-section').forEach(sec=>{
      if(inserted) return;
      const secRole = sec.querySelector('.role-section-head')?.textContent || '';
      if(ROLE_ORDER.indexOf(secRole)>roleIdx){ body.insertBefore(roleSection,sec); inserted=true; }
    });
    if(!inserted) body.appendChild(roleSection);
  }
  roleSection.insertAdjacentHTML('beforeend', armyUnitRow(unit, state.army.accent));
  applyServerState(res);
  refreshLeftPicker();   // bump the "in list" count in the left picker
}
