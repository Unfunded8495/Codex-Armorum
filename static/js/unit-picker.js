import { esc, api } from './utils.js';
import { state } from './army-state.js';
import { ROLE_ORDER, armyUnitRow, refreshPointsTotal, refreshValidation } from './army-detail.js';

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
  const groups = {};
  units.forEach(u=>{(groups[u.role]=groups[u.role]||[]).push(u);});
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  body.innerHTML = ordered.map(role=>`
    <div class="modal-role-head">${esc(role)}</div>
    ${groups[role].map(u=>`
      <div class="modal-unit-row" onclick="addUnitToArmy('${u.id}')">
        <img class="modal-unit-thumb" src="/api/units/${u.id}/image" alt="${esc(u.name)}" loading="lazy">
        <span class="modal-unit-name">${esc(u.name)}</span>
        <span class="modal-unit-owned">${u.owned>0?`${u.owned} owned`:''}</span>
        ${u.points?`<span class="modal-unit-pts">${u.points}+ pts</span>`:''}
      </div>`).join('')}
  `).join('');
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
  refreshPointsTotal();
  refreshValidation();
}
