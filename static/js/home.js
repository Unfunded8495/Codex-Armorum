import { esc, api, readableInk, withTimeout } from './utils.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';

const view       = document.getElementById('view');
let factionCache = null;
let unassignedGroups = [];
export function clearFactionCache(){ factionCache = null; }

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
  const favouriteHtml = favourites.length
    ? `<section class="favourite-armies">
        <div class="fave-head"><h3>Favourite Armies</h3><span>${favourites.length}</span></div>
        <div class="faction-grid fave-grid">${favourites.map((f,i)=>factionCard(f,i,'fave-card')).join('')}</div>
      </section>`
    : `<section class="favourite-armies is-empty">
        <div class="fave-head"><div><h3>Favourite Armies</h3>
          <p>Star the armies you use most and they will stay here.</p></div></div>
      </section>`;
  view.innerHTML = `
    <h2 class="view-title">Select an Army</h2>
    <p class="view-sub">Choose a faction to manage your collection</p>
    <div class="rule"></div>
    ${firstRunHtml}
    ${favouriteHtml}
    <h3 class="army-list-title">${favourites.length?'All Other Armies':'All Armies'}</h3>
    <div class="faction-grid">${otherFactions.map((f,i)=>factionCard(f,i)).join('')}</div>
    ${unassignedSection(unassignedGroups)}`;
  wireFavouriteButtons();
  wireUnassigned();
}

/* ---- Unassigned minis (safety net) ----
   Minis whose unit_bsdata_id no longer resolves to a datasheet are invisible to every
   faction view. Surface them here so they can be filed under a unit. Hidden when none. */
function unassignedSection(groups){
  if(!groups || !groups.length) return '';
  const total = groups.reduce((n,g)=>n+(g.count||0),0);
  return `
    <section class="unassigned-armies">
      <div class="fave-head">
        <div><h3>⚠ Unassigned Minis</h3>
          <p>Purchased minis with no datasheet — they don't show under any army. Assign each to a unit to file it.</p>
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
      toggleFavouriteFaction(btn.dataset.favFid, btn.classList.contains('is-on'));
    });
  });
}

export async function showFaction(fid, browseAll=false){
  setActiveNav('armies');
  refreshLedger();
  view.innerHTML = `<div class="loading">Consulting the archives…</div>`;

  // Resolve faction info from cache
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
      <h2 class="view-title" style="color:${readableInk(accent)}">${esc(facName)}</h2>
      <div class="rule" style="background:linear-gradient(90deg,transparent,${accent},transparent)"></div>
      <div class="fc-empty">
        <p>You have no minis logged for <strong>${esc(facName)}</strong> yet.</p>
        <div class="fc-empty-actions">
          <a href="/#/purchases" class="btn-primary" style="text-decoration:none">
            + Record a Purchase
          </a>
          <span class="fc-empty-or">or</span>
          <a href="#/faction/${esc(fid)}/browse" class="btn-secondary" style="text-decoration:none">
            Browse All Datasheets
          </a>
        </div>
        <p class="fc-empty-hint">Recording a purchase logs the box set and creates
        mini entries that appear here.</p>
      </div>`;
    return;
  }

  // Group minis by datasheet, expanding unresolved multikits into buildable choices.
  const unitStats = new Map((unitPayload?.units || []).map(u => [u.id, u]));
  const completeByDid = new Map();
  const unitMap = new Map();
  const isCompleteStage = stage => stage === 'finished' || stage === 'display';
  const addUnitMini = (did, name, mini, potential=false) => {
    if(!unitMap.has(did)){
      unitMap.set(did, { id:did, name, minis:[], potential:false });
    }
    const unit = unitMap.get(did);
    unit.minis.push(mini);
    unit.potential = unit.potential || potential;
  };
  for(const m of minis){
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

  const total   = minis.length;
  const painted = minis.filter(m=>isCompleteStage(m.stage)).length;
  const pct     = total > 0 ? Math.round(painted/total*100) : 0;

  const tiles = [...unitMap.values()].map(unit=>{
    const stat = unitStats.get(unit.id);
    const purchased = Math.max(Number(stat?.bought || 0), unit.minis.length);
    const complete = completeByDid.get(unit.id) || 0;
    const sharedComplete = sharedCompleteCount(unit.id);
    // WIP = started but not finished (any stage past 'unbuilt' that isn't complete).
    // Potential multikit builds are always unbuilt, so they never land here.
    const wip = unit.minis.filter(m => {
      const s = m.stage || 'unbuilt';
      return s !== 'unbuilt' && !isCompleteStage(s);
    }).length;
    // Buildable is now only the un-started (unbuilt) models: carve WIP out of the
    // not-complete pool so buildable + WIP + complete reads as the full count.
    const buildable = Math.max(0, purchased - sharedComplete - wip);
    const uPct = purchased > 0 ? Math.round(complete/purchased*100) : 0;
    const repCid = unit.minis.find(m => !m.is_potential_build && m.catalogue_model_id)?.catalogue_model_id;
    const imgSrc = repCid ? `/api/model-catalogue/${encodeURIComponent(repCid)}/image` : `/api/units/${esc(unit.id)}/image`;
    const imgFallback = `/api/units/${esc(unit.id)}/image`;

    // Multi-build kits: some of this unit's "purchased" count comes from a kit that
    // can be built as one of several datasheets. Flag the shared pool so the tile is
    // not read as that many extra physical models.
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
              ? `${sharedPool} of these come from one multi-build kit you can build as ${[...siblingNames].join(' / ')} instead — those models count once across all of these options.`
              : `${sharedPool} of these come from a multi-build kit and can be built as only one option.`)}">
            <span class="fc-shared-ico" aria-hidden="true">⚒</span>${sharedPool} shared multi-build kit
          </div>` : '';

    return `
      <div class="unit-card fc-mini-tile" style="--cardarmy:${primary};--cardaccent:${accent};--cardglow:${accent}" onclick="location.hash='/mini/${esc(unit.id)}'">
        <div class="unit-thumb">
          <img src="${imgSrc}" onerror="this.src='${imgFallback}';this.onerror=null" alt="${esc(unit.name)}" loading="lazy">
          <span class="pts">${purchased} purchased</span>
        </div>
        <div class="unit-body faction-surface">
          <div class="faction-bg-mark" aria-hidden="true">${facMark}</div>
          <div class="unit-name">${esc(unit.name)}</div>${sharedNote}
          <div class="fc-unit-bar-wrap">
            <div class="fc-unit-bar" style="width:${uPct}%;background:${accent}"></div>
          </div>
          <div class="fc-unit-stats">
            <span>${buildable} buildable</span>
            <span class="fc-stat-wip">${wip} WIP</span>
            <span>${complete} Complete</span>
          </div>
        </div>
      </div>`;
  }).join('');

  view.innerHTML = `
    <h2 class="view-title" style="color:${readableInk(accent)}">${esc(facName)}</h2>
    <div class="fc-summary">
      <span><b>${total}</b> mini${total===1?'':'s'} owned</span>
      <span class="fc-sep">·</span>
      <span><b>${painted}</b> painted</span>
      <span class="fc-sep">·</span>
      <span><b>${pct}%</b> complete</span>
      <a href="/#/purchases" class="btn-secondary fc-add-btn" style="text-decoration:none">+ Record Purchase</a>
    </div>
    <div class="rule" style="background:linear-gradient(90deg,transparent,${accent},transparent)"></div>
    <div class="unit-grid">${tiles}</div>`;
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
