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

import { esc, api, readableInk, withTimeout } from './utils.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';

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
   HOME - "My Armies"
   ==================================================================== */
export async function showHome(){
  setActiveNav('armies');
  setBreadcrumb([{label:'My Armies'}]);
  view.innerHTML = `<div class="loading">Mustering the forces…</div>`;
  const summaryPromise = withTimeout(refreshLedger()).catch(() => null);
  let factions;
  try{
    factions = factionCache || (factionCache = await withTimeout(api('/api/factions')));
  }catch(e){
    const isTimeout = e.message === 'timeout';
    view.innerHTML = `<div class="loading load-error">
      ${isTimeout
        ? 'Taking too long to load.<br><small>Is app.py still running in your terminal?</small>'
        : 'Could not reach the server.<br><small>Make sure app.py is running, then refresh.</small>'
      }
    </div>`;
    return;
  }
  try{ unassignedGroups = await withTimeout(api('/api/unassigned-minis')); }
  catch(e){ unassignedGroups = []; }
  const summary = await summaryPromise;

  /* --- aggregate ledger, computed from the faction list (no new API) --- */
  const totalModels   = factions.reduce((n,f)=>n+(f.bought_minis||0),0);
  const totalPainted  = factions.reduce((n,f)=>n+(f.finished_minis||0),0);
  const totalPct      = totalModels>0 ? Math.round(totalPainted/totalModels*100) : 0;
  const ownedArmies   = factions.filter(f=>(f.bought_minis||0)>0).length;

  const isFirstRun = summary && (summary.bought_minis || 0) === 0;
  const firstRunHtml = isFirstRun
    ? `<div class="first-run-banner">
        <div class="frb-icon">&#9876;</div>
        <div class="frb-body">
          <strong>Your collection is empty</strong>
          <p>Start by recording your first purchase. Logging a boxed set creates mini
             entries in your collection that you can then track, paint, and manage.</p>
          <a href="/#/purchases" class="btn-primary" style="text-decoration:none">
            + Record First Purchase
          </a>
        </div>
      </div>`
    : '';

  const favourites    = factions.filter(f=>f.favourite);
  const otherFactions = favourites.length ? factions.filter(f=>!f.favourite) : factions;

  /* masthead: only show the ledger once there's something to count */
  const mastheadHtml = totalModels > 0
    ? `<div class="home-masthead">
        <div>
          <div class="mh-eyebrow">&#10016;&ensp;The Muster Field</div>
          <h2 class="view-title">My Armies</h2>
          <p class="mh-sub">Choose a faction to muster, paint, and expand your collection.</p>
        </div>
        <div class="mh-stats">
          <div class="mh-stat"><b>${totalModels}</b><span>Models</span></div>
          <div class="mh-stat"><b>${totalPainted}</b><span>Painted</span></div>
          <div class="mh-stat"><b>${totalPct}%</b><span>Complete</span></div>
          <div class="mh-stat"><b>${ownedArmies}</b><span>Armies</span></div>
        </div>
      </div>
      <div class="collection-meter">
        <div class="cm-head"><span>Collection Painted</span>
          <span><b>${totalPainted}</b> / ${totalModels} &middot; ${totalPct}%</span></div>
        <div class="cm-track"><div class="cm-fill" style="width:${totalPct}%"></div></div>
      </div>`
    : `<h2 class="view-title">Select an Army</h2>
       <p class="view-sub">Choose a faction to manage your collection</p>`;

  const favouriteHtml = favourites.length
    ? `<section class="favourite-armies">
        <div class="fave-head"><h3>Your Armies</h3><span>${favourites.length}</span></div>
        <div class="faction-grid army-banner-grid">${favourites.map((f,i)=>armyBannerCard(f,i)).join('')}</div>
      </section>`
    : `<section class="favourite-armies is-empty">
        <div class="fave-head"><div><h3>Your Armies</h3>
          <p>Star the armies you use most and they will stay here.</p></div></div>
      </section>`;

  view.innerHTML = `
    ${mastheadHtml}
    <div class="rule"></div>
    ${firstRunHtml}
    ${favouriteHtml}
    <h3 class="army-list-title">${favourites.length?'All Armies':'All Armies'}</h3>
    <div class="faction-grid">${otherFactions.map((f,i)=>factionCard(f,i)).join('')}</div>
    ${unassignedSection(unassignedGroups)}`;
  wireFavouriteButtons();
  wireUnassigned();
}

/* ---- "Your Armies" banner card (favourites) --------------------------
   Uses the photographic banner_url when the app.py patch supplies one;
   otherwise falls back to the tinted gradient + faction glyph so it
   still looks deliberate before you apply that patch. */
function armyBannerCard(f, i){
  const bought   = f.bought_minis || 0;
  const finished = f.finished_minis || 0;
  const pct      = bought>0 ? Math.round(finished/bought*100) : 0;
  const bench    = Math.max(0, bought - finished);
  const dname    = f.display_name || f.name;
  const tag      = bought===0 ? 'New Project'
                 : pct>=100   ? 'Battle Ready'
                 : pct>=60    ? 'Main Force'
                 : 'In Progress';
  const emblem = f.icon_url ? `<img src="${esc(f.icon_url)}" alt="" loading="lazy">` : '';
  const head = f.banner_url
    ? `<div class="abc-head">
         <img src="${esc(f.banner_url)}" alt="${esc(dname)}" loading="lazy">
         <div class="abc-scrim"></div>
         <div class="abc-tag">${esc(tag)}</div>
         ${emblem?`<div class="abc-emblem">${emblem}</div>`:''}
       </div>`
    : `<div class="abc-head is-glyph">
         <div class="abc-tag">${esc(tag)}</div>
         ${emblem?`<div class="abc-emblem">${emblem}</div>`:''}
       </div>`;
  return `
    <div class="army-banner-card" style="--cardarmy:${f.primary};--cardaccent:${f.accent};--cardglow:${f.accent};animation-delay:${i*0.04}s"
         onclick="location.hash='/faction/${f.id}'">
      ${head}
      <button class="abc-fav" type="button" data-fav-fid="${esc(f.id)}"
              title="Remove from favourites" aria-label="Remove ${esc(dname)} from favourites">★</button>
      <div class="abc-body">
        ${f.group?`<div class="abc-group">${esc(f.group)}</div>`:''}
        <div class="abc-name">${esc(dname)}</div>
        <div class="abc-prog-head">
          <span>${finished} / ${bought} Blessed by the Omnissiah</span>
          <span class="abc-pct">${pct}%</span>
        </div>
        <div class="abc-track"><div class="abc-fill" style="width:${pct}%"></div></div>
        <div class="abc-stats">
          <span><b>${bought}</b> models</span>
          <span><b>${bench}</b> undergoing rites</span>
        </div>
      </div>
    </div>`;
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

/* ---- "All Armies" tile (non-favourites) - original treatment kept ---- */
function factionCard(f, i, extraClass=''){
  const fav=!!f.favourite;
  const bought=f.bought_minis||0;
  const finished=f.finished_minis||0;
  const pct=bought>0?Math.round(finished/bought*100):0;
  const dname = f.display_name || f.name;
  const progressBar = bought > 0
    ? `<div class="fc-bar" title="${finished} of ${bought} finished">
         <div class="fc-bar-fill" style="width:${pct}%"></div>
       </div>`
    : '';
  const meta = bought > 0
    ? `${f.unit_count} datasheets &middot; ${bought} bought &middot; ${pct}% done`
    : `${f.unit_count} datasheets`;
  const emblemHtml = f.icon_url
    ? `<img src="${esc(f.icon_url)}" alt="" loading="lazy">`
    : `<span class="emblem-watermark-letter">${esc(f.initial||dname[0]||'?')}</span>`;
  return `<div class="faction-card ${extraClass} ${fav?'is-favourite':''}" style="--cardarmy:${f.primary};--cardaccent:${f.accent};--cardglow:${f.accent};animation-delay:${i*0.03}s"
     onclick="location.hash='/faction/${f.id}'">
    <div class="emblem-watermark" aria-hidden="true">${emblemHtml}</div>
    <button class="fav-toggle ${fav?'is-on':''}" type="button" data-fav-fid="${esc(f.id)}"
            title="${fav?'Remove from favourites':'Add to favourites'}"
            aria-label="${fav?'Remove '+esc(dname)+' from favourites':'Add '+esc(dname)+' to favourites'}"
            >${fav?'★':'☆'}</button>
    <div class="fname">${esc(dname)}</div>
    ${f.group?`<div class="fname-group">${esc(f.group)}</div>`:''}
    ${progressBar}
    <div class="fmeta">${meta}</div>
  </div>`;
}

async function toggleFavouriteFaction(fid, favourite){
  await api(`/api/factions/${encodeURIComponent(fid)}/favourite`, {method: favourite?'DELETE':'POST'});
  factionCache = null;
  showHome();
}

function wireFavouriteButtons(){
  document.querySelectorAll('[data-fav-fid]').forEach(btn=>{
    btn.addEventListener('click', e=>{
      e.stopPropagation();
      const isOn = btn.classList.contains('is-on') || btn.classList.contains('abc-fav');
      toggleFavouriteFaction(btn.dataset.favFid, isOn);
    });
  });
}

/* ====================================================================
   FACTION PAGE
   ==================================================================== */
export async function showFaction(fid, browseAll=false){
  setActiveNav('armies');
  refreshLedger();
  view.innerHTML = `<div class="loading">Consulting the archives…</div>`;

  let fac = factionCache?.find(f=>f.id===fid);
  if(!fac){
    try{
      const fs = factionCache || (factionCache = await withTimeout(api('/api/factions')));
      fac = fs.find(f=>f.id===fid);
    }catch(e){ fac = null; }
  }
  const accent  = fac?.accent  || 'var(--gold)';
  const primary = fac?.primary || 'var(--panel)';
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
    view.innerHTML = `<div class="loading load-error">
      ${isTimeout
        ? 'Taking too long to load.<br><small>Is app.py still running in your terminal?</small>'
        : 'Could not reach the server.<br><small>Make sure app.py is running, then refresh.</small>'
      }
    </div>`;
    return;
  }

  if(browseAll){
    view.innerHTML = renderFactionBrowse(fid, facName, primary, accent, unitPayload?.units || [], minis.length);
    return;
  }

  if(!minis.length){
    view.innerHTML = `
      ${factionHero(fac, fid, facName, primary, accent, 0, 0)}
      <div class="fc-empty">
        <p>You have no minis logged for <strong>${esc(facName)}</strong> yet.</p>
        <div class="fc-empty-actions">
          <a href="/#/purchases" class="btn-primary" style="text-decoration:none">+ Record a Purchase</a>
          <span class="fc-empty-or">or</span>
          <a href="#/faction/${esc(fid)}/browse" class="btn-secondary" style="text-decoration:none">Browse All Datasheets</a>
        </div>
        <p class="fc-empty-hint">Recording a purchase logs the box set and creates
        mini entries that appear here.</p>
      </div>`;
    return;
  }

  const total   = minis.length;
  const painted = minis.filter(m=>isCompleteStage(m.stage)).length;

  const tileObjs = buildUnitTiles({ fid, minis, units: unitPayload?.units || [], primary, accent, facMark });
  const tiles = tileObjs.map(t => t.html).join('');

  /* role filter bar, built from the roles actually present */
  const roleOrder = ['Epic Hero','Character','Battleline','Infantry','Mounted','Beast','Monster','Vehicle','Fortification','Other'];
  const present = [...new Set(tileObjs.map(t => t.role || 'Other'))]
    .sort((a,b)=>{ const ia=roleOrder.indexOf(a), ib=roleOrder.indexOf(b); return (ia<0?99:ia)-(ib<0?99:ib); });
  const tabs = [`<button class="uf-tab is-active" data-role="__all">All Units<span class="uf-count">${tileObjs.length}</span></button>`]
    .concat(present.map(r =>
      `<button class="uf-tab" data-role="${esc(r)}">${esc(r)}<span class="uf-count">${tileObjs.filter(t=>(t.role||'Other')===r).length}</span></button>`
    )).join('');

  view.innerHTML = `
    ${factionHero(fac, fid, facName, primary, accent, total, painted)}
    <div class="unit-filter">
      <div class="unit-filter-tabs">${tabs}</div>
      <div class="unit-legend">
        <span><i class="ul-dot is-done"></i>Blessed by the Omnissiah</span>
        <span><i class="ul-dot is-wip"></i>Undergoing Rites</span>
        <span><i class="ul-dot is-raw"></i>Awaiting the Forge</span>
      </div>
    </div>
    <div class="unit-grid">${tiles}</div>`;
  wireUnitFilter();
}

/* ---- faction hero banner --------------------------------------------- */
function factionHero(fac, fid, facName, primary, accent, total, painted){
  const pct = total>0 ? Math.round(painted/total*100) : 0;
  const emblem = fac?.icon_url ? `<div class="fh-emblem"><img src="${esc(fac.icon_url)}" alt="" loading="lazy"></div>` : '';
  const kicker = fac?.group ? esc(fac.group) : 'Faction';
  const tagline = FACTION_TAGLINE[facName] || `Your ${esc(facName)} collection - mustered, painted, and catalogued.`;
  const hasBanner = !!fac?.banner_url;
  const meterHtml = total>0
    ? `<div class="fh-meter">
         <div class="fhm-head"><span>Collection Painted</span><b>${pct}%</b></div>
         <div class="fhm-track"><div class="fhm-fill" style="width:${pct}%"></div></div>
       </div>` : '';
  return `
    <section class="fac-hero ${hasBanner?'':'is-glyph'}" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}">
      ${hasBanner?`<img class="fac-hero-bg" src="${esc(fac.banner_url)}" alt="${esc(facName)}">`:''}
      <div class="fh-scrim"></div>
      <div class="fh-inner">
        <div style="max-width:560px">
          <div class="fh-eyebrow">${emblem}<div class="fh-kicker">${kicker}</div></div>
          <h1>${esc(facName)}</h1>
          <p class="fh-tagline">${tagline}</p>
          <div class="fh-actions">
            <a href="/#/purchases" class="btn-primary" style="text-decoration:none">+ Record Purchase</a>
            <a href="#/faction/${esc(fid)}/browse" class="btn-secondary" style="text-decoration:none">Browse All Datasheets</a>
          </div>
        </div>
        <div>
          <div class="fh-stats">
            <div class="fh-stat"><b>${total}</b><span>Models</span></div>
            <div class="fh-stat is-accent"><b>${painted}</b><span>Painted</span></div>
            <div class="fh-stat"><b>${pct}%</b><span>Complete</span></div>
          </div>
          ${meterHtml}
        </div>
      </div>
    </section>`;
}

/* role filter - pure DOM show/hide, no re-fetch */
function wireUnitFilter(){
  const tabs = [...document.querySelectorAll('.uf-tab')];
  const cards = [...document.querySelectorAll('.unit-grid .unit-card')];
  tabs.forEach(tab=>{
    tab.addEventListener('click', ()=>{
      tabs.forEach(t=>t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const role = tab.dataset.role;
      cards.forEach(c=>{ c.style.display = (role==='__all' || c.dataset.role===role) ? '' : 'none'; });
    });
  });
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
      <div class="unit-card fc-mini-tile" data-role="${esc(role)}" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}" onclick="location.hash='/mini/${esc(unit.id)}'">
        <div class="unit-thumb is-niche">
          <div class="niche-shadow"></div>
          <img src="${cutImg}" onerror="${onerr}" alt="${esc(unit.name)}" loading="lazy">
          <span class="role-tag">${esc(role)}</span>
          <span class="pts">${purchased} models</span>
          ${wip>0?`<span class="bench-tag">Undergoing Rites</span>`:''}
        </div>
        <div class="unit-body faction-surface">
          <div class="faction-bg-mark" aria-hidden="true">${facMark}</div>
          <div class="unit-name">${esc(unit.name)}</div>${sharedNote}
          <div class="fc-unit-bar-wrap">
            <div class="fc-unit-bar" style="width:${uPct}%;background:${accent}"></div>
          </div>
          <div class="fc-unit-stats is-tri">
            <span><i class="ul-dot is-done"></i><b>${complete}</b> Blessed</span>
            <span><i class="ul-dot is-wip"></i><b>${wip}</b> Rites</span>
            <span><i class="ul-dot is-raw"></i><b>${buildable}</b> Forge</span>
          </div>
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
          <img src="/api/units/${esc(u.id)}/image" alt="${esc(u.name)}" loading="lazy">
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
    <h2 class="view-title" style="color:${readableInk(accent)}">${esc(facName)}</h2>
    <div class="fc-summary">
      <span><b>${total}</b> datasheets</span>
      <span class="fc-sep">&middot;</span>
      <span><b>${ownedCount}</b> mini${ownedCount===1?'':'s'} owned</span>
      <a href="#/faction/${esc(fid)}" class="btn-secondary fc-add-btn" style="text-decoration:none">Owned Minis</a>
    </div>
    <div class="rule" style="background:linear-gradient(90deg,transparent,${accent},transparent)"></div>
    <div class="unit-grid">${tiles}</div>`;
}
