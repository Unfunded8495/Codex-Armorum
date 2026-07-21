/* History view — Codex Armorum archive.
   #/history          : edition timeline, page-level search, faction cards grid.
   #/history/<label>  : one faction's models grouped edition → year → model, newest first.

   Editions and the catalogue are joined only at runtime via the per-edition era
   ranges (era_start / era_end). No `edition` field is ever written into the
   model catalogue. */
import { esc, api, readableInk, withTimeout } from './utils.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';
import { rlThemeMode, rlThemeToggleHtml, rlWireThemeToggle } from './rl-theme.js';

const view = document.getElementById('view');

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

let editionsCache = null;   // ascending by edition number
let cardsCache    = null;   // faction cards (one per canonical label)
let itemsCache    = null;   // full catalogue items
let currentDrill  = null;   // { label, accent } of the open faction drill-in, for post-save refresh

/* ---- data loaders -------------------------------------------------------- */
async function loadEditions(){
  if(editionsCache) return editionsCache;
  const doc = await withTimeout(api('/api/editions'));
  editionsCache = (doc.editions || []).slice().sort((a,b)=>(a.edition||0)-(b.edition||0));
  return editionsCache;
}
async function loadCards(){
  if(cardsCache) return cardsCache;
  const res = await withTimeout(api('/api/model-catalogue/faction-cards'));
  cardsCache = res.cards || [];
  return cardsCache;
}
async function loadItems(){
  if(itemsCache) return itemsCache;
  const res = await withTimeout(api('/api/model-catalogue'));
  itemsCache = res.items || [];
  return itemsCache;
}

/* ---- paper shell + reading strip (shared skin: spa-shell.css) ------------ */
function histShell(inner){
  return `<div class="rl-shell"><div class="rl-wrap">${inner}</div></div>`;
}
function histStrip(backToAll){
  return `
    <nav class="rl-strip" aria-label="Codex Archive">
      ${backToAll
        ? `<a class="rl-back" href="#/history">&lsaquo; Codex Archive</a>`
        : `<span class="rl-strip-label">The Codex Archive</span>`}
      <span class="rl-strip-spacer"></span>
      ${rlThemeToggleHtml()}
    </nav>`;
}

function loadError(e, backToAll = false){
  const isTimeout = e && e.message === 'timeout';
  view.innerHTML = histStrip(backToAll) + histShell(`<div class="rl-error">
    ${isTimeout
      ? 'Taking too long to load.<small>Is app.py still running in your terminal?</small>'
      : 'Could not reach the server.<small>Make sure app.py is running, then refresh.</small>'}
  </div>`);
  rlWireThemeToggle(document);
}

/* ---- date / edition helpers ---------------------------------------------- */
function releaseYearOf(item){
  if(Number.isFinite(item.release_year)) return item.release_year;
  const d = item.release_date || '';
  const m = /^(\d{4})/.exec(d);
  return m ? parseInt(m[1],10) : null;
}

// month 1-12 when the catalogue gives YYYY-MM, else null (year-only / undated)
function releaseMonthOf(item){
  const m = /^\d{4}-(\d{2})/.exec(item.release_date || '');
  return m ? parseInt(m[1],10) : null;
}

function fmtModelDate(item){
  const d = item.release_date || '';
  const m = /^(\d{4})-(\d{2})/.exec(d);
  if(m) return `${MONTHS[parseInt(m[2],10)-1] || ''} ${m[1]}`.trim();
  if(item.release_year) return String(item.release_year);
  return 'Date unknown';
}

// Assign a model to an edition by its era ranges. Returns the edition object or null.
// YYYY-MM → edition whose [era_start, next era_start) contains it. Year-only →
// bucket by 1 July of that year (and the row is flagged undated for the year group).
function editionForItem(editionsAsc, item){
  let key, undated = false;
  const d = item.release_date || '';
  if(/^\d{4}-\d{2}/.test(d)){
    key = d.slice(0,7);
  } else if(releaseYearOf(item)){
    key = `${releaseYearOf(item)}-07`;
    undated = true;
  } else {
    return { edition:null, undated:true };
  }
  let chosen = null;
  for(const e of editionsAsc){
    if(e.era_start && e.era_start <= key) chosen = e; else if(e.era_start) break;
  }
  return { edition: chosen, undated };
}

function eraLabel(ed){
  if(!ed) return '';
  const sy = (ed.era_start || '').slice(0,4);
  const ey = (ed.era_end || '').slice(0,4);
  if(!sy) return '';
  return ey ? `${sy} to ${ey}` : `${sy} to present`;
}

function editionReleaseLabel(ed){
  const d = ed.release_date || '';
  if(ed.release_precision === 'day'){
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
    if(m) return `${m[3]} ${MONTHS[parseInt(m[2],10)-1]} ${m[1]}`;
  }
  const m = /^(\d{4})-(\d{2})/.exec(d);
  if(m && ed.release_precision === 'month') return `${MONTHS[parseInt(m[2],10)-1]} ${m[1]}`;
  return (d || '').slice(0,4);
}

/* ======================================================================== */
/*  History home: timeline + search + faction cards                          */
/* ======================================================================== */
export async function showHistory(){
  setActiveNav('history');
  setBreadcrumb([{label:'Codex Archive'}]);
  refreshLedger();
  document.body.classList.add('rl-spa', 'codex-archive');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  view.innerHTML = histStrip(false) + histShell(
    `<div class="rl-load"><div class="rl-load-bar"></div>` +
    `<div class="rl-load-note">Unsealing the archives…</div></div>`);
  rlWireThemeToggle(document);

  let editions, cards;
  try{
    [editions, cards] = await Promise.all([loadEditions(), loadCards()]);
  }catch(e){ return loadError(e); }

  const displayCounts = cards.reduce((counts, card) => {
    counts.set(card.display_name, (counts.get(card.display_name) || 0) + 1);
    return counts;
  }, new Map());
  const labelledCards = cards.map(card => ({
    ...card,
    source_label: displayCounts.get(card.display_name) > 1 ? card.faction_label : '',
  }));

  view.innerHTML = histStrip(false) + histShell(`
    <h2 class="view-title">Codex Archive</h2>
    <p class="view-sub">Forty years of war, edition by edition</p>

    <div class="rl-sect-head">
      <span class="rl-sect-tag">Edition Timeline</span>
      <span class="rl-sect-note">${editions.length} editions &middot; select one for its chronicle</span>
      <span class="rl-sect-rule"></span>
    </div>
    <section class="hist-timeline-section" aria-label="Edition timeline">
      ${renderTimeline(editions)}
      <div class="tl-detail" id="tlDetail" hidden></div>
    </section>

    <div class="hist-search-wrap">
      <input id="histSearch" class="ff-input hist-search" type="search"
             placeholder="Search factions and models…" autocomplete="off" aria-label="Search the archive">
      <button id="histSearchClear" class="hist-search-clear" type="button" hidden aria-label="Clear search">&times;</button>
    </div>

    <div class="hist-results" id="histResults" hidden></div>

    <div class="rl-sect-head">
      <span class="rl-sect-tag">Factions</span>
      <span class="rl-sect-note">${labelledCards.length} catalogued</span>
      <span class="rl-sect-rule"></span>
    </div>
    <div class="faction-grid hist-card-grid" id="histCardGrid">
      ${labelledCards.map((c,i)=>factionCard(c,i)).join('')}
    </div>
    <p class="hist-empty" id="histCardEmpty" hidden>No factions match that search.</p>`);

  wireTimeline(editions);
  wirePageSearch(labelledCards);
  rlWireThemeToggle(document);
}

function renderTimeline(editions){
  const nodes = editions.map(e=>{
    const year = (e.release_date || '').slice(0,4);
    const current = e.is_current ? ' is-current' : '';
    return `
      <li class="tl-node${current}" data-ed="${e.edition}" tabindex="0" role="button"
          aria-label="${esc(e.full_title || e.name)} — released ${esc(editionReleaseLabel(e))}">
        <span class="tl-year">${esc(year)}</span>
        <span class="tl-dot" aria-hidden="true"></span>
        <span class="tl-name">${esc(e.name)}</span>
        ${e.is_current ? '<span class="tl-flag">Current</span>' : ''}
      </li>`;
  }).join('');
  return `<div class="tl-track"><ol class="tl-list">${nodes}</ol></div>`;
}

function wireTimeline(editions){
  const detail = document.getElementById('tlDetail');
  const byEd = new Map(editions.map(e=>[String(e.edition), e]));
  let openEd = null;
  const nodes = [...document.querySelectorAll('.tl-node')];
  const open = (node)=>{
    const ed = byEd.get(node.dataset.ed);
    if(!ed) return;
    if(openEd === node.dataset.ed){            // toggle closed
      detail.hidden = true; openEd = null;
      nodes.forEach(n=>n.classList.remove('is-open'));
      return;
    }
    openEd = node.dataset.ed;
    nodes.forEach(n=>n.classList.toggle('is-open', n===node));
    detail.innerHTML = renderEditionDetail(ed);
    detail.hidden = false;
  };
  nodes.forEach(node=>{
    node.addEventListener('click', ()=>open(node));
    node.addEventListener('keydown', e=>{ if(e.key==='Enter' || e.key===' '){ e.preventDefault(); open(node); } });
  });
}

function renderEditionDetail(ed){
  const projected = !ed.era_end && ed.projected_era_end
    ? `<span class="tl-projected">Current · projected end ${esc(ed.projected_era_end.slice(0,4))} (community estimate, not confirmed by Games Workshop)</span>`
    : '';
  const list = (arr) => (arr && arr.length)
    ? `<ul class="tl-d-list">${arr.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>` : '';
  const box = ed.launch_box
    ? `<p class="tl-d-line"><b>Launch box:</b> ${esc(ed.launch_box)}${ed.launch_box_note ? ` — ${esc(ed.launch_box_note)}` : ''}</p>` : '';
  return `
    <div class="tl-detail-card">
      <div class="tl-d-head">
        <h3>${esc(ed.full_title || ed.name)}</h3>
        <span class="tl-d-era">${esc(eraLabel(ed))}</span>
      </div>
      <p class="tl-d-line"><b>Released:</b> ${esc(editionReleaseLabel(ed))}
        ${ed.box_factions && ed.box_factions.length ? ` · <b>Box factions:</b> ${esc(ed.box_factions.join(', '))}` : ''}</p>
      ${projected ? `<p class="tl-d-line">${projected}</p>` : ''}
      ${box}
      ${ed.rules_summary ? `<p class="tl-d-summary">${esc(ed.rules_summary)}</p>` : ''}
      <div class="tl-d-cols">
        ${ed.key_changes && ed.key_changes.length ? `<div><h4>Key changes</h4>${list(ed.key_changes)}</div>` : ''}
        ${ed.iconic_models && ed.iconic_models.length ? `<div><h4>Iconic models</h4>${list(ed.iconic_models)}</div>` : ''}
      </div>
      ${ed.narrative_hook ? `<p class="tl-d-hook">${esc(ed.narrative_hook)}</p>` : ''}
    </div>`;
}

function factionCard(c, i){
  const ink = readableInk(c.accent);
  const years = c.year_min && c.year_max
    ? (c.year_min === c.year_max ? `${c.year_min}` : `${c.year_min}–${c.year_max}`)
    : '';
  const img = c.image_url
    ? `<img class="hfc-img" src="${esc(c.image_url)}" alt="" loading="lazy"
            onerror="this.classList.add('is-broken');this.removeAttribute('src')">`
    : '';
  const source = c.source_label ? `${c.source_label} catalogue` : '';
  const ariaName = source ? `${c.display_name} (${source})` : c.display_name;
  return `
    <button type="button" class="hist-faction-card" data-label="${esc(c.faction_label)}"
        data-search="${esc(`${c.display_name} ${c.faction_label}`.toLowerCase())}"
        style="--cardarmy:${c.primary};--cardaccent:${c.accent};animation-delay:${i*0.025}s"
        aria-label="${esc(ariaName)} — ${c.count} models">
      <span class="hfc-media" aria-hidden="true">
        ${img}
        <span class="hfc-fallback">${esc(c.initial)}</span>
        <span class="hfc-scrim"></span>
      </span>
      <span class="hfc-body">
        <span class="hfc-name" style="color:${ink}">${esc(c.display_name)}</span>
        ${source ? `<span class="hfc-source">${esc(source)}</span>` : ''}
        <span class="hfc-meta"><b>${c.count}</b> model${c.count===1?'':'s'}${years?` · ${years}`:''}</span>
      </span>
    </button>`;
}

/* ---- page-level search: filter cards + surface matching models ----------- */
function wirePageSearch(cards){
  const input   = document.getElementById('histSearch');
  const clearBtn= document.getElementById('histSearchClear');
  const grid    = document.getElementById('histCardGrid');
  const empty   = document.getElementById('histCardEmpty');
  const results = document.getElementById('histResults');
  if(!input) return;
  let timer;

  const openFaction = label => { location.hash = '/history/' + encodeURIComponent(label); };
  grid.querySelectorAll('.hist-faction-card').forEach(btn=>{
    btn.addEventListener('click', ()=>openFaction(btn.dataset.label));
  });

  const filterCards = q => {
    let shown = 0;
    grid.querySelectorAll('.hist-faction-card').forEach(btn=>{
      const hit = !q || btn.dataset.search.includes(q);
      btn.style.display = hit ? '' : 'none';
      if(hit) shown++;
    });
    empty.hidden = shown !== 0;
  };

  const run = async () => {
    const raw = input.value.trim();
    const q = raw.toLowerCase();
    clearBtn.hidden = !raw;
    filterCards(q);
    if(raw.length < 2){ results.hidden = true; results.innerHTML = ''; return; }
    results.hidden = false;
    results.innerHTML = `<div class="hist-results-head">Searching…</div>`;
    try{
      const rows = await api(`/api/model-catalogue/search?q=${encodeURIComponent(raw)}`);
      if(!rows.length){
        results.innerHTML = `<div class="hist-results-head">No models match “${esc(raw)}”.</div>`;
        return;
      }
      results.innerHTML = `
        <div class="hist-results-head">${rows.length} matching model${rows.length===1?'':'s'}</div>
        <div class="hist-results-list">
          ${rows.map(r=>`
            <button type="button" class="hist-result-row" data-label="${esc(r.faction_label)}">
              <span class="hrr-name">${esc(r.name)}</span>
              <span class="hrr-meta">${esc(r.faction_label.split(' - ').pop())}${r.release_year?` · ${esc(String(r.release_year))}`:''}${r.material?` · ${esc(r.material)}`:''}</span>
            </button>`).join('')}
        </div>`;
      results.querySelectorAll('.hist-result-row').forEach(btn=>{
        btn.addEventListener('click', ()=>openFaction(btn.dataset.label));
      });
    }catch(e){
      results.innerHTML = `<div class="hist-results-head hist-err">Search failed: ${esc(e.message)}</div>`;
    }
  };

  input.addEventListener('input', ()=>{ clearTimeout(timer); timer = setTimeout(run, 220); });
  clearBtn.addEventListener('click', ()=>{ input.value=''; input.focus(); run(); });
}

/* ======================================================================== */
/*  Faction drill-in: models grouped edition → year → model                  */
/* ======================================================================== */
export async function showHistoryFaction(label){
  setActiveNav('history');
  refreshLedger();
  document.body.classList.add('rl-spa', 'codex-archive');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  view.innerHTML = histStrip(true) + histShell(
    `<div class="rl-load"><div class="rl-load-bar"></div>` +
    `<div class="rl-load-note">Consulting the archives…</div></div>`);
  rlWireThemeToggle(document);

  let editions, items, cards;
  try{
    [editions, items, cards] = await Promise.all([loadEditions(), loadItems(), loadCards()]);
  }catch(e){ return loadError(e, true); }

  const card = cards.find(c=>c.faction_label === label);
  const facItems = items.filter(it => it.faction_label === label);
  const display = card ? card.display_name : label.split(' - ').pop();
  const primary = card ? card.primary : 'var(--panel)';
  const accent  = card ? card.accent  : 'var(--gold)';
  const ink     = readableInk(accent);
  currentDrill = { label, accent };

  setBreadcrumb([
    {label:'Codex Archive', href:'#/history'},
    {label: display},
  ]);

  view.innerHTML = histStrip(true) + histShell(`
    <div class="hist-faction-head" style="--cardaccent:${accent};--cardarmy:${primary}">
      <h2 class="view-title hist-faction-title" style="color:${ink}">${esc(display)}</h2>
      <div class="hist-faction-search">
        <input id="histFacSearch" class="ff-input" type="search"
               placeholder="Search within ${esc(display)}…" autocomplete="off" aria-label="Search within faction">
      </div>
    </div>
    <div class="fc-summary hist-faction-summary">
      <span><b>${facItems.length}</b> model${facItems.length===1?'':'s'} catalogued</span>
    </div>
    <div class="rule" style="background:linear-gradient(90deg,transparent,${accent},transparent)"></div>
    <div class="hist-drill" id="histDrill">${renderGroups(editions, facItems, accent)}</div>`);

  wireFactionSearch(label, editions, facItems, accent);
  rlWireThemeToggle(document);

  // Delegated so it keeps working after the drill body is re-rendered (search / edits).
  const drill = document.getElementById('histDrill');
  drill.addEventListener('click', e=>{
    const row = e.target.closest('.hist-model-row');
    if(row && row.dataset.cid) openModelEditor(row.dataset.cid);
  });
  drill.addEventListener('keydown', e=>{
    if(e.key !== 'Enter' && e.key !== ' ') return;
    const row = e.target.closest('.hist-model-row');
    if(row && row.dataset.cid){ e.preventDefault(); openModelEditor(row.dataset.cid); }
  });
}

// Build edition → year → model grouping, all newest first.
function groupItems(editionsAsc, items){
  const editionsDesc = editionsAsc.slice().sort((a,b)=>(b.edition||0)-(a.edition||0));
  const byEdition = new Map();   // edition number (or 'unknown') → { ed, years:Map<year,{dated:[],undated:[]}> }
  for(const it of items){
    const { edition, undated } = editionForItem(editionsAsc, it);
    const edKey = edition ? edition.edition : 'unknown';
    if(!byEdition.has(edKey)) byEdition.set(edKey, { ed: edition, years: new Map() });
    const bucket = byEdition.get(edKey);
    const year = releaseYearOf(it) || 'Unknown';
    if(!bucket.years.has(year)) bucket.years.set(year, { dated:[], undated:[] });
    (undated ? bucket.years.get(year).undated : bucket.years.get(year).dated).push(it);
  }

  const orderedEditions = [];
  for(const ed of editionsDesc){
    if(byEdition.has(ed.edition)) orderedEditions.push({ ed, bucket: byEdition.get(ed.edition) });
  }
  if(byEdition.has('unknown')) orderedEditions.push({ ed:null, bucket: byEdition.get('unknown') });

  for(const grp of orderedEditions){
    grp.years = [...grp.bucket.years.entries()]
      .sort((a,b)=>{
        const ya = a[0]==='Unknown' ? -1 : a[0];
        const yb = b[0]==='Unknown' ? -1 : b[0];
        return yb - ya;
      })
      .map(([year, sets])=>{
        sets.dated.sort((x,y)=> (releaseMonthOf(y)-releaseMonthOf(x)) || (x.name||'').localeCompare(y.name||''));
        sets.undated.sort((x,y)=> (x.name||'').localeCompare(y.name||''));
        return { year, models: sets.dated, undated: sets.undated };
      });
  }
  return orderedEditions;
}

function renderGroups(editionsAsc, items, accent){
  if(!items.length){
    return `<p class="hist-empty">No models catalogued for this faction yet.</p>`;
  }
  const groups = groupItems(editionsAsc, items);
  return groups.map(grp=>{
    const heading = grp.ed
      ? `${esc(grp.ed.name)} <span class="hist-era">(${esc(eraLabel(grp.ed))})</span>`
      : `Undated <span class="hist-era">(no edition match)</span>`;
    const years = grp.years.map(y=>{
      const rows = [
        ...y.models.map(m=>modelRow(m, accent)),
        ...(y.undated.length
          ? [`<div class="hist-undated-label">Year only</div>`, ...y.undated.map(m=>modelRow(m, accent))]
          : []),
      ].join('');
      return `
        <div class="hist-year-group">
          <div class="hist-year">${esc(String(y.year))}</div>
          <div class="hist-rows">${rows}</div>
        </div>`;
    }).join('');
    return `
      <section class="hist-edition-group">
        <h3 class="hist-edition-head">${heading}</h3>
        ${years}
      </section>`;
  }).join('');
}

function modelRow(item, accent){
  const imgUrl = item.image && item.image.url ? item.image.url : '';
  const thumb = imgUrl
    ? `<img src="${esc(imgUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
       <span class="hist-thumb-ph" style="display:none">${esc((item.name||'?')[0])}</span>`
    : `<span class="hist-thumb-ph" style="display:flex">${esc((item.name||'?')[0])}</span>`;
  const disc = item.status === 'discontinued' ? `<span class="hist-disc">Discontinued</span>` : '';
  return `
    <div class="hist-model-row" data-cid="${esc(item.id)}" role="button" tabindex="0"
         aria-label="Edit ${esc(item.name)}" title="Edit this model">
      <div class="hist-thumb" style="border-color:${accent}">${thumb}</div>
      <div class="hist-model-main">
        <div class="hist-model-name">${esc(item.name)}</div>
        <div class="hist-model-meta">${esc(fmtModelDate(item))}${item.material?` · ${esc(item.material)}`:''}</div>
      </div>
      ${disc}
      <span class="hist-row-edit" aria-hidden="true">Edit</span>
    </div>`;
}

/* ---- in-card search: scope to this faction via the search endpoint -------- */
function wireFactionSearch(label, editions, facItems, accent){
  const input = document.getElementById('histFacSearch');
  const drill = document.getElementById('histDrill');
  if(!input || !drill) return;
  let timer;
  const run = async () => {
    const raw = input.value.trim();
    if(raw.length < 2){ drill.innerHTML = renderGroups(editions, facItems, accent); return; }
    drill.innerHTML = `<div class="loading">Searching…</div>`;
    try{
      const rows = await api(`/api/model-catalogue/search?faction_label=${encodeURIComponent(label)}&q=${encodeURIComponent(raw)}`);
      const ids = new Set(rows.map(r=>r.id || r.catalogue_model_id));
      const filtered = facItems.filter(it=>ids.has(it.id));
      drill.innerHTML = filtered.length
        ? renderGroups(editions, filtered, accent)
        : `<p class="hist-empty">No models in ${esc(label.split(' - ').pop())} match “${esc(raw)}”.</p>`;
    }catch(e){
      drill.innerHTML = `<p class="hist-empty hist-err">Search failed: ${esc(e.message)}</p>`;
    }
  };
  input.addEventListener('input', ()=>{ clearTimeout(timer); timer = setTimeout(run, 220); });
}

/* ======================================================================== */
/*  Model editor overlay — click a row to edit & save its info               */
/*  Reuses the catalogue-review modal styling (.cfe-backdrop / .am-*) and the */
/*  existing PATCH /api/model-catalogue/<id> + image endpoints.              */
/* ======================================================================== */
const MATERIALS = ['Plastic','Resin','Metal','Finecast','Other'];
let editorCid = null;

function openModelEditor(cid){
  if(editorCid) closeModelEditor();
  const item = (itemsCache || []).find(i=>i.id === cid);
  if(!item) return;
  editorCid = cid;

  const matOpts = MATERIALS.map(m=>`<option value="${m}"${(item.material||'Plastic')===m?' selected':''}>${m}</option>`).join('');
  // Faction is edited by canonical label, NOT faction_id: sub-factions (Blood Angels,
  // Dark Angels, …) share one BSData GUID, so the label is the grouping key here.
  const labels = new Map();
  (cardsCache || []).forEach(c=>labels.set(c.faction_label, c.display_name));
  if(item.faction_label && !labels.has(item.faction_label)){
    labels.set(item.faction_label, item.faction_label.split(' - ').pop());
  }
  const factionOpts = [...labels.entries()]
    .sort((a,b)=>a[1].localeCompare(b[1]))
    .map(([label, name])=>`<option value="${esc(label)}"${label===(item.faction_label||'')?' selected':''}>${esc(name)}</option>`)
    .join('');

  const backdrop = document.createElement('div');
  backdrop.className = 'cfe-backdrop';
  backdrop.id = 'histEditBackdrop';
  backdrop.innerHTML = `
    <div class="cfe-box" role="dialog" aria-modal="true" aria-labelledby="histEditTitle">
      <div class="am-head">
        <span class="am-title" id="histEditTitle">Edit Model</span>
        <button class="am-close he-close" title="Close" aria-label="Close">×</button>
      </div>
      <div class="catalogue-field-editor">
        <div class="cfe-grid">
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="he-name">Name</label>
            <input class="cfe-input" id="he-name" type="text" value="${esc(item.name)}" maxlength="300" autocomplete="off">
          </div>
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="he-faction">Faction</label>
            <select class="cfe-input" id="he-faction">${factionOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="he-date">Release Date</label>
            <input class="cfe-input" id="he-date" type="text" value="${esc(item.release_date||'')}"
                   placeholder="YYYY or YYYY-MM" maxlength="7" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label" for="he-material">Material</label>
            <select class="cfe-input" id="he-material">${matOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="he-status">Status</label>
            <select class="cfe-input" id="he-status">
              <option value="current_or_unknown"${item.status==='current_or_unknown'?' selected':''}>Current / Unknown</option>
              <option value="discontinued"${item.status==='discontinued'?' selected':''}>Discontinued</option>
            </select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="he-flags">Flags <span class="cfe-hint">(comma-separated)</span></label>
            <input class="cfe-input" id="he-flags" type="text" value="${esc((item.flags||[]).join(', '))}"
                   placeholder="e.g. exclusive, limited" autocomplete="off">
          </div>
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="he-note">Note</label>
            <input class="cfe-input" id="he-note" type="text" value="${esc(item.note||'')}" maxlength="500" autocomplete="off">
          </div>
        </div>
        ${renderEditorImage(item)}
        <p class="cfe-err" id="he-err" hidden></p>
        <div class="am-foot">
          <button class="btn-primary he-save">Save Changes</button>
          <button class="btn-ghost he-cancel">Cancel</button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(backdrop);
  backdrop.querySelector('#he-name').focus({ preventScroll: true });

  backdrop.querySelector('.he-save').addEventListener('click', saveModelEdits);
  backdrop.querySelector('.he-cancel').addEventListener('click', closeModelEditor);
  backdrop.querySelector('.he-close').addEventListener('click', closeModelEditor);
  backdrop.addEventListener('click', e=>{ if(e.target === backdrop) closeModelEditor(); });
  backdrop.addEventListener('keydown', e=>{ if(e.key === 'Escape') closeModelEditor(); });
  wireEditorImage(backdrop, cid);
}

function imageSearchUrl(item){
  return 'https://www.google.com/search?tbm=isch&q=' +
    encodeURIComponent(`${item.name} ${(item.faction_label||'').split(' - ').pop()} Warhammer 40k miniature`);
}

function renderEditorImage(item){
  const url = item.image && item.image.url ? item.image.url : '';
  const preview = url
    ? `<img src="${esc(url)}" alt="" class="he-img-preview">`
    : `<div class="he-img-empty">No image</div>`;
  return `
    <div class="he-img-section" id="heImgSection">
      <div class="am-label">Image</div>
      <a class="ref-search" href="${esc(imageSearchUrl(item))}" target="_blank" rel="noopener noreferrer">Find an image ↗</a>
      <div class="he-img-row">
        <div class="he-img-frame">${preview}</div>
        <div class="he-img-controls">
          <div class="ref-row">
            <input class="cfe-input" id="he-img-url" placeholder="Paste image address…" autocomplete="off">
            <button class="btn-primary he-img-url-save" type="button">Add</button>
          </div>
          <p class="ref-alt">or <label class="link-btn he-img-file-label">choose a file<input type="file" id="he-img-file" accept="image/*" hidden></label>
            ${url ? `<button class="btn-ghost he-img-clear" type="button">Remove image</button>` : ''}</p>
          <p class="ref-msg he-img-msg" id="he-img-msg"></p>
        </div>
      </div>
    </div>`;
}

function wireEditorImage(backdrop, cid){
  backdrop.querySelector('.he-img-url-save')?.addEventListener('click', ()=>saveEditorImageUrl(cid));
  backdrop.querySelector('#he-img-url')?.addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); saveEditorImageUrl(cid); } });
  backdrop.querySelector('#he-img-file')?.addEventListener('change', e=>{ if(e.target.files[0]) saveEditorImageFile(cid, e.target.files[0]); });
  backdrop.querySelector('.he-img-clear')?.addEventListener('click', ()=>clearEditorImage(cid));
}

function heImgMsg(msg, ok=true){
  const el = document.getElementById('he-img-msg');
  if(el){ el.textContent = msg; el.classList.toggle('is-err', !ok); }
}

// Reflect an image change into the editor preview, the in-memory item, and the row.
function applyImageChange(cid, url){
  const item = (itemsCache || []).find(i=>i.id===cid);
  if(item) item.image = url ? { url } : null;
  const section = document.getElementById('heImgSection');
  if(section && item) section.outerHTML = renderEditorImage(item);
  const bd = document.getElementById('histEditBackdrop');
  if(bd) wireEditorImage(bd, cid);
  // live-update the drill row thumbnail
  const row = document.querySelector(`.hist-model-row[data-cid="${CSS.escape(cid)}"] .hist-thumb`);
  if(row){
    row.innerHTML = url
      ? `<img src="${esc(url)}?v=${Date.now()}" alt="" loading="lazy">`
      : `<span class="hist-thumb-ph" style="display:flex">${esc((item?.name||'?')[0])}</span>`;
  }
}

async function saveEditorImageUrl(cid){
  const input = document.getElementById('he-img-url');
  const url = (input?.value || '').trim();
  if(!url){ heImgMsg('Paste an image address first.', false); return; }
  heImgMsg('Saving image…');
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url}),
    });
    if(!res.ok) throw new Error(res.error || 'Could not save image.');
    applyImageChange(cid, res.image_url);
    heImgMsg('Image saved.');
  }catch(e){ heImgMsg(e.message, false); }
}

async function saveEditorImageFile(cid, file){
  heImgMsg('Uploading image…');
  try{
    const fd = new FormData(); fd.append('file', file);
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, { method:'POST', body: fd });
    if(!res.ok) throw new Error(res.error || 'Could not upload image.');
    applyImageChange(cid, res.image_url);
    heImgMsg('Image saved.');
  }catch(e){ heImgMsg(e.message, false); }
}

async function clearEditorImage(cid){
  heImgMsg('Removing image…');
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, { method:'DELETE' });
    if(!res.ok) throw new Error(res.error || 'Could not remove image.');
    applyImageChange(cid, '');
    heImgMsg('Image removed.');
  }catch(e){ heImgMsg(e.message, false); }
}

function closeModelEditor(){
  document.getElementById('histEditBackdrop')?.remove();
  editorCid = null;
}

function heErr(msg){
  const el = document.getElementById('he-err');
  if(el){ el.textContent = msg; el.hidden = false; }
}

async function saveModelEdits(){
  if(!editorCid) return;
  const cid = editorCid;
  const saveBtn = document.querySelector('#histEditBackdrop .he-save');
  const errEl = document.getElementById('he-err');
  if(errEl) errEl.hidden = true;

  const name = document.getElementById('he-name').value.trim();
  if(!name){ heErr('Name cannot be empty.'); return; }
  const release_date = document.getElementById('he-date').value.trim();
  if(release_date && !/^\d{4}(-\d{2})?$/.test(release_date)){
    heErr('Release date must be YYYY or YYYY-MM (e.g. 2024-06).'); return;
  }

  if(saveBtn){ saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  const payload = {
    name,
    release_date,
    material: document.getElementById('he-material').value,
    status:   document.getElementById('he-status').value,
    note:     document.getElementById('he-note').value.trim(),
    flags:    document.getElementById('he-flags').value.split(',').map(f=>f.trim()).filter(Boolean),
    faction_label: document.getElementById('he-faction').value,
  };

  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload),
    });
    if(!res.ok) throw new Error(res.error || 'Save failed');
    closeModelEditor();
    // Caches are now stale (name/date/material/faction affect grouping & counts) — refetch.
    itemsCache = null; cardsCache = null;
    if(currentDrill) await showHistoryFaction(currentDrill.label);
  }catch(e){
    heErr(e.message);
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
  }
}
