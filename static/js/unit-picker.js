import { esc, api } from './utils.js';
import { state } from './army-state.js';
import { ROLE_ORDER, armyUnitRow, applyServerState, renderRoster } from './army-detail.js';

/* ---- add-unit picker overlay --------------------------------------------
   Full-screen overlay (matches the reference app's add-unit screen), reached
   from a Force-Org section's "+" and pre-scoped to that one category -- a
   unit's category is never a player choice, so every real entry point is
   scoped. The category is optional only as a defensive fallback. ---------- */

function unitsUsedCount(did){
  return (state.army?.units || []).filter(u=>u.datasheet_id===did).length;
}

function scopedUnits(units){
  const cat = state.pickerCategory;
  return cat ? units.filter(u=>(u.foc_category||'Other Datasheets')===cat) : units;
}

export async function openUnitPicker(category){
  if(!state.army) return;
  state.pickerCategory = category || null;
  const modal = document.getElementById('unitPickerModal');
  const body  = document.getElementById('pickerBody');
  const title = document.getElementById('pickerTitle');
  if(title) title.textContent = category || 'Add Unit';
  body.innerHTML = `<p class="po-empty">Loading&hellip;</p>`;
  modal.hidden = false;
  document.getElementById('pickerSearch').value = '';

  let units = state.unitsCache[state.army.faction_id];
  if(!units){
    const data = await api(`/api/factions/${state.army.faction_id}/units?for=army-builder`);
    units = data.units || [];
    state.unitsCache[state.army.faction_id] = units;
  }
  state.picker = {units, owned: Object.fromEntries(units.map(u=>[u.id,u.owned]))};
  renderPicker(scopedUnits(units));
}

export function renderPicker(units){
  const body = document.getElementById('pickerBody');
  if(!units||!units.length){ body.innerHTML = `<p class="po-empty">No units found.</p>`; return; }
  const row = u=>{
    const used = unitsUsedCount(u.id);
    return `<div class="po-card" data-testid="picker-unit-${esc(u.name)}">
        <img class="po-thumb" src="/api/units/${u.id}/image" alt="" loading="lazy">
        <div class="po-body-text">
          <div class="po-name">${esc(u.name)}${u.is_ally?` <span class="modal-ally-tag">${esc(u.ally_faction)}</span>`:''}</div>
          ${used?`<div class="po-owned">${used}&times; Unit In Army</div>`:''}
        </div>
        <div class="po-side">
          <button class="po-add" type="button" aria-label="Add ${esc(u.name)}" onclick="addUnitToArmy('${u.id}')">+</button>
          ${u.points?`<span class="po-pts">${u.points}+ Points</span>`:''}
        </div>
      </div>`;
  };
  const native = units.filter(u=>!u.is_ally);
  const allyGroups = {};
  units.filter(u=>u.is_ally).forEach(u=>{(allyGroups[u.ally_faction]=allyGroups[u.ally_faction]||[]).push(u);});
  const allyHtml = Object.keys(allyGroups).sort().map(f=>
    `<div class="po-role-head po-ally-head">Allies &middot; ${esc(f)}</div>${allyGroups[f].map(row).join('')}`).join('');
  // Scoped to one Force-Org category: every card already belongs to it, so
  // no role sub-grouping. Unscoped (defensive fallback only -- every real
  // entry point passes a category): group by battlefield role so a flat
  // all-units list stays usable.
  if(state.pickerCategory){
    body.innerHTML = native.map(row).join('') + allyHtml;
    return;
  }
  const groups = {};
  native.forEach(u=>{(groups[u.role]=groups[u.role]||[]).push(u);});
  const ordered = ROLE_ORDER.filter(r=>groups[r]).concat(Object.keys(groups).filter(r=>!ROLE_ORDER.includes(r)));
  body.innerHTML = ordered.map(role=>`<div class="po-role-head">${esc(role)}</div>${groups[role].map(row).join('')}`).join('') + allyHtml;
}

export function filterPicker(q){
  if(!state.picker) return;
  const f = state.picker.units.filter(u=>u.name.toLowerCase().includes((q||'').toLowerCase()));
  renderPicker(scopedUnits(f));
}

export function closeUnitPicker(){
  const modal = document.getElementById('unitPickerModal');
  if(modal) modal.hidden = true;
}

// Adds instantly and stays open (matches the reference app: "Nx Unit In
// Army" appears on the card so you can keep adding more without leaving the
// picker), rather than the old single-add-then-close modal behaviour.
export async function addUnitToArmy(did){
  if(!state.army) return;
  const res = await api(`/api/armies/${state.army.id}/units`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({datasheet_id:did})});
  if(!res.ok) return;
  state.army.units.push(res.unit);

  // All 4 Force-Org sections already exist in the DOM (renderRoster always
  // renders them), so a full re-render is simpler and correct here -- no
  // surgical per-section DOM creation/insertion-order logic needed.
  const body = document.getElementById('rosterBody');
  if(body) body.innerHTML = renderRoster(state.army.units, state.army.accent);
  applyServerState(res);
  filterPicker(document.getElementById('pickerSearch')?.value || '');
}
