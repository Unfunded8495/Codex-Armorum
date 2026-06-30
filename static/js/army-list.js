import { esc, api, intOr } from './utils.js';
import { ensureBattleSizes } from './army-state.js';
import { setBreadcrumb } from './header.js';

const view       = document.getElementById('view');

export async function showArmyList(){
  setBreadcrumb([
    {label:'My Armies', href:'/'},
    {label:'Army Builder'},
  ]);
  view.innerHTML = `<div class="loading">Marshalling forces…</div>`;
  let armies;
  try{ armies = await api('/api/armies'); }
  catch(e){
    view.innerHTML=`<div class="loading load-error">Could not reach the server.<br><small>Make sure app.py is running.</small></div>`;
    return;
  }
  view.innerHTML = `
    <h2 class="view-title">Army Builder</h2>
    <p class="view-sub">Create army lists, plan your forces, track what you own and what you need</p>
    <div class="rule"></div>
    <div id="armyGrid" class="army-grid">
      ${armies.map(a=>armyTile(a)).join('')}
    </div>
    <button class="new-army-btn" data-testid="new-army-button" onclick="toggleCreateForm()">✠ Create New Army List</button>
    <button class="new-army-btn new-army-btn--ghost" data-testid="import-button" onclick="importArmyList()">⬆ Import List (JSON)</button>
    <div id="createArmyForm" hidden></div>`;
}

function armyTile(a){
  const pct = a.points_limit>0 ? Math.min(100, Math.round(a.total_points/a.points_limit*100)) : 0;
  const markHtml = a.icon_url
    ? `<img src="${esc(a.icon_url)}" alt="" loading="lazy">`
    : `<span class="faction-bg-letter">${esc((a.faction_display_name || a.faction_name)?.[0]||'?')}</span>`;
  const facLabel = a.faction_display_name || a.faction_name;
  return `<div class="army-tile faction-surface" style="--cardarmy:${a.primary};--cardaccent:${a.accent};--cardglow:${a.accent};--at-accent:${a.accent}" onclick="location.hash='/army/${a.id}'">
    <div class="faction-bg-mark army-tile-mark" aria-hidden="true">${markHtml}</div>
    <button class="army-tile-del" onclick="event.stopPropagation();deleteArmy('${a.id}',this)" title="Delete army">✕</button>
    <div class="army-tile-name">${esc(a.name)}</div>
    <div class="army-tile-meta">${esc(facLabel)}${a.battle_size?' · '+esc(a.battle_size):''}${a.detachment_name?' · '+esc(a.detachment_name):''}</div>
    <div class="army-tile-pts">
      <b>${a.total_points}</b> / ${a.points_limit} pts · ${a.unit_count} unit${a.unit_count===1?'':'s'}
    </div>
    <div style="margin-top:10px;height:4px;background:rgba(44,42,53,.8)">
      <div style="height:100%;width:${pct}%;background:${pct>=100?'var(--blood-bright)':'var(--gold)'};transition:width .3s"></div>
    </div>
  </div>`;
}

export async function deleteArmy(aid, btn){
  if(!confirm('Delete this army list? This cannot be undone.')) return;
  const res = await fetch(`/api/armies/${aid}`, {method:'DELETE'});
  if(!res.ok){ alert('Could not delete army. Please try again.'); return; }
  btn.closest('.army-tile').remove();
}

export function importArmyList(){
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = '.json,application/json';
  inp.onchange = async () => {
    const f = inp.files && inp.files[0];
    if(!f) return;
    let data;
    try { data = JSON.parse(await f.text()); }
    catch(e){ alert('That file is not valid JSON.'); return; }
    try {
      const res = await fetch('/api/armies/import', {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
      const j = await res.json();
      if(res.ok && j.ok && j.id){ location.hash = '/army/' + j.id; }
      else alert('Import failed: ' + (j.error || ('HTTP ' + res.status)));
    } catch(e){ alert('Import failed: ' + e); }
  };
  inp.click();
}

export async function toggleCreateForm(){
  const el = document.getElementById('createArmyForm');
  if(!el.hidden){el.hidden=true;el.innerHTML='';return;}
  let factions, battleSizes;
  try{ [factions, battleSizes] = await Promise.all([api('/api/factions'), ensureBattleSizes()]); }
  catch(e){ alert('Could not load factions.'); return; }
  el.innerHTML = `
    <div class="create-army-form">
      <h3>New Army List</h3>
      <div class="caf-grid">
        <div class="caf-field" style="grid-column:1/-1">
          <label>Army Name</label>
          <input type="text" id="cafName" placeholder="e.g. World Eaters — Tide of Khorne" autocomplete="off">
        </div>
        <div class="caf-field">
          <label>Faction</label>
          <select id="cafFaction" data-testid="faction-select">
            <option value="">— select faction —</option>
            ${factions.map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('')}
          </select>
        </div>
        <div class="caf-field">
          <label>Battle Size</label>
          <select id="cafBattleSize" data-testid="battle-size-select" onchange="onCafBattleSize()">
            ${battleSizes.map(b=>`<option value="${esc(b.name)}" ${b.name==='Strike Force'?'selected':''}>${esc(b.name)} · ${b.points_limit} pts</option>`).join('')}
            <option value="Custom">Custom</option>
          </select>
        </div>
        <div class="caf-field" id="cafPtsField" hidden>
          <label>Points Limit</label>
          <input type="number" id="cafPts" value="2000" min="0" step="100">
        </div>
      </div>
      <div class="ff-actions" style="margin-top:16px">
        <button class="btn-primary" data-testid="create-army-confirm" onclick="submitCreateArmy()">Create Army</button>
        <button class="btn-ghost"   onclick="toggleCreateForm()">Cancel</button>
      </div>
    </div>`;
  el.hidden = false;
  document.getElementById('cafName').focus();
}

// Battle-size change in the create form: reveal the points input only for Custom.
export function onCafBattleSize(){
  const bs = document.getElementById('cafBattleSize')?.value;
  const ptsField = document.getElementById('cafPtsField');
  if(ptsField) ptsField.hidden = bs !== 'Custom';
}

export async function submitCreateArmy(){
  const name  = (document.getElementById('cafName')?.value || '').trim();
  const fid   = document.getElementById('cafFaction')?.value || '';
  const bs    = document.getElementById('cafBattleSize')?.value || 'Strike Force';
  const pts   = intOr(document.getElementById('cafPts')?.value, 2000);
  if(!fid){alert('Please select a faction.');return;}
  let res;
  try {
    res = await api('/api/armies', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name: name||'New Army', faction_id:fid, battle_size:bs, points_limit:pts})});
  } catch(e) {
    alert('Could not reach the server. Please try again.');
    return;
  }
  if(res.ok) location.hash = `/army/${res.id}`;
  else alert(res.error || 'Failed to create army.');
}
