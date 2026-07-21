import { esc, api } from './utils.js';
import { refreshLedger, setBreadcrumb } from './header.js';
import { rlThemeMode, rlWireThemeToggle } from './rl-theme.js';

/* ---- constants ---- */
const STAGES = ['unbuilt','assembled','primed','base_coated','washed','highlighted','finished','display'];
const STAGE_LABELS = {
  unbuilt:'Unbuilt', assembled:'Assembled', primed:'Primed', base_coated:'Base Coated',
  washed:'Washed', highlighted:'Highlighted', finished:'Finished', display:'Display',
};
/* stage bar hues live in collection.css (--cs-stage-*), keyed by data-stage,
   so they follow the light/dark reading toggle */

/* ---- DOM ---- */
const statsBody = document.getElementById('colStatsBody');

/* ---- init ---- */
async function init(){
  setBreadcrumb([
    {label:'My Armies', href:'/'},
    {label:'Paint Progress'},
  ]);
  refreshLedger();
  /* reading mode: the template applies the stored theme pre-paint; here we
     correct the toggle's label and wire the shared flip handler */
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  const themeLabel = document.querySelector('#rlThemeToggle .rl-toggle-label');
  if(themeLabel) themeLabel.textContent = rlThemeMode() === 'dark' ? 'Light' : 'Dark';
  rlWireThemeToggle(document);
  try{
    const [minis, factions] = await Promise.all([
      api('/api/collection'),
      api('/api/factions'),
    ]);
    renderStats(minis, factions);
  }catch(e){
    statsBody.innerHTML = `<div class="rl-error">Could not load collection data.<small>Make sure app.py is running, then refresh.</small></div>`;
  }
}

function renderStats(minis, factions){
  if(!minis.length){
    statsBody.innerHTML = `
      <div class="col-stats-empty">
        <p>No minis in your collection yet.</p>
        <a href="/#/purchases" class="rl-btn">+ Record Purchase</a>
      </div>`;
    return;
  }

  const total   = minis.length;
  const painted = minis.filter(m=>m.stage==='finished'||m.stage==='display').length;
  const pct     = total > 0 ? Math.round(painted/total*100) : 0;

  // Stage breakdown
  const byStageCounts = {};
  for(const s of STAGES) byStageCounts[s] = 0;
  for(const m of minis) byStageCounts[m.stage || 'unbuilt']++;
  const maxStageCount = Math.max(...Object.values(byStageCounts), 1);

  const stageRows = STAGES.map(s=>{
    const count = byStageCounts[s] || 0;
    const barPct = Math.round(count/maxStageCount*100);
    return `<div class="csp-stage-row">
      <span class="csp-stage-label">${STAGE_LABELS[s]}</span>
      <div class="csp-stage-bar-wrap">
        <div class="csp-stage-bar" data-stage="${s}" style="width:${barPct}%"></div>
      </div>
      <span class="csp-stage-count">${count}</span>
    </div>`;
  }).join('');

  // Faction breakdown
  const byFaction = new Map();
  for(const m of minis){
    if(!byFaction.has(m.faction_id)) byFaction.set(m.faction_id, {name:m.faction_display_name || m.faction_name, total:0, done:0});
    const f = byFaction.get(m.faction_id);
    f.total++;
    if(m.stage==='finished'||m.stage==='display') f.done++;
  }

  const factionRows = [...byFaction.entries()]
    .sort(([,a],[,b])=>b.total-a.total)
    .map(([fid, f])=>{
      const fData = factions.find(x=>x.id===fid);
      const accent = fData?.accent || 'var(--gold)';
      const primary = fData?.primary || 'var(--panel)';
      const fPct   = f.total > 0 ? Math.round(f.done/f.total*100) : 0;
      const iconHtml = fData?.icon_url
        ? `<img class="csp-faction-icon" src="${esc(fData.icon_url)}" alt="">`
        : `<span class="csp-faction-initial">${esc(f.name?.[0]||'?')}</span>`;
      const markHtml = fData?.icon_url
        ? `<img src="${esc(fData.icon_url)}" alt="" loading="lazy">`
        : `<span class="faction-bg-letter">${esc(f.name?.[0]||'?')}</span>`;
      return `<a class="csp-faction-row faction-surface" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}" href="/#/faction/${esc(fid)}">
        <span class="faction-bg-mark csp-bg-mark" aria-hidden="true">${markHtml}</span>
        ${iconHtml}
        <span class="csp-faction-name">${esc(f.name)}</span>
        <div class="csp-faction-bar-wrap">
          <div class="csp-faction-bar" style="width:${fPct}%;background:${accent}"></div>
        </div>
        <span class="csp-faction-pct">${f.done}/${f.total}</span>
        <span class="csp-faction-arrow">→</span>
      </a>`;
    }).join('');

  const factionCount = new Set(minis.map(m=>m.faction_id)).size;

  statsBody.innerHTML = `
    <div class="csp-wrap">
      <div class="csp-sidebar">
        <div class="csp-overview">
          <div class="csp-big-stat">
            <span class="csp-big-num">${pct}%</span>
            <span class="csp-big-label">Painted</span>
          </div>
          <div class="csp-big-bar-wrap">
            <div class="csp-big-bar" style="width:${pct}%"></div>
          </div>
          <div class="csp-overview-sub">${painted} of ${total} minis painted</div>
        </div>
        <div class="csp-stat-tiles">
          <div class="csp-stat-tile"><b>${total}</b><span>Minis</span></div>
          <div class="csp-stat-tile"><b>${factionCount}</b><span>Factions</span></div>
          <div class="csp-stat-tile"><b>${total - painted}</b><span>Remaining</span></div>
        </div>
        <div class="csp-card csp-card--stage">
          <h3 class="csp-card-title">By Stage</h3>
          <div class="csp-stage-list">${stageRows}</div>
        </div>
      </div>
      <div class="csp-main">
        <p class="legend">Ten thousand worlds burn at the edges of the Imperium, and yet the true warrior knows that victory begins here, at the desk, under the lamp. Each brushstroke is a prayer offered up in silence. Each finished model, a soldier sworn to service and arrayed in the Emperor's livery, ready for the long war that never truly ends.</p>
        <div class="csp-card">
          <h3 class="csp-card-title">By Faction</h3>
          <div class="csp-faction-list">${factionRows}</div>
        </div>
      </div>
    </div>`;
}

init();
