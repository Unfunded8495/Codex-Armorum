import { esc, api } from './utils.js';

export const state = {
  army:        null,
  rightSel:    null,   // {type:'unit'|'battlesize'|'detachment', id?} -> right panel
  picker:      null,
  detachCache: {},
  enhCache:    {},
  unitsCache:  {},
  unitDetailCache: {},   // did -> /api/units/<did> payload (statline + weapons)
  battleSizes: null,
};

// Battle sizes (Incursion / Strike Force / Onslaught) drive the points cap and
// the enhancement / duplicate / detachment limits. Fetched once and cached.
export async function ensureBattleSizes(){
  if(!state.battleSizes) state.battleSizes = await api('/api/battle-sizes');
  return state.battleSizes;
}

// Detachment points limit for a battle size name; null for Custom / unknown,
// which means "no cost filtering — show every detachment".
export function detLimitFor(name){
  const b = (state.battleSizes||[]).find(b=>b.name===name);
  return b ? b.detachment_points_limit : null;
}

// Build <option>s for a detachment <select>, dropping any whose points_cost
// exceeds `limit` (null limit = keep all). Marks `selectedId` as selected.
export function detOptions(dts, selectedId, limit){
  return (dts||[])
    .filter(d => limit == null || (d.points_cost||0) <= limit)
    .map(d => `<option value="${esc(d.id)}" ${d.id===selectedId?'selected':''}>${esc(d.name)}</option>`)
    .join('');
}
