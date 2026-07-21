/* =====================================================================
   static/js/home.js  -  CODEX ARMORUM redesign drop-in
   ---------------------------------------------------------------------
   Same exports, same data sources, same routes as the original. What
   changed is purely presentation:
     • showHome()  - adds an aggregate masthead + collection meter, and
                     renders favourites as photo "banner" cards.
     • showFaction() - adds a hero banner, a role filter bar, and the
                     dark display-niche unit tiles.
     • buildUnitTiles() - now also returns `role`, emits the niche thumb,
                     and requests the cut-out image (?cut=1) with a clean
                     fallback chain when no cutout exists yet.
   Requires the style.additions.css block and (optionally) the app.py
   patch that adds `banner_url` to /api/factions and serves ?cut=1 images.
   Everything degrades gracefully if that patch is not applied.
   ===================================================================== */

import { esc, api, withTimeout } from './utils.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';
import { rlThemeMode, rlThemeToggleHtml, rlWireThemeToggle } from './rl-theme.js';

const view       = document.getElementById('view');
let factionCache = null;
let unassignedGroups = [];
export function clearFactionCache(){ factionCache = null; }

const isCompleteStage = stage => stage === 'finished' || stage === 'display';

/* Short flavour line per faction name; falls back to the group/display name.
   Purely cosmetic - extend or trim freely. Keyed on faction.name from
   w40k.db so chapter cards (e.g. Blood Angels) can have their own line too. */
const FACTION_TAGLINE = {
  'Adeptus Astartes': 'The Adeptus Astartes stand vigil over a dying Imperium.',
  'Astra Militarum':  'Countless masses of the Astra Militarum hold the line.',
  'Necrons':          'The Necrons wake from sixty million years of slumber.',
  'Tyranids':         'The great devourer hungers, and the stars grow dark.',
  'Adeptus Custodes': 'The Talons of the Emperor answer to no mortal authority.',
  'Aeldari':          'The Aeldari walk the knife-edge between glory and ruin.',
};

/* ====================================================================
   HOME - "My Armies"  (PDF-manual paper shell)
   Shared skin lives in spa-shell.css (body.rl-spa) and rl-theme.js; the
   home-only rail + index components live in my-armies.css. A random
   featured hero, a rail of starred armies, and an allegiance-grouped
   index of every faction. Star state persists through the favourites
   API; light/dark reading mode is the shared caRules.theme toggle.
   ==================================================================== */
const AM_ALLEGIANCE = ['Imperium', 'Chaos', 'Xenos'];
let amFilter = 'all';        // 'all' | 'Imperium' | 'Chaos' | 'Xenos'
let amHeroId = null;         // random starred army, fixed until page reload

function amPct(f){ const b = f.bought_minis || 0; return b > 0 ? Math.round((f.finished_minis||0)/b*100) : 0; }
function amTagFor(f){
  const bought = f.bought_minis || 0;
  if(!bought) return 'New Project';
  const pct = amPct(f);
  if(pct >= 100) return 'Battle Ready';
  if(pct >= 60)  return 'Main Force';
  return 'In Progress';
}

export async function showHome(){
  setActiveNav('armies');
  setBreadcrumb([{label:'My Armies'}]);
  document.body.classList.add('rl-spa', 'home-armies');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  view.innerHTML = amStrip(null) + amShell(
    `<div class="rl-load"><div class="rl-load-bar"></div>` +
    `<div class="rl-load-note">Mustering the forces…</div></div>`);
  amWireStrip();

  const summaryPromise = withTimeout(refreshLedger()).catch(() => null);
  let factions;
  try{
    factions = factionCache || (factionCache = await withTimeout(api('/api/factions')));
  }catch(e){
    const isTimeout = e.message === 'timeout';
    view.innerHTML = amStrip(null) + amShell(`<div class="rl-error">${
      isTimeout
        ? 'Taking too long to load.<small>Is app.py still running in your terminal?</small>'
        : 'Could not reach the server.<small>Make sure app.py is running, then refresh.</small>'
      }</div>`);
    amWireStrip();
    return;
  }
  try{ unassignedGroups = await withTimeout(api('/api/unassigned-minis')); }
  catch(e){ unassignedGroups = []; }
  await summaryPromise;
  renderMyArmies();
}

/* ---- shell + muster strip skeleton ---------------------------------- */
function amShell(inner){
  return `<div class="rl-shell"><div class="rl-wrap">${inner}</div></div>`;
}
function amStrip(chips){
  const chipHtml = (chips || []).map(c =>
    `<button type="button" class="rl-chip${c.active?' is-active':''}" data-am-filter="${esc(c.key)}">` +
    `${esc(c.label)}<b>${c.count}</b></button>`).join('');
  return `
    <nav class="rl-strip" aria-label="Allegiance filter">
      <span class="rl-strip-label">The Muster Field</span>
      ${chipHtml}
      <span class="rl-strip-spacer"></span>
      ${rlThemeToggleHtml()}
    </nav>`;
}

/* ---- the whole home view, rebuilt from cache + state (no refetch) ---- */
function renderMyArmies(){
  const factions = factionCache || [];
  const favs   = factions.filter(f=>f.favourite).slice().sort((a,b)=>(b.bought_minis||0)-(a.bought_minis||0));
  const others = factions.filter(f=>!f.favourite);

  /* chip counts = non-starred factions per allegiance */
  const counts = { all: others.length };
  AM_ALLEGIANCE.forEach(a => counts[a] = others.filter(f=>f.allegiance===a).length);
  const chips = [{key:'all', label:'All', count:counts.all, active:amFilter==='all'}]
    .concat(AM_ALLEGIANCE.map(a => ({key:a, label:a, count:counts[a], active:amFilter===a})));

  /* featured hero: a random starred army, chosen once and kept until reload;
     falls back to the top favourite if it was unstarred so it never blanks */
  if(amHeroId === null && favs.length) amHeroId = favs[Math.floor(Math.random()*favs.length)].id;
  const hf = favs.find(f=>f.id===amHeroId) || favs[0] || null;

  /* aggregate foot line */
  const totalModels  = factions.reduce((n,f)=>n+(f.bought_minis||0),0);
  const totalPainted = factions.reduce((n,f)=>n+(f.finished_minis||0),0);
  const totalPct     = totalModels>0 ? Math.round(totalPainted/totalModels*100) : 0;
  const ownedArmies  = factions.filter(f=>(f.bought_minis||0)>0).length;

  /* grouped index, allegiance order, filtered */
  const groups = AM_ALLEGIANCE
    .map(a => ({key:a, facs: others.filter(f=>f.allegiance===a)}))
    .filter(g => g.facs.length && (amFilter==='all' || amFilter===g.key));

  const railNote  = `${favs.length} starred · your active projects`;
  const indexNote = `${amFilter==='all' ? others.length+' factions' : amFilter} · star one to muster it`;
  const railHtml  = favs.length
    ? `<div class="am-rail">${favs.map(f=>amRailCard(f, !!(hf && f.id===hf.id))).join('')}</div>` : '';

  const inner = `
    ${amHeroHtml(hf)}
    <div class="rl-sect-head">
      <span class="rl-sect-tag">Your Armies</span>
      <span class="rl-sect-note">${esc(railNote)}</span>
      <span class="rl-sect-rule"></span>
    </div>
    ${railHtml}
    <div class="rl-sect-head is-index">
      <span class="rl-sect-tag">All Armies</span>
      <span class="rl-sect-note">${esc(indexNote)}</span>
      <span class="rl-sect-rule"></span>
    </div>
    ${groups.map(amGroupHtml).join('')}
    ${unassignedGroups.length ? unassignedSection(unassignedGroups) : ''}
    <div class="rl-foot">
      <div class="rl-foot-rule"></div>
      <div class="rl-foot-text">&#10016;&nbsp; ${ownedArmies} armies mustered &middot; ${totalModels} models &middot; ${totalPct}% blessed by the Omnissiah &nbsp;&#10016;</div>
    </div>`;

  view.innerHTML = amStrip(chips) + amShell(inner);
  amWireStrip();
  amWireCards();
  wireUnassigned();
}

/* ---- featured hero --------------------------------------------------- */
function amHeroHtml(hf){
  if(!hf){
    return `<div class="rl-hero is-empty">
      <div class="rl-hero-inner"><div class="rl-hero-copy">
        <div class="rl-hero-eyebrow"><span class="rl-hero-flag">Featured Army</span></div>
        <h1 class="rl-hero-name" style="font-size:30px">No featured army</h1>
        <p class="rl-hero-tagline">Star an army below and it will muster here.</p>
      </div></div></div>`;
  }
  const dname   = hf.display_name || hf.name;
  const group   = hf.group || hf.parent_display_name || 'Faction';
  const tagline = FACTION_TAGLINE[hf.name] || FACTION_TAGLINE[dname]
                || `Your ${dname} collection, mustered and catalogued.`;
  const pct = amPct(hf);
  const art = hf.banner_url
    ? `<img class="rl-hero-art" src="${esc(hf.banner_url)}" alt="${esc(dname)}" loading="lazy">` : '';
  return `
    <a class="rl-hero" href="#/faction/${esc(hf.id)}" style="--am-primary:${esc(hf.primary)};--am-accent:${esc(hf.accent)}">
      ${art}
      <div class="rl-hero-scrim-h"></div>
      <div class="rl-hero-scrim-v"></div>
      <div class="rl-hero-inner">
        <div class="rl-hero-copy">
          <div class="rl-hero-eyebrow">
            <span class="rl-hero-flag">Featured Army</span>
            <span class="rl-hero-group">${esc(group)}</span>
          </div>
          <h1 class="rl-hero-name">${esc(dname)}</h1>
          <p class="rl-hero-tagline">${esc(tagline)}</p>
          <span class="rl-hero-cta">Muster the Legion&ensp;&rsaquo;</span>
        </div>
        <div class="rl-hero-side">
          <div class="rl-plate">
            <div class="rl-plate-cell"><b>${hf.bought_minis||0}</b><span>Models</span></div>
            <div class="rl-plate-cell is-accent"><b>${hf.finished_minis||0}</b><span>Painted</span></div>
            <div class="rl-plate-cell"><b>${pct}%</b><span>Blessed</span></div>
          </div>
          <div class="rl-hero-track"><div class="rl-hero-fill" style="width:${pct}%"></div></div>
        </div>
      </div>
      <button type="button" class="rl-hero-star" data-fav-fid="${esc(hf.id)}"
              title="Remove from Your Armies" aria-label="Remove ${esc(dname)} from Your Armies">&#9733;</button>
    </a>`;
}

/* ---- starred-army rail card ----------------------------------------- */
function amRailCard(f, featured){
  const dname = f.display_name || f.name;
  const pct   = amPct(f);
  const tag   = featured ? '★ Featured' : amTagFor(f);
  const banner = f.banner_url
    ? `<img class="am-railhead-art" src="${esc(f.banner_url)}" alt="" loading="lazy">` : '';
  const glyph  = f.icon_url ? `<img src="${esc(f.icon_url)}" alt="" loading="lazy">` : '';
  return `
    <a class="am-railcard${featured?' is-featured':''}" href="#/faction/${esc(f.id)}"
       style="--am-primary:${esc(f.primary)};--am-accent:${esc(f.accent)}">
      <div class="am-railhead">
        ${banner}
        <div class="am-railhead-scrim"></div>
        <span class="am-railtag">${esc(tag)}</span>
        <div class="am-railglyph">${glyph}</div>
        <button type="button" class="am-railstar" data-fav-fid="${esc(f.id)}"
                title="Remove from Your Armies" aria-label="Remove ${esc(dname)} from Your Armies">&#9733;</button>
      </div>
      <div class="am-railbody">
        <div class="am-railname">${esc(dname)}</div>
        <div class="am-railprog"><span>${f.finished_minis||0} / ${f.bought_minis||0} blessed</span><b>${pct}%</b></div>
        <div class="rl-track"><div class="rl-track-fill" style="width:${pct}%"></div></div>
      </div>
    </a>`;
}

/* ---- one allegiance section of the index ---------------------------- */
function amGroupHtml(g){
  return `
    <section class="rl-group">
      <div class="rl-group-head">
        <span class="rl-group-title">${esc(g.key)}</span>
        <span class="rl-group-count">${g.facs.length} factions</span>
      </div>
      <div class="am-index-grid">${g.facs.map(amIndexCard).join('')}</div>
    </section>`;
}

/* ---- index card (non-starred faction) ------------------------------- */
function amIndexCard(f){
  const dname = f.display_name || f.name;
  const owned = (f.bought_minis||0) > 0;
  const pct   = amPct(f);
  const meta  = owned
    ? `${f.unit_count} sheets &middot; ${f.bought_minis} owned &middot; ${pct}%`
    : `${f.unit_count} datasheets`;
  const glyph = f.icon_url ? `<img src="${esc(f.icon_url)}" alt="" loading="lazy">` : '';
  const bar   = owned
    ? `<div class="am-lift-bar"><div class="rl-track-fill" style="width:${pct}%"></div></div>` : '';
  return `
    <a class="am-lift" href="#/faction/${esc(f.id)}" style="--am-primary:${esc(f.primary)};--am-accent:${esc(f.accent)}">
      <div class="am-lift-wm">${glyph}</div>
      <div class="am-lift-row">
        <span class="am-glyph">${glyph}</span>
        <div class="am-lift-text">
          <div class="am-name">${esc(dname)}</div>
          <div class="am-meta">${meta}</div>
        </div>
        <button type="button" class="am-star" data-fav-fid="${esc(f.id)}"
                title="Add ${esc(dname)} to Your Armies" aria-label="Add ${esc(dname)} to Your Armies">&#9734;</button>
      </div>
      ${bar}
    </a>`;
}

/* ---- wiring: strip (filter + theme) and cards (stars) --------------- */
function amWireStrip(){
  document.querySelectorAll('[data-am-filter]').forEach(btn=>{
    btn.addEventListener('click', ()=>{ amFilter = btn.dataset.amFilter; renderMyArmies(); });
  });
  rlWireThemeToggle(document);
}
function amWireCards(){
  document.querySelectorAll('.rl-shell [data-fav-fid], .rl-hero [data-fav-fid]').forEach(btn=>{
    btn.addEventListener('click', e=>{
      e.preventDefault(); e.stopPropagation();
      amToggleFav(btn.dataset.favFid);
    });
  });
}

/* Optimistic star toggle: flip the cached faction, re-render instantly so it
   jumps between rail and index, then persist. Revert + re-render on failure. */
function amToggleFav(fid){
  const f = (factionCache||[]).find(x=>x.id===fid);
  if(!f) return;
  const was = !!f.favourite;
  f.favourite = !was;
  renderMyArmies();
  api(`/api/factions/${encodeURIComponent(fid)}/favourite`, {method: was ? 'DELETE' : 'POST'})
    .catch(()=>{ f.favourite = was; renderMyArmies(); });
}

/* ====================================================================
   Unassigned minis (safety net) - unchanged behaviour
   ==================================================================== */
function unassignedSection(groups){
  if(!groups || !groups.length) return '';
  const total = groups.reduce((n,g)=>n+(g.count||0),0);
  return `
    <section class="unassigned-armies">
      <div class="fave-head">
        <div><h3>⚠ Unassigned Minis</h3>
          <p>Purchased minis with no datasheet - they don't show under any army. Assign each to a unit to file it.</p>
        </div>
        <span>${total}</span>
      </div>
      <div class="faction-grid">${groups.map((g,i)=>unassignedCard(g,i)).join('')}</div>
    </section>`;
}

function unassignedCard(g, idx){
  const imgSrc = g.image_url || '/static/images/warhammer_40_000_logo.png';
  return `
    <div class="unit-card unassigned-card" data-ua-idx="${idx}" style="--cardarmy:var(--panel);--cardaccent:var(--gold);--cardglow:var(--gold)">
      <div class="unit-thumb">
        <img src="${esc(imgSrc)}" alt="${esc(g.name)}" loading="lazy">
        <span class="pts">${g.count}</span>
      </div>
      <div class="unit-body faction-surface">
        <div class="unit-name">${esc(g.name)}</div>
        <div class="fc-unit-stats">
          <span>${esc(g.faction_label || 'No army')}</span>
          <span class="ua-warn">No datasheet</span>
        </div>
        <button class="btn-secondary ua-assign-btn" type="button" data-ua-idx="${idx}">Assign datasheet</button>
        <div class="ua-picker" data-ua-idx="${idx}" hidden>
          <input class="ff-input ua-search" type="search" placeholder="Search datasheets…" autocomplete="off">
          <div class="ua-results"><div class="ua-hint">Type a unit name to search.</div></div>
        </div>
      </div>
    </div>`;
}

function wireUnassigned(){
  document.querySelectorAll('.ua-assign-btn').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const idx = btn.dataset.uaIdx;
      const picker = document.querySelector(`.ua-picker[data-ua-idx="${idx}"]`);
      if(!picker) return;
      const opening = picker.hidden;
      picker.hidden = !opening;
      btn.textContent = opening ? 'Cancel' : 'Assign datasheet';
      if(opening) picker.querySelector('.ua-search')?.focus();
    });
  });
  document.querySelectorAll('.ua-picker').forEach(picker=>{
    const idx = picker.dataset.uaIdx;
    const input = picker.querySelector('.ua-search');
    const results = picker.querySelector('.ua-results');
    let timer;
    input?.addEventListener('input', ()=>{
      clearTimeout(timer);
      timer = setTimeout(()=>uaSearch(idx, input.value, results), 220);
    });
  });
}

async function uaSearch(idx, q, resultsEl){
  const g = unassignedGroups[idx];
  if(!g || !resultsEl) return;
  const trimmed = (q||'').trim();
  if(!trimmed){ resultsEl.innerHTML = '<div class="ua-hint">Type a unit name to search.</div>'; return; }
  resultsEl.innerHTML = '<div class="ua-hint">Searching…</div>';
  try{
    const params = new URLSearchParams({q:trimmed});
    if(g.faction_id) params.set('faction_id', g.faction_id);
    const rows = await api(`/api/units/search?${params}`);
    if(!rows.length){ resultsEl.innerHTML = '<div class="ua-hint">No datasheets found.</div>'; return; }
    resultsEl.innerHTML = rows.slice(0,12).map(u=>`
      <button class="ua-result" type="button" data-did="${esc(u.id)}" data-name="${esc(u.name)}">
        <span class="ua-result-name">${esc(u.name)}</span>
        <span class="ua-result-meta">${esc(u.role||'')}${u.faction_id?' · '+esc(u.faction_id):''}</span>
      </button>`).join('');
    resultsEl.querySelectorAll('.ua-result').forEach(b=>{
      b.addEventListener('click', ()=>uaAssign(idx, b.dataset.did, b.dataset.name, resultsEl));
    });
  }catch(e){
    resultsEl.innerHTML = `<div class="ua-hint ua-err">Search failed: ${esc(e.message)}</div>`;
  }
}

async function uaAssign(idx, datasheetId, datasheetName, resultsEl){
  const g = unassignedGroups[idx];
  if(!g) return;
  resultsEl.innerHTML = `<div class="ua-hint">Filing ${g.count} mini${g.count===1?'':'s'} under ${esc(datasheetName)}…</div>`;
  try{
    const res = await api('/api/minis/assign-datasheet', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mini_ids:g.mini_ids, datasheet_id:datasheetId}),
    });
    if(!res.ok) throw new Error(res.error || 'Assign failed');
    clearFactionCache();
    refreshLedger();
    showHome();
  }catch(e){
    resultsEl.innerHTML = `<div class="ua-hint ua-err">${esc(e.message)}</div>`;
  }
}

/* The "All Armies" index card, favourites banner card and favourite-button
   wiring now live in the My Armies render pipeline above (amIndexCard,
   amRailCard, amWireCards, amToggleFav). */

/* ====================================================================
   FACTION PAGE
   ==================================================================== */
export async function showFaction(fid, browseAll=false){
  setActiveNav('armies');
  refreshLedger();
  document.body.classList.add('rl-spa', 'faction-roster');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  view.innerHTML = facStrip(null) + amShell(
    `<div class="rl-load"><div class="rl-load-bar"></div>` +
    `<div class="rl-load-note">Consulting the archives…</div></div>`);
  facWireStrip();

  let fac = factionCache?.find(f=>f.id===fid);
  if(!fac){
    try{
      const fs = factionCache || (factionCache = await withTimeout(api('/api/factions')));
      fac = fs.find(f=>f.id===fid);
    }catch(e){ fac = null; }
  }
  const accent  = fac?.accent  || '#c79a3a';
  const primary = fac?.primary || '#4a4a4a';
  const facName = fac?.display_name || fac?.name || fid;
  const facMark = fac?.icon_url
    ? `<img src="${esc(fac.icon_url)}" alt="" loading="lazy">`
    : `<span class="faction-bg-letter">${esc(facName?.[0]||'?')}</span>`;

  setBreadcrumb([
    {label:'My Armies', href:'#/'},
    browseAll ? {label:facName, href:`#/faction/${fid}`} : {label:facName},
    ...(browseAll ? [{label:'All Datasheets'}] : []),
  ]);

  let minis, unitPayload;
  try{
    [minis, unitPayload] = await withTimeout(Promise.all([
      api(`/api/collection?faction_id=${encodeURIComponent(fid)}`),
      api(`/api/factions/${encodeURIComponent(fid)}/units`),
    ]));
  }
  catch(e){
    const isTimeout = e.message === 'timeout';
    view.innerHTML = facStrip(null) + amShell(`<div class="rl-error">${
      isTimeout
        ? 'Taking too long to load.<small>Is app.py still running in your terminal?</small>'
        : 'Could not reach the server.<small>Make sure app.py is running, then refresh.</small>'
      }</div>`);
    facWireStrip();
    return;
  }

  if(browseAll){
    view.innerHTML = facStrip(null) + amShell(renderFactionBrowse(fid, facName, primary, accent, unitPayload?.units || [], minis.length));
    facWireStrip();
    return;
  }

  if(!minis.length){
    view.innerHTML = facStrip(null) + amShell(`
      ${factionHero(fac, fid, facName, 0, 0)}
      <div class="fc-empty">
        <p>You have no minis logged for <strong>${esc(facName)}</strong> yet.</p>
        <div class="fc-empty-actions">
          <a href="/#/purchases" class="rl-btn" style="text-decoration:none">+ Record a Purchase</a>
          <span class="fc-empty-or">or</span>
          <a href="#/faction/${esc(fid)}/browse" class="rl-btn rl-btn--ghost" style="text-decoration:none">Browse All Datasheets</a>
        </div>
        <p class="fc-empty-hint">Recording a purchase logs the box set and creates
        mini entries that appear here.</p>
      </div>`);
    facWireStrip();
    return;
  }

  const total   = minis.length;
  const painted = minis.filter(m=>isCompleteStage(m.stage)).length;

  const tileObjs = buildUnitTiles({ fid, minis, units: unitPayload?.units || [], primary, accent, facMark });

  /* group the tiles into stacked role sections (design: grouped by role) */
  const roleOrder = ['Epic Hero','Character','Battleline','Infantry','Mounted','Beast','Monster','Vehicle','Fortification','Other'];
  const byRole = new Map();
  tileObjs.forEach(t => { const r = t.role || 'Other'; if(!byRole.has(r)) byRole.set(r, []); byRole.get(r).push(t); });
  const present = [...byRole.keys()]
    .sort((a,b)=>{ const ia=roleOrder.indexOf(a), ib=roleOrder.indexOf(b); return (ia<0?99:ia)-(ib<0?99:ib); });

  const roleChips = [{key:'__all', label:'All Units', count:tileObjs.length, active:true}]
    .concat(present.map(r => ({key:r, label:r, count:byRole.get(r).length, active:false})));

  const sections = present.map(r => {
    const list = byRole.get(r);
    return `
      <section class="fac-role-section rl-group" data-role="${esc(r)}">
        <div class="rl-group-head">
          <span class="rl-group-title">${esc(r)}</span>
          <span class="rl-group-count">${list.length} ${list.length===1?'unit':'units'}</span>
        </div>
        <div class="unit-grid">${list.map(t=>t.html).join('')}</div>
      </section>`;
  }).join('');

  view.innerHTML = facStrip(roleChips) + amShell(`
    ${factionHero(fac, fid, facName, total, painted)}
    <div class="fac-legend">
      <span><i class="ul-dot is-done"></i>Blessed by the Omnissiah</span>
      <span><i class="ul-dot is-wip"></i>Undergoing Rites</span>
      <span><i class="ul-dot is-raw"></i>Awaiting the Forge</span>
    </div>
    ${sections}`);
  facWireStrip();
}

/* ---- faction reading strip (back + role filter + theme) -------------- */
function facStrip(roleChips){
  const chipHtml = (roleChips || []).map(c =>
    `<button type="button" class="rl-chip${c.active?' is-active':''}" data-fac-role="${esc(c.key)}">` +
    `${esc(c.label)}<b>${c.count}</b></button>`).join('');
  return `
    <nav class="rl-strip" aria-label="Role filter">
      <a class="rl-back" href="#/">&lsaquo; My Armies</a>
      ${chipHtml}
      <span class="rl-strip-spacer"></span>
      ${rlThemeToggleHtml()}
    </nav>`;
}
function facWireStrip(){
  const chips = [...document.querySelectorAll('[data-fac-role]')];
  const sections = [...document.querySelectorAll('.fac-role-section')];
  chips.forEach(chip => chip.addEventListener('click', ()=>{
    chips.forEach(c => c.classList.toggle('is-active', c === chip));
    const role = chip.dataset.facRole;
    sections.forEach(s => { s.style.display = (role === '__all' || s.dataset.role === role) ? '' : 'none'; });
  }));
  rlWireThemeToggle(document);
}

/* ---- faction hero (paper; shared .rl-hero) --------------------------- */
function factionHero(fac, fid, facName, total, painted){
  const primary = fac?.primary || '#4a4a4a';
  const accent  = fac?.accent  || '#c79a3a';
  const pct = total>0 ? Math.round(painted/total*100) : 0;
  const group = fac?.group || fac?.parent_display_name || 'Faction';
  const tagline = FACTION_TAGLINE[facName] || FACTION_TAGLINE[fac?.name]
                || `Your ${facName} collection, mustered and catalogued.`;
  const emblem = fac?.icon_url
    ? `<span class="rl-hero-emblem"><img src="${esc(fac.icon_url)}" alt="" loading="lazy"></span>` : '';
  const art = fac?.banner_url
    ? `<img class="rl-hero-art" src="${esc(fac.banner_url)}" alt="${esc(facName)}" loading="lazy">` : '';
  return `
    <section class="rl-hero" style="--am-primary:${esc(primary)};--am-accent:${esc(accent)}">
      ${art}
      <div class="rl-hero-scrim-h"></div>
      <div class="rl-hero-scrim-v"></div>
      <div class="rl-hero-inner">
        <div class="rl-hero-copy">
          <div class="rl-hero-eyebrow">${emblem}<span class="rl-hero-group">${esc(group)}</span></div>
          <h1 class="rl-hero-name">${esc(facName)}</h1>
          <p class="rl-hero-tagline">${esc(tagline)}</p>
          <div class="rl-hero-actions">
            <a class="rl-btn" href="/#/purchases">+ Record Purchase</a>
            <a class="rl-btn rl-btn--ghost" href="#/faction/${esc(fid)}/browse">Browse All Datasheets</a>
          </div>
        </div>
        <div class="rl-hero-side">
          <div class="rl-plate">
            <div class="rl-plate-cell"><b>${total}</b><span>Models</span></div>
            <div class="rl-plate-cell is-accent"><b>${painted}</b><span>Painted</span></div>
            <div class="rl-plate-cell"><b>${pct}%</b><span>Complete</span></div>
          </div>
          <div class="rl-hero-track"><div class="rl-hero-fill" style="width:${pct}%"></div></div>
        </div>
      </div>
    </section>`;
}

/* ====================================================================
   Shared unit-tile builder - now returns role + niche thumb + cutout img
   ==================================================================== */
export function buildUnitTiles({ fid, minis, units, primary, accent, facMark }){
  const unitStats = new Map((units || []).map(u => [u.id, u]));
  const completeByDid = new Map();
  const unitMap = new Map();
  const addUnitMini = (did, name, mini, potential=false) => {
    if(!unitMap.has(did)){
      unitMap.set(did, { id:did, name, minis:[], potential:false });
    }
    const unit = unitMap.get(did);
    unit.minis.push(mini);
    unit.potential = unit.potential || potential;
  };
  for(const m of (minis || [])){
    addUnitMini(m.datasheet_id, m.datasheet_name, m, false);
    if(isCompleteStage(m.stage)) completeByDid.set(m.datasheet_id, (completeByDid.get(m.datasheet_id) || 0) + 1);
    if((m.stage || 'unbuilt') !== 'unbuilt') continue;
    for(const opt of (m.multikit_options || [])){
      if(opt.faction_id !== fid || opt.datasheet_id === m.datasheet_id) continue;
      addUnitMini(opt.datasheet_id, opt.name, {
        ...m,
        datasheet_id: opt.datasheet_id,
        datasheet_name: opt.name,
        faction_id: opt.faction_id,
        faction_name: opt.faction_name,
        faction_display_name: opt.faction_display_name || opt.faction_name,
        is_potential_build: true,
      }, true);
    }
  }

  const sharedCompleteCount = did => {
    const stat = unitStats.get(did);
    const groups = stat?.multikit_groups || [];
    if(!groups.length) return completeByDid.get(did) || 0;
    const memberIds = new Set();
    groups.forEach(g => (g.members || []).forEach(member => memberIds.add(member)));
    let complete = 0;
    memberIds.forEach(member => { complete += completeByDid.get(member) || 0; });
    return complete;
  };

  return [...unitMap.values()].map(unit=>{
    const stat = unitStats.get(unit.id);
    const role = stat?.role || 'Other';
    const purchased = Math.max(Number(stat?.bought || 0), unit.minis.length);
    const complete = completeByDid.get(unit.id) || 0;
    const sharedComplete = sharedCompleteCount(unit.id);
    const wip = unit.minis.filter(m => {
      const s = m.stage || 'unbuilt';
      return s !== 'unbuilt' && !isCompleteStage(s);
    }).length;
    const buildable = Math.max(0, purchased - sharedComplete - wip);
    const uPct = purchased > 0 ? Math.round(complete/purchased*100) : 0;
    const stageClass = wip > 0 ? 'is-wip' : (complete >= purchased && purchased > 0 ? 'is-done' : 'is-raw');
    const stageLabel = wip > 0 ? 'Undergoing Rites' : (complete >= purchased && purchased > 0 ? 'Blessed' : 'Awaiting the Forge');
    const repCid = unit.minis.find(m => !m.is_potential_build && m.catalogue_model_id)?.catalogue_model_id;
    const baseImg = repCid ? `/api/model-catalogue/${encodeURIComponent(repCid)}/image` : `/api/units/${esc(unit.id)}/image`;
    const unitImg = `/api/units/${esc(unit.id)}/image`;
    // Request the cut-out first; fall back to the un-cut image, then the unit glyph.
    const cutImg = `${baseImg}${baseImg.includes('?')?'&':'?'}cut=1`;
    const onerr = `if(!this.dataset.f){this.dataset.f=1;this.src='${baseImg}';}else if(this.src.indexOf('${unitImg}')<0){this.src='${unitImg}';this.onerror=null;}else{this.onerror=null;}`;

    const sharedPool = (stat?.multikit_groups || [])
      .reduce((sum, g) => sum + Number(g.pool || 0), 0);
    const siblingNames = new Set();
    (stat?.multikit_groups || []).forEach(g => (g.members || []).forEach(mid => {
      if(mid === unit.id) return;
      const nm = unitStats.get(mid)?.name;
      if(nm) siblingNames.add(nm);
    }));
    const sharedNote = sharedPool > 0 ? `
          <div class="fc-shared-note" title="${esc(siblingNames.size
              ? `${sharedPool} of these come from one multi-build kit you can build as ${[...siblingNames].join(' / ')} instead - those models count once across all of these options.`
              : `${sharedPool} of these come from a multi-build kit and can be built as only one option.`)}">
            <span class="fc-shared-ico" aria-hidden="true">⚒</span>${sharedPool} shared multi-build kit
          </div>` : '';

    const html = `
      <div class="unit-card fc-mini-tile fc-army-card" data-role="${esc(role)}" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}" onclick="location.hash='/mini/${esc(unit.id)}'">
        <div class="fc-card-cap">
          <span class="fc-card-cap-sigil" aria-hidden="true">${facMark}</span>
          <span class="fc-card-role">${esc(role)}</span>
        </div>
        <div class="unit-thumb is-niche">
          <div class="niche-shadow"></div>
          <img src="${cutImg}" onerror="${onerr}" alt="${esc(unit.name)}" loading="lazy">
        </div>
        <div class="fc-card-status">
          <span class="fc-card-models"><b>${purchased}</b> ${purchased===1?'model':'models'}</span>
          <span class="fc-card-stage ${stageClass}">${stageLabel}</span>
        </div>
        <div class="unit-body faction-surface">
          <div class="faction-bg-mark" aria-hidden="true">${facMark}</div>
          <div class="unit-name">${esc(unit.name)}</div>
          <div class="fc-card-divider" aria-hidden="true"><span>${facMark}</span></div>
          <div class="fc-unit-bar-wrap">
            <div class="fc-unit-bar" style="width:${uPct}%;background:${accent}"></div>
          </div>
          <div class="fc-unit-stats is-tri">
            <span class="fc-card-stat is-done"><i class="ul-dot is-done"></i><small>Blessed</small><b>${complete}</b></span>
            <span class="fc-card-stat is-wip"><i class="ul-dot is-wip"></i><small>Rites</small><b>${wip}</b></span>
            <span class="fc-card-stat is-raw"><i class="ul-dot is-raw"></i><small>Forge</small><b>${buildable}</b></span>
          </div>
          ${sharedNote}
        </div>
      </div>`;
    return { id: unit.id, faction_id: fid, role, html };
  });
}

function renderFactionBrowse(fid, facName, primary, accent, units, ownedCount){
  const total = units.length;
  const tiles = units.map(u => {
    const owned = Number(u.owned || 0);
    const bought = Number(u.bought || 0);
    const unlogged = Number(u.unlogged || 0);
    const status = [
      owned ? `${owned} owned` : '',
      bought && bought !== owned ? `${bought} purchased` : '',
      unlogged ? `${unlogged} unlogged` : '',
    ].filter(Boolean).join(' / ') || 'Not in collection';
    return `
      <div class="unit-card fc-mini-tile" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}" onclick="location.hash='/unit/${esc(u.id)}'">
        <div class="unit-thumb">
          ${u.has_image === false ? `
          <div class="fc-ph" aria-hidden="true">
            <span class="fc-ph-letter">${esc((facName || '?')[0])}</span>
            <span class="fc-ph-label">No reference image</span>
          </div>` : `
          <img src="/api/units/${esc(u.id)}/image" alt="${esc(u.name)}" loading="lazy">`}
          ${u.points?`<span class="pts">${esc(String(u.points))} pts</span>`:''}
        </div>
        <div class="unit-body faction-surface">
          <div class="unit-name">${esc(u.name)}</div>
          <div class="fc-unit-stats">
            <span>${esc(u.role || 'Other')}</span>
            <span>${esc(status)}</span>
          </div>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="rl-sect-head">
      <span class="rl-sect-tag">${esc(facName)}</span>
      <span class="rl-sect-note">${total} datasheets &middot; ${ownedCount} owned</span>
      <span class="rl-sect-rule"></span>
    </div>
    <div class="fc-summary">
      <a href="#/faction/${esc(fid)}" class="rl-btn rl-btn--ghost fc-add-btn" style="text-decoration:none">Owned Minis</a>
    </div>
    ${total ? `<div class="unit-grid">${tiles}</div>` : `<p class="rl-error">No datasheets found for this faction.</p>`}`;
}
