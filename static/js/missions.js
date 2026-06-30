import { esc } from './utils.js';

const view = document.getElementById('view');

// Plain-text fields carry GW's **bold** markers; escape first, then promote pairs.
function fmt(s){ return esc(s || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
function chip(name){ return `<span class="mz-chip">${esc(name || '')}</span>`; }

function primaryCard(m){
  return `<div class="mz-card">
    <h3>${esc(m.name)}</h3>
    ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
    ${m.description ? `<div class="mz-body">${fmt(m.description)}</div>` : ''}
    ${(m.objectives && m.objectives.length)
      ? `<ul class="mz-obj">${m.objectives.map(o =>
          `<li><b>${esc(o.name || '')}</b>${o.when ? ` &mdash; ${fmt(o.when)}` : ''}</li>`).join('')}</ul>`
      : ''}
  </div>`;
}
function secondaryCard(m){
  const tag = `${m.fixed ? 'Fixed' : 'Tactical'}${m.scorable_first_turn ? ' · Scores turn 1' : ''}`;
  return `<div class="mz-card">
    <h3>${esc(m.name)}</h3>
    <span class="mz-tag">${esc(tag)}</span>
    ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
    ${m.description ? `<div class="mz-body">${fmt(m.description)}</div>` : ''}
  </div>`;
}
function twistCard(m){
  return `<div class="mz-card">
    <h3>${esc(m.name)}</h3>
    ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
    ${m.rules ? `<div class="mz-body">${fmt(m.rules)}</div>` : ''}
  </div>`;
}
function presetCard(m, depById, layById){
  return `<div class="mz-card">
    <h3>${esc(m.name)}</h3>
    <div class="mz-sub">Deployment: ${esc(depById[m.deployment_id] || '—')} &middot; Layout: ${esc(layById[m.layout_id] || '—')}</div>
  </div>`;
}

const TABS = [
  {key:'primary',     label:'Primary',     render:d => `<div class="mz-grid">${d.primary.map(primaryCard).join('')}</div>`},
  {key:'secondary',   label:'Secondary',   render:d => `<div class="mz-grid">${d.secondary.map(secondaryCard).join('')}</div>`},
  {key:'deployments', label:'Deployments', render:d => `<div class="mz-names">${d.deployments.map(x => chip(x.name)).join('')}</div>`},
  {key:'layouts',     label:'Layouts',     render:d => `<div class="mz-names">${d.layouts.map(x => chip(x.name)).join('')}</div>`},
  {key:'presets',     label:'Maps',        render:d => {
      const dep = Object.fromEntries(d.deployments.map(x => [x.id, x.name]));
      const lay = Object.fromEntries(d.layouts.map(x => [x.id, x.name]));
      return `<div class="mz-grid">${d.presets.map(m => presetCard(m, dep, lay)).join('')}</div>`;
  }},
  {key:'twists',      label:'Twists',      render:d => `<div class="mz-grid">${d.twists.map(twistCard).join('')}</div>`},
];

let DATA = null, active = 'primary';

function render(){
  if(!DATA) return;
  const pack = (DATA.packs && DATA.packs[0] && DATA.packs[0].name) || 'Matched Play';
  const tab = TABS.find(t => t.key === active) || TABS[0];
  view.innerHTML = `<div data-testid="missions-view">
    <p class="mz-pack">${esc(pack)}</p>
    <p class="mz-intro">Mission reference &mdash; primary &amp; secondary missions, deployments, layouts, maps and twists.</p>
    <div class="mz-tabs">
      ${TABS.map(t => `<button class="mz-tab${t.key === active ? ' is-active' : ''}" data-tab="${t.key}">${esc(t.label)} <span style="opacity:.6">${(DATA[t.key] || []).length}</span></button>`).join('')}
    </div>
    <div class="mz-content">${tab.render(DATA)}</div></div>`;
  view.querySelectorAll('.mz-tab').forEach(b =>
    b.addEventListener('click', () => { active = b.dataset.tab; render(); }));
}

(async () => {
  try {
    DATA = await (await fetch('/api/missions')).json();
    render();
  } catch(e){
    view.innerHTML = `<p class="mz-intro">Failed to load missions: ${esc(String(e))}</p>`;
  }
})();
