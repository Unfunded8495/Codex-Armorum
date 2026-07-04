import { esc, api } from './utils.js';
import { state } from './army-state.js';
import { ROLE_ORDER, armyUnitRow, applyServerState, renderRoster, renderProfiles,
         syncOverlayScrim } from './army-detail.js';

/* ---- add-unit picker drawer ----------------------------------------------
   Right-docked drawer (the roster stays visible beside it), reached from a
   Force-Org section's "+" and pre-scoped to that one category -- a unit's
   category is never a player choice, so every real entry point is scoped.
   The category is optional only as a defensive fallback. ------------------ */

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
  const facTag = document.getElementById('pickerFaction');
  if(facTag) facTag.textContent = state.army.faction_display_name || state.army.faction_name || '';
  body.innerHTML = `<p class="po-empty">Loading&hellip;</p>`;
  modal.hidden = false;
  syncOverlayScrim();
  document.getElementById('pickerSearch').value = '';

  let units = state.unitsCache[state.army.faction_id];
  if(!units){
    try{
      const data = await api(`/api/factions/${state.army.faction_id}/units?for=army-builder`);
      units = data.units || [];
      state.unitsCache[state.army.faction_id] = units;
    }catch(e){
      body.innerHTML = `<p class="po-empty">Could not load units.</p>`;
      return;
    }
  }
  state.picker = {units, owned: Object.fromEntries(units.map(u=>[u.id,u.owned]))};
  renderPicker(scopedUnits(units));
}

// Model count + real cost range + owned-from-collection, so a card carries
// what an informed add actually needs (previously: name + one price only).
function pickerMeta(u){
  const bits = [];
  if(u.squad_min){
    bits.push(u.squad_max>u.squad_min
      ? `${u.squad_min}&ndash;${u.squad_max} models` : `${u.squad_min} model${u.squad_min===1?'':'s'}`);
  }
  if(u.owned>0) bits.push(`<span class="po-own">Own ${u.owned}</span>`);
  return bits.length ? `<div class="po-meta">${bits.join(' &middot; ')}</div>` : '';
}

function pickerPts(u){
  if(u.points_min && u.points_max && u.points_max!==u.points_min)
    return `${u.points_min}&ndash;${u.points_max} pts`;
  return u.points ? `${u.points} pts` : '';
}

export function renderPicker(units){
  const body = document.getElementById('pickerBody');
  if(!units||!units.length){ body.innerHTML = `<p class="po-empty">No units found.</p>`; return; }
  const row = u=>{
    const used = unitsUsedCount(u.id);
    const pts = pickerPts(u);
    return `<div class="po-card" data-testid="picker-unit-${esc(u.name)}">
        <img class="po-thumb" src="/api/units/${u.id}/image" alt="" loading="lazy" onclick="togglePickerProfile('${u.id}')">
        <div class="po-body-text" onclick="togglePickerProfile('${u.id}')" title="Show profile">
          <div class="po-name">${esc(u.name)}${u.is_ally?` <span class="modal-ally-tag">${esc(u.ally_faction)}</span>`:''} <span class="po-prof-chev" id="poChev-${u.id}">&#9656;</span></div>
          ${pickerMeta(u)}
          ${used?`<div class="po-owned">${used}&times; Unit In Army</div>`:''}
        </div>
        <div class="po-side">
          ${pts?`<span class="po-pts">${pts}</span>`:''}
          <button class="po-add" type="button" aria-label="Add ${esc(u.name)}" onclick="addUnitToArmy('${u.id}')">+ Add</button>
        </div>
      </div>
      <div class="po-profile" id="poProf-${u.id}" hidden></div>`;
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
  syncOverlayScrim();
}

// Tap a picker card's body to preview the datasheet (statline + weapons)
// in place, before deciding to add it. Lazy-loaded, cached in
// state.unitDetailCache (shared with the right panel + Command Bunker).
export async function togglePickerProfile(did){
  const box = document.getElementById(`poProf-${did}`);
  if(!box) return;
  const opening = box.hidden;
  box.hidden = !opening;
  const chev = document.getElementById(`poChev-${did}`);
  if(chev) chev.innerHTML = opening ? '&#9662;' : '&#9656;';
  if(opening && !box.dataset.loaded){
    box.innerHTML = `<p class="ab-rp-hint">Loading profile&hellip;</p>`;
    let detail = state.unitDetailCache[did];
    if(!detail){
      try{ detail = await api(`/api/units/${did}`); state.unitDetailCache[did] = detail; }
      catch(e){ box.innerHTML = `<p class="ab-rp-hint">Could not load profile.</p>`; return; }
    }
    box.innerHTML = renderProfiles(detail);
    box.dataset.loaded = '1';
  }
}

// Adds instantly and stays open (matches the reference app: "Nx Unit In
// Army" appears on the card so you can keep adding more without leaving the
// picker), rather than the old single-add-then-close modal behaviour.
export async function addUnitToArmy(did){
  if(!state.army) return;
  let res;
  try{ res = await api(`/api/armies/${state.army.id}/units`, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({datasheet_id:did})}); }
  catch(e){ return; }
  if(!res || !res.ok) return;
  state.army.units.push(res.unit);

  // All 4 Force-Org sections already exist in the DOM (renderRoster always
  // renders them), so a full re-render is simpler and correct here -- no
  // surgical per-section DOM creation/insertion-order logic needed.
  const body = document.getElementById('rosterBody');
  if(body) body.innerHTML = renderRoster(state.army.units, state.army.accent);
  applyServerState(res);
  filterPicker(document.getElementById('pickerSearch')?.value || '');
}
