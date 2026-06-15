import { esc, api, jsStr, readableInk, withTimeout } from './utils.js';
import { clearFactionCache } from './home.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';
import { openLightbox } from './lightbox.js';
import { renderDatasheetModels, renderWargear, renderUnitComposition, renderOptions, renderPoints, renderKeywords } from './datasheet.js';
import { setupArsenalHover } from './arsenal-hover.js';

const view       = document.getElementById('view');

let CURRENT         = null;  // {did, choices, compRange}
let LINKED_RELEASES = [];    // linked catalogue models for the current datasheet
let LRE_OPEN        = null;  // cid of the currently open release editor
const GROUP_PHOTOS  = new Map(); // gcid -> [{url, caption}, …] for the photo overlay

const STAGES = ['unbuilt','assembled','primed','base_coated','washed','highlighted','finished','display'];
const STAGE_LABELS = {
  unbuilt:'Unbuilt', assembled:'Assembled', primed:'Primed', base_coated:'Based',
  washed:'Washed', highlighted:'Highlighted', finished:'Done', display:'Display',
};

/* ---- unit detail -------------------------------------------------------- */

export async function showUnit(did){
  setActiveNav('armies');
  refreshLedger();
  view.innerHTML = `<div class="loading">Retrieving datasheet…</div>`;
  let d;
  try{ d = await withTimeout(api(`/api/units/${did}`)); }
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
  CURRENT        = {did, choices: d.wargear_choices||[],
                   compRange: d.composition_range||null};
  LINKED_RELEASES = d.linked_catalogue_models || [];
  LRE_OPEN        = null;
  setBreadcrumb([
    {label:'My Armies', href:'#/'},
    {label:d.faction_name, href:`#/faction/${d.faction_id}`},
    {label:d.name},
  ]);

  const linkedModels = d.linked_catalogue_models || [];
  view.innerHTML = `
    <div class="detail-wrap">
      <div class="detail-media">
        ${renderHeroGallery(did, d)}
        <div class="owned-panel">
          <div class="owned-readout">
            <b id="ownTotal">${d.owned}</b> <span>mini${d.owned===1?'':'s'} in collection</span>
          </div>
          ${d.bought>0?`<div class="owned-readout buy-readout">
            <b>${d.bought}</b> <span>bought${d.unlogged>0?` · ${d.unlogged} unlogged`:''}${d.multikit_alternatives?.length?' · shared kit':''}</span>
          </div>`:''}
          ${d.multikit_alternatives?.length?`<div class="mk-alt-note">
            Alternative build${d.multikit_alternatives.length>1?'s':''} from same kit:
            ${d.multikit_alternatives.map(a=>`<a onclick="location.hash='/unit/${esc(a.id)}'">${esc(a.name)}</a>`).join(', ')}
          </div>`:''}
        </div>
        ${linkedModels.length ? renderLinkedReleases(linkedModels) : ''}
      </div>
      <div class="detail-info">
        <h1 class="detail-name" style="color:${readableInk(d.accent)}">${esc(d.name)}</h1>
        <p class="detail-role">${esc(d.role)}${d.transport?` · Transport: ${esc(d.transport)}`:''}</p>
        <div class="unit-tabs" role="tablist">
          <button class="unit-tab is-active" id="unitInfoTab" data-unit-tab="info">Unit Information</button>
          <button class="unit-tab" id="collectionTab" data-unit-tab="collection">My Collection</button>
        </div>
        <div class="unit-tab-panel" id="unitInfoPanel">
          ${d.legend?`<p class="legend">${esc(d.legend)}</p>`:''}
          ${renderDatasheetModels(d.models)}
          ${renderWargear('Ranged Weapons', d.ranged)}
          ${renderWargear('Melee Weapons', d.melee)}
          ${renderUnitComposition(d.composition, d.loadout, d.led_by)}
          ${renderOptions(d.options)}
          ${renderPoints(d.costs)}
          ${renderKeywords(d)}
        </div>
        <div class="unit-tab-panel" id="collectionPanel" hidden>
          ${renderCollectionShell(d)}
        </div>
      </div>
    </div>`;

  wireUnitTabs();
  setupArsenalHover(document.getElementById('unitInfoPanel'));
  populateMiniList(d.collection_minis, d.squad_suggestions);
  setupGallery();
  setupLinkedReleases();
}

function wireUnitTabs(){
  document.querySelectorAll('[data-unit-tab]').forEach(btn=>{
    btn.addEventListener('click', ()=>switchUnitTab(btn.dataset.unitTab));
  });
}

function switchUnitTab(tab){
  const isCollection = tab === 'collection';
  document.getElementById('unitInfoPanel').hidden   = isCollection;
  document.getElementById('collectionPanel').hidden = !isCollection;
  document.getElementById('unitInfoTab').classList.toggle('is-active', !isCollection);
  document.getElementById('collectionTab').classList.toggle('is-active', isCollection);
}

/* ---- collection tab ----------------------------------------------------- */

function renderCollectionShell(d){
  return `<div class="collection-section">
    <div id="squadHint"></div>
    <div class="coll-header">
      <span class="coll-count" id="collCount">${d.owned} mini${d.owned===1?'':'s'} in collection</span>
      <a href="/collection" class="btn-secondary" style="text-decoration:none">Manage in Collection →</a>
    </div>
    <div id="miniList"></div>
  </div>`;
}

function populateMiniList(minis, suggestions){
  renderSquadHint(suggestions);
  const list = document.getElementById('miniList');
  if(!list) return;
  if(!minis||!minis.length){
    list.innerHTML = `<p class="empty-note mc-empty">No minis logged yet. Record a purchase to add minis to your pool, then advance their stage from the <a href="/collection" style="color:var(--gold)">Collection page</a>.</p>`;
    return;
  }
  const groups = groupMinis(minis);
  list.innerHTML = groups.map(g=>miniGroupCard(g)).join('');
  minis.forEach(m=>wireDrop(m.id));
}

async function refreshMiniList(){
  const d = await api(`/api/units/${CURRENT.did}`);
  const list = document.getElementById('miniList');
  const openGroups = list ? [...list.querySelectorAll('.mgc-details[open]')]
    .map(details => details.closest('.mini-group-card')?.id)
    .filter(Boolean) : [];
  populateMiniList(d.collection_minis, d.squad_suggestions);
  openGroups.forEach(id => {
    const details = document.querySelector(`#${CSS.escape(id)} .mgc-details`);
    if(details) details.open = true;
  });
  const el = document.getElementById('ownTotal');
  if(el) el.textContent = d.owned;
  const cc = document.getElementById('collCount');
  if(cc) cc.textContent = `${d.owned} mini${d.owned===1?'':'s'} in collection`;
}

/* ---- grouping helpers ---------------------------------------------------- */

function miniGroupKey(m){
  const wg = [...(m.wargear||[])].sort().join('\x00');
  return `${m.label||''}\x01${wg}\x01${m.catalogue_model_id||''}`;
}

function groupMinis(minis){
  const map = new Map();
  for(const m of minis){
    const k = miniGroupKey(m);
    if(!map.has(k)) map.set(k, []);
    map.get(k).push(m);
  }
  return [...map.values()];
}

function renderSquadHint(sugg){
  const el = document.getElementById('squadHint');
  if(!el||!sugg||sugg.total===0) return;
  const cr = CURRENT.compRange;
  if(!cr) return;
  let inner = '';
  if(sugg.squads.length===0&&sugg.total>0){
    inner = `<div class="sh-row sh-warn">⚠ ${sugg.total} mini${sugg.total===1?'':'s'} — not enough for a squad (minimum ${cr.min})</div>`;
  }else{
    const squadsText = sugg.squads.map(s=>`${s} mini${s===1?'':'s'}`).join(', ');
    const count = sugg.squads.length;
    inner = `<div class="sh-row sh-ok">✓ ${count} squad${count===1?'':'s'}: ${squadsText}</div>`;
    if(sugg.leftover>0)
      inner += `<div class="sh-row sh-info">${sugg.leftover} mini${sugg.leftover===1?'':'s'} left over (not enough for another squad)</div>`;
  }
  el.innerHTML = `<div class="squad-hint"><div class="sh-head">Squad Suggestions</div>${inner}</div>`;
}

function mgcPhotoTile(p, gcid, idx){
  return `<button class="mgc-thumb" onclick="openGroupOverlay('${gcid}',${idx})" title="${esc(p.caption||'')}">
    <img src="${esc(p.url)}" alt="${esc(p.caption||'')}">
  </button>`;
}

function stageSelect(mid, stage){
  const opts = STAGES.map(s=>`<option value="${s}" ${stage===s?'selected':''}>${STAGE_LABELS[s]||s}</option>`).join('');
  return `<select class="stage-sel" data-mid="${esc(mid)}" data-stage="${esc(stage)}"
    onchange="setMiniStage('${mid}',this.value)">${opts}</select>`;
}

function miniGroupCard(group){
  const rep    = group[0];
  const count  = group.length;
  const ids    = group.map(m=>m.id).join(',');
  const gcid   = `mg-${rep.id}`;

  const chips = rep.wargear&&rep.wargear.length
    ? rep.wargear.map(g=>`<span class="gear-chip">${esc(g)}</span>`).join('')
    : `<span class="gear-chip muted">No gear specified</span>`;

  const cm = rep.catalogue_model;
  const sculptBadge = cm
    ? `<div class="mc-sculpt">${esc(cm.name)}${cm.release_year?` · ${cm.release_year}`:''}${cm.material?` · ${esc(cm.material)}`:''}</div>`
    : '';

  const labelText = rep.label || 'Standard';

  // Pool all photos from all minis in this group
  const allPhotos = group.flatMap(m => m.photos||[]);
  GROUP_PHOTOS.set(gcid, allPhotos.map(p=>({url:p.url, caption:p.caption||''})));
  const hasPhotos = allPhotos.length > 0;

  if(count === 1){
    const repStage = rep.stage || 'unbuilt';
    const head = `<div class="mc-head">
        <span class="mgc-label" id="mgclabel-${gcid}">${esc(labelText)}</span>
        <button class="link-btn mgc-label-btn" onclick="editGroupLabel('${gcid}')" title="Rename">✎</button>
        ${stageSelect(rep.id, repStage)}
        <button class="mc-del" onclick="deleteMini('${rep.id}')" title="Remove mini">✕</button>
      </div>
      <div class="mc-label-ed" id="mgcled-${gcid}" hidden></div>
      ${sculptBadge}
      <div class="mc-gear-row">
        <div class="gear-chips" id="mgcgear-${gcid}">${chips}</div>
        <button class="link-btn" onclick="editGroupGear('${gcid}')">Edit gear</button>
      </div>
      <div class="mc-gear-ed" id="mgcged-${gcid}" hidden></div>
      <textarea class="mc-notes" placeholder="Notes — paint scheme, kitbash, magnets…"
                oninput="saveMiniNotesDebounced('${rep.id}',this.value)">${esc(rep.notes||'')}</textarea>`;

    if(hasPhotos){
      // Two-column: content left, photo rail right (rail doubles as mc-gallery for uploads)
      return `<div class="mini-group-card" id="${gcid}" data-mini-ids="${ids}">
        <div class="mgc-layout">
          <div class="mgc-content">${head}</div>
          <div class="mgc-photo-rail" id="mcgal-${rep.id}">
            ${allPhotos.map((p,i)=>mgcPhotoTile(p,gcid,i)).join('')}
            ${miniUploaderTile(rep.id)}
          </div>
        </div>
      </div>`;
    }
    return `<div class="mini-group-card" id="${gcid}" data-mini-ids="${ids}">
      ${head}
      <div class="mc-gallery" id="mcgal-${rep.id}">
        ${miniUploaderTile(rep.id)}
      </div>
    </div>`;
  }

  const finishedCount = group.filter(m=>(m.stage||'unbuilt')==='finished'||(m.stage||'unbuilt')==='display').length;
  const paintDots = group.map(m=>{
    const s = m.stage||'unbuilt';
    const isPainted = s==='finished'||s==='display';
    return `<button class="mgc-dot${isPainted?' is-painted':''}" data-mid="${m.id}"
             title="${esc(STAGE_LABELS[s]||s)} — click to edit"
             onclick="cycleMiniStage(this,'${m.id}')"></button>`;
  }).join('');

  const cardContent = `<div class="mc-head">
      <span class="mgc-badge">×${count}</span>
      <span class="mgc-label" id="mgclabel-${gcid}">${esc(labelText)}</span>
      <button class="link-btn mgc-label-btn" onclick="editGroupLabel('${gcid}')" title="Rename">✎</button>
      <div class="mgc-paint-row">
        ${paintDots}
        <span class="mgc-paint-tally">${finishedCount}/${count}</span>
      </div>
      <button class="mc-del" onclick="deleteOneFromGroup('${gcid}')" title="Remove one mini">−1</button>
    </div>
    <div class="mc-label-ed" id="mgcled-${gcid}" hidden></div>
    ${sculptBadge}
    <div class="mc-gear-row">
      <div class="gear-chips" id="mgcgear-${gcid}">${chips}</div>
      <button class="link-btn" onclick="editGroupGear('${gcid}')">Edit gear</button>
    </div>
    <div class="mc-gear-ed" id="mgcged-${gcid}" hidden></div>
    <details class="mgc-details">
      <summary class="mgc-summary">Manage ${count} minis individually</summary>
      <div class="mgc-minis">
        ${group.map((m,i)=>miniSubCard(m,i+1)).join('')}
      </div>
    </details>`;

  if(hasPhotos){
    return `<div class="mini-group-card" id="${gcid}" data-mini-ids="${ids}">
      <div class="mgc-layout">
        <div class="mgc-content">${cardContent}</div>
        <div class="mgc-photo-rail">
          ${allPhotos.map((p,i)=>mgcPhotoTile(p,gcid,i)).join('')}
        </div>
      </div>
    </div>`;
  }
  return `<div class="mini-group-card" id="${gcid}" data-mini-ids="${ids}">
    ${cardContent}
  </div>`;
}

function miniSubCard(m, num){
  const mid = m.id;
  const s = m.stage || 'unbuilt';
  return `<div class="mini-sub-card" id="msc-${mid}">
    <div class="msc-head">
      <span class="msc-num">#${num}</span>
      ${stageSelect(mid, s)}
      <button class="mc-del" onclick="deleteMini('${mid}')" title="Remove this mini">✕</button>
    </div>
    <textarea class="mc-notes" placeholder="Notes — paint scheme, kitbash, magnets…"
              oninput="saveMiniNotesDebounced('${mid}',this.value)">${esc(m.notes||'')}</textarea>
    <div class="mc-gallery" id="mcgal-${mid}">
      ${(m.photos||[]).map(p=>photoTile(p,mid)).join('')}
      ${miniUploaderTile(mid)}
    </div>
  </div>`;
}

/* ---- model label + painted ---------------------------------------------- */

export async function saveMiniLabel(mid, value){
  await api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({label: value.trim()})});
  await refreshMiniList();
}

export async function setMiniStage(mid, stage){
  const sel = document.querySelector(`.stage-sel[data-mid="${CSS.escape(mid)}"]`);
  const prev = sel?.dataset.stage || 'unbuilt';
  try{
    await api(`/api/minis/${mid}/stage`, {method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({stage})});
    await refreshMiniList();
    clearFactionCache();
    refreshLedger();
  }catch(e){
    document.querySelectorAll(`.stage-sel[data-mid="${CSS.escape(mid)}"]`).forEach(s=>{
      s.value = prev;
      s.dataset.stage = prev;
    });
    console.error('Stage update failed', e);
  }
}

export async function cycleMiniStage(btn, mid){
  // Cycle through stages on dot click (for grouped card dots)
  const PAINT_STAGES = ['unbuilt','base_coated','finished'];
  const title = btn.title || '';
  // Find current stage from dot's title prefix
  const curLabel = title.split(' —')[0].trim().toLowerCase();
  const curStageEntry = Object.entries(STAGE_LABELS).find(([,v])=>v.toLowerCase()===curLabel);
  const curStage = curStageEntry ? curStageEntry[0] : 'unbuilt';
  const curIdx = PAINT_STAGES.indexOf(PAINT_STAGES.find(s=>s===curStage) || PAINT_STAGES[0]);
  const nextStage = PAINT_STAGES[(curIdx + 1) % PAINT_STAGES.length];
  const isPainted = nextStage==='finished'||nextStage==='display';
  btn.classList.toggle('is-painted', isPainted);
  btn.title = `${STAGE_LABELS[nextStage]||nextStage} — click to edit`;
  const row   = btn.closest('.mgc-paint-row');
  const tally = row?.querySelector('.mgc-paint-tally');
  if(tally){
    const total  = row.querySelectorAll('.mgc-dot').length;
    const pcount = row.querySelectorAll('.mgc-dot.is-painted').length;
    tally.textContent = `${pcount}/${total}`;
  }
  await api(`/api/minis/${mid}/stage`, {method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({stage: nextStage})});
  await refreshMiniList();
  clearFactionCache();
  refreshLedger();
}

/* ---- group gear editor -------------------------------------------------- */

export function editGroupGear(gcid){
  const ed = document.getElementById('mgcged-'+gcid);
  if(!ed.hidden){ed.hidden=true;ed.innerHTML='';return;}
  const chipsEl     = document.getElementById('mgcgear-'+gcid);
  const currentGear = [...chipsEl.querySelectorAll('.gear-chip:not(.muted)')].map(c=>c.textContent);
  const choices     = CURRENT.choices;
  const extras      = currentGear.filter(g=>!choices.includes(g));
  const card        = document.getElementById(gcid);
  const ids         = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  const multi       = ids.length > 1;
  ed.innerHTML = `
    ${choices.length?`<div class="gear-grid">
      ${choices.map(c=>`<label class="gear-opt"><input type="checkbox" value="${esc(c)}" ${currentGear.includes(c)?'checked':''}> ${esc(c)}</label>`).join('')}
    </div>`:''}
    <input class="ff-input" id="mgex-${gcid}" placeholder="Other / custom gear, comma separated" value="${esc(extras.join(', '))}" style="margin-top:6px">
    <div class="ff-actions" style="margin-top:8px">
      <button class="btn-primary" onclick="saveGroupGear('${gcid}')">${multi?'Save for all':'Save'}</button>
      <button class="btn-ghost"   onclick="editGroupGear('${gcid}')">Cancel</button>
    </div>`;
  ed.hidden = false;
}

export async function saveGroupGear(gcid){
  const card    = document.getElementById(gcid);
  const ed      = document.getElementById('mgcged-'+gcid);
  const ids     = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  const checked = [...ed.querySelectorAll('input[type=checkbox]:checked')].map(i=>i.value);
  const custom  = (document.getElementById('mgex-'+gcid)?.value||'').split(',').map(s=>s.trim()).filter(Boolean);
  const gear    = [...checked,...custom];
  await Promise.all(ids.map(mid=>
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({wargear: gear})})
  ));
  await refreshMiniList();
}

/* ---- group label editor ------------------------------------------------- */

export function editGroupLabel(gcid){
  const ed = document.getElementById('mgcled-'+gcid);
  if(!ed.hidden){ ed.hidden=true; ed.innerHTML=''; return; }
  const labelEl = document.getElementById('mgclabel-'+gcid);
  const currentLabel = labelEl?.textContent === 'Standard' ? '' : (labelEl?.textContent || '');
  ed.innerHTML = `
    <div class="mc-label-ed-inner">
      <input class="ff-input" id="mgclinp-${gcid}" value="${esc(currentLabel)}"
             placeholder="Leave blank for Standard" autocomplete="off"
             onkeydown="if(event.key==='Enter')saveGroupLabel('${gcid}');else if(event.key==='Escape')editGroupLabel('${gcid}')">
      <button class="btn-primary" onclick="saveGroupLabel('${gcid}')">Save</button>
      <button class="btn-ghost"   onclick="editGroupLabel('${gcid}')">Cancel</button>
    </div>`;
  ed.hidden = false;
  document.getElementById('mgclinp-'+gcid)?.focus();
}

export async function saveGroupLabel(gcid){
  const card  = document.getElementById(gcid);
  const ids   = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  const label = (document.getElementById('mgclinp-'+gcid)?.value||'').trim();
  await Promise.all(ids.map(mid=>
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({label})})
  ));
  await refreshMiniList();
}

/* ---- model notes autosave ----------------------------------------------- */

const noteTimers = {};
export function saveMiniNotesDebounced(mid, value){
  clearTimeout(noteTimers[mid]);
  noteTimers[mid] = setTimeout(()=>{
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({notes: value})});
  }, 600);
}

/* ---- duplicate model ---------------------------------------------------- */

export function startDuplicate(mid, originalLabel){
  const form = document.getElementById('mcdup-'+mid);
  if(!form) return;
  if(!form.hidden){ form.hidden=true; form.innerHTML=''; return; }
  const newLabel = originalLabel ? originalLabel+' — Copy' : 'Copy';
  form.innerHTML = `
    <div class="maf-inner" style="margin-top:10px">
      <div class="maf-title">Duplicate — change the label to distinguish it</div>
      <label class="ff-label">New mini label</label>
      <input class="ff-input" id="dupLabel-${mid}" value="${esc(newLabel)}" autocomplete="off">
      <div class="dup-error" id="dupErr-${mid}" hidden></div>
      <div class="ff-actions">
        <button class="btn-primary" onclick="submitDuplicate('${mid}',${jsStr(originalLabel)})">Duplicate</button>
        <button class="btn-ghost"   onclick="cancelDuplicate('${mid}')">Cancel</button>
      </div>
    </div>`;
  form.hidden = false;
  const inp = document.getElementById('dupLabel-'+mid);
  inp.focus(); inp.select();
}

export function cancelDuplicate(mid){
  const form = document.getElementById('mcdup-'+mid);
  if(form){ form.hidden=true; form.innerHTML=''; }
}

export async function submitDuplicate(mid, originalLabel){
  const inp = document.getElementById('dupLabel-'+mid);
  const err = document.getElementById('dupErr-'+mid);
  if(!inp) return;
  const label = inp.value.trim();
  if(!label){
    err.textContent='Label cannot be empty.'; err.hidden=false; inp.focus(); return;
  }
  if(label === originalLabel){
    err.textContent='Label must differ from the original — update it before duplicating.';
    err.hidden=false; inp.focus(); return;
  }
  err.hidden=true;
  const res = await api(`/api/minis/${mid}/duplicate`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({label})
  });
  if(!res.ok){
    err.textContent = res.error||'Duplicate failed.'; err.hidden=false; return;
  }
  cancelDuplicate(mid);
  await refreshMiniList();
  clearFactionCache();
  refreshLedger();
}

/* ---- delete model ------------------------------------------------------- */

export async function deleteMini(mid){
  if(!confirm('Remove this mini from your collection? This cannot be undone.')) return;
  await fetch(`/api/minis/${mid}`, {method:'DELETE'});
  await refreshMiniList();
  clearFactionCache();
  refreshLedger();
}

/* ---- group photo overlay ------------------------------------------------ */

export function openGroupOverlay(gcid, startIndex){
  const photos = GROUP_PHOTOS.get(gcid) || [];
  if(!photos.length) return;
  let ov = document.getElementById('mgcOverlay');
  if(!ov){
    ov = document.createElement('div');
    ov.id = 'mgcOverlay';
    ov.className = 'mgc-overlay';
    ov.setAttribute('hidden','');
    document.body.appendChild(ov);
    ov.addEventListener('click', e=>{ if(e.target===ov) closeGroupOverlay(); });
    document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeGroupOverlay(); });
  }
  ov.innerHTML = `
    <button class="mgc-overlay-close" onclick="closeGroupOverlay()" aria-label="Close">✕</button>
    <div class="mgc-overlay-track">
      ${photos.map((p,i)=>`
        <div class="mgc-overlay-item" id="mgc-ov-${i}">
          <img src="${esc(p.url)}" alt="${esc(p.caption)}">
          ${p.caption?`<p class="mgc-ov-cap">${esc(p.caption)}</p>`:''}
        </div>`).join('')}
    </div>`;
  ov.removeAttribute('hidden');
  if(startIndex > 0){
    requestAnimationFrame(()=>{
      document.getElementById(`mgc-ov-${startIndex}`)?.scrollIntoView({block:'start'});
    });
  } else {
    ov.scrollTop = 0;
  }
}

export function closeGroupOverlay(){
  document.getElementById('mgcOverlay')?.setAttribute('hidden','');
}

export async function deleteOneFromGroup(gcid){
  const card = document.getElementById(gcid);
  if(!card) return;
  const ids   = (card.dataset.miniIds||'').split(',').filter(Boolean);
  const count = ids.length;
  if(!count) return;
  if(!confirm(`Remove 1 mini from this group (${count} total)? This cannot be undone.`)) return;
  await fetch(`/api/minis/${ids[ids.length-1]}`, {method:'DELETE'});
  await refreshMiniList();
  clearFactionCache();
  refreshLedger();
}

/* ---- photos ------------------------------------------------------------- */

function photoTile(p, mid){
  return `<div class="shot" data-id="${p.id}">
    <img src="${p.url}" alt="${esc(p.caption)}" onclick="openLightbox(${jsStr(p.url)},${jsStr(p.caption)})">
    <button class="del" onclick="deletePhoto('${p.id}')">&times;</button>
  </div>`;
}

function miniUploaderTile(mid){
  return `<label class="uploader" data-mid="${mid}">
    + Add Photos
    <input type="file" accept="image/*" multiple hidden onchange="uploadToMini('${mid}',this.files)">
  </label>`;
}

function wireDrop(mid){
  const up = document.querySelector(`#mcgal-${mid} .uploader`);
  if(!up) return;
  ['dragover','dragenter'].forEach(ev=>up.addEventListener(ev, e=>{e.preventDefault();up.classList.add('drag');}));
  ['dragleave','drop'].forEach(ev=>up.addEventListener(ev, e=>{e.preventDefault();up.classList.remove('drag');}));
  up.addEventListener('drop', e=>uploadToMini(mid, e.dataTransfer.files));
}

export async function uploadToMini(mid, files){
  if(!files||!files.length) return;
  const up = document.querySelector(`#mcgal-${mid} .uploader`);
  if(up){ up.classList.add('busy'); up.childNodes[0].textContent = 'Uploading…'; }
  const fd = new FormData();
  [...files].forEach(f=>fd.append('photos', f));
  await api(`/api/minis/${mid}/photos`, {method:'POST', body:fd});
  await refreshMiniList();
  refreshLedger();
}

export async function deletePhoto(pid){
  if(!confirm('Remove this photo?')) return;
  await fetch(`/api/photos/${pid}`, {method:'DELETE'});
  await refreshMiniList();
  refreshLedger();
}

/* ---- hero gallery ------------------------------------------------------- */

function renderHeroGallery(did, d){
  const models = d.linked_catalogue_models || [];
  const slides = [];

  for(const m of models){
    if(m.image_url){
      const meta = [m.release_year, m.material].filter(Boolean).join(' · ');
      slides.push({src: m.image_url, caption: meta ? `${esc(m.name)} · ${meta}` : esc(m.name), accent: d.accent});
    }
  }
  if(!slides.length){
    return `
      <div class="hero-wrap">
        <img class="hero-img" id="heroImg" src="/api/units/${did}/image" alt="${esc(d.name)}" style="border-color:${d.accent}">
      </div>`;
  }
  const multi = slides.length > 1;
  return `
    <div class="hero-gallery" id="heroGallery" data-slide="0">
      <div class="hero-slides" id="heroSlides">
        ${slides.map((s,i)=>`
          <div class="hero-slide${i===0?' is-active':''}">
            <img class="hero-img" src="${s.src}" alt="${s.caption}" style="border-color:${s.accent}">
            ${s.caption ? `<p class="hero-slide-caption">${s.caption}</p>` : ''}
          </div>`).join('')}
      </div>
      ${multi ? `
        <button class="hero-nav hero-prev" id="heroPrev" aria-label="Previous image">&#8249;</button>
        <button class="hero-nav hero-next" id="heroNext" aria-label="Next image">&#8250;</button>
        <div class="hero-dots" id="heroDots">
          ${slides.map((_,i)=>`<button class="hero-dot${i===0?' is-active':''}" data-slide="${i}" aria-label="Image ${i+1}"></button>`).join('')}
        </div>` : ''}
    </div>`;
}

function setupGallery(){
  const gallery = document.getElementById('heroGallery');
  if(!gallery) return;
  const prev = document.getElementById('heroPrev');
  const next = document.getElementById('heroNext');
  const dots = document.querySelectorAll('.hero-dot');
  if(!prev) return;

  function goTo(n){
    const slides = gallery.querySelectorAll('.hero-slide');
    const total = slides.length;
    const idx = ((n % total) + total) % total;
    slides.forEach((s,i) => s.classList.toggle('is-active', i===idx));
    dots.forEach((d,i) => d.classList.toggle('is-active', i===idx));
    gallery.dataset.slide = idx;
  }

  prev.addEventListener('click', () => goTo(+gallery.dataset.slide - 1));
  next.addEventListener('click', () => goTo(+gallery.dataset.slide + 1));
  dots.forEach(d => d.addEventListener('click', () => goTo(+d.dataset.slide)));
}

function renderLinkedReleases(models){
  const rows = models.map(m => {
    const meta = [m.release_year, m.material].filter(Boolean).join(' · ');
    return `
      <div class="linked-release-item" data-cid="${esc(m.id)}">
        <div class="linked-release-row">
          <div class="linked-release-thumb-wrap">
            ${m.image_url
              ? `<img class="linked-release-thumb" id="lre-thumb-${esc(m.id)}" src="${esc(m.image_url)}" alt="${esc(m.name)}" loading="lazy">`
              : `<div class="linked-release-thumb linked-release-no-img" id="lre-thumb-${esc(m.id)}"></div>`}
          </div>
          <div class="linked-release-info">
            <div class="linked-release-name">${esc(m.name)}</div>
            ${meta ? `<div class="linked-release-meta">${esc(meta)}</div>` : ''}
          </div>
          <button class="btn-secondary btn-sm lre-edit-btn" data-cid="${esc(m.id)}">Edit</button>
        </div>
        <div class="lre-panel" id="lre-panel-${esc(m.id)}" hidden></div>
      </div>`;
  }).join('');
  return `
    <div class="linked-releases" id="linkedReleases">
      <div class="linked-releases-head">Catalogue Releases</div>
      ${rows}
    </div>`;
}

function lreGoogleUrl(m){
  return 'https://www.google.com/search?tbm=isch&q=' +
    encodeURIComponent(`${m.name} ${m.faction_label} Warhammer 40k miniature`);
}

function renderLreImageSection(m){
  if(m.image_url){
    return `
      <div class="lre-img-preview" id="lre-img-section-${esc(m.id)}">
        <img src="${esc(m.image_url)}?v=${Date.now()}" alt="${esc(m.name)}">
        <button class="link-btn ref-clear lre-img-clear" data-cid="${esc(m.id)}">Remove image</button>
      </div>`;
  }
  return `
    <div class="lre-img-section" id="lre-img-section-${esc(m.id)}">
      <a class="ref-search" href="${lreGoogleUrl(m)}" target="_blank" rel="noopener noreferrer">Find an image ↗</a>
      <div class="ref-row">
        <input class="lre-img-url" placeholder="Paste image address here…" autocomplete="off">
        <button class="btn-primary lre-img-save" data-cid="${esc(m.id)}">Save</button>
      </div>
      <p class="ref-alt">or <label class="link-btn ref-file">choose a file<input type="file" accept="image/*" hidden class="lre-img-file" data-cid="${esc(m.id)}"></label></p>
      <p class="ref-msg lre-img-msg" id="lre-img-msg-${esc(m.id)}"></p>
    </div>`;
}

function renderLrePanel(m){
  const matOpts = ['Plastic','Resin','Metal','Finecast','Other'].map(mat =>
    `<option${m.material===mat?' selected':''}>${esc(mat)}</option>`).join('');
  return `
    <div class="lre-panel-inner">
      <div class="lre-panel-section">
        <div class="lre-section-head">Image</div>
        ${renderLreImageSection(m)}
      </div>
      <div class="lre-panel-section">
        <div class="lre-section-head">Details</div>
        <div class="cfe-grid">
          <div class="cfe-field cfe-field--full">
            <label class="am-label">Name</label>
            <input class="cfe-input lre-field-name" value="${esc(m.name)}" maxlength="300" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label">Release Date</label>
            <input class="cfe-input lre-field-date" value="${esc(m.release_date||'')}" placeholder="YYYY or YYYY-MM" maxlength="7" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label">Material</label>
            <select class="cfe-input lre-field-material">${matOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label">Status</label>
            <select class="cfe-input lre-field-status">
              <option value="current_or_unknown"${m.status==='current_or_unknown'?' selected':''}>Current / Unknown</option>
              <option value="discontinued"${m.status==='discontinued'?' selected':''}>Discontinued</option>
            </select>
          </div>
          <div class="cfe-field cfe-field--full">
            <label class="am-label">Note</label>
            <input class="cfe-input lre-field-note" value="${esc(m.note||'')}" maxlength="500" autocomplete="off">
          </div>
        </div>
        <p class="ref-msg lre-save-msg" id="lre-save-msg-${esc(m.id)}"></p>
        <div class="lre-actions">
          <button class="btn-primary lre-save-btn" data-cid="${esc(m.id)}">Save</button>
          <button class="btn-ghost lre-close-btn" data-cid="${esc(m.id)}">Close</button>
          <button class="btn-danger btn-sm catalogue-delete-btn lre-delete-btn" data-cid="${esc(m.id)}">Delete</button>
        </div>
      </div>
    </div>`;
}

function setupLinkedReleases(){
  const container = document.getElementById('linkedReleases');
  if(!container) return;

  container.addEventListener('click', async e => {
    const editBtn  = e.target.closest('.lre-edit-btn');
    const closeBtn = e.target.closest('.lre-close-btn');
    const saveBtn  = e.target.closest('.lre-save-btn');
    const delBtn   = e.target.closest('.lre-delete-btn');
    const clrBtn   = e.target.closest('.lre-img-clear');
    const imgSave  = e.target.closest('.lre-img-save');

    if(editBtn)  { lreToggle(editBtn.dataset.cid); return; }
    if(closeBtn) { lreClose(closeBtn.dataset.cid); return; }
    if(saveBtn)  { lreSaveFields(saveBtn.dataset.cid); return; }
    if(delBtn)   { lreDelete(delBtn.dataset.cid); return; }
    if(clrBtn)   { lreClearImage(clrBtn.dataset.cid); return; }
    if(imgSave)  { lreSaveImageFromUrl(imgSave.dataset.cid); return; }
  });

  container.addEventListener('change', e => {
    const fileIn = e.target.closest('.lre-img-file');
    if(fileIn && fileIn.files[0]) lreSaveImageFromFile(fileIn.dataset.cid, fileIn.files[0]);
  });

  container.addEventListener('keydown', e => {
    if(e.key !== 'Enter') return;
    const urlIn = e.target.closest('.lre-img-url');
    if(urlIn){
      const item = urlIn.closest('.linked-release-item');
      if(item) lreSaveImageFromUrl(item.dataset.cid);
    }
  });
}

function lreToggle(cid){
  if(LRE_OPEN === cid){ lreClose(cid); return; }
  if(LRE_OPEN) lreClose(LRE_OPEN);
  const m = LINKED_RELEASES.find(r => r.id === cid);
  if(!m) return;
  const panel = document.getElementById(`lre-panel-${cid}`);
  const item  = panel?.closest('.linked-release-item');
  if(!panel) return;
  panel.innerHTML = renderLrePanel(m);
  panel.hidden = false;
  item?.classList.add('is-editing');
  LRE_OPEN = cid;
}

function lreClose(cid){
  const panel = document.getElementById(`lre-panel-${cid}`);
  const item  = panel?.closest('.linked-release-item');
  if(panel){ panel.hidden = true; panel.innerHTML = ''; }
  item?.classList.remove('is-editing');
  if(LRE_OPEN === cid) LRE_OPEN = null;
}

function lreImgMsg(cid, text, ok){
  const el = document.getElementById(`lre-img-msg-${cid}`);
  if(!el) return;
  el.textContent = text || '';
  el.className = 'ref-msg lre-img-msg' + (text ? (ok?' ok':' err') : '');
}

function lreSaveMsg(cid, text, ok){
  const el = document.getElementById(`lre-save-msg-${cid}`);
  if(!el) return;
  el.textContent = text || '';
  el.className = 'ref-msg lre-save-msg' + (text ? (ok?' ok':' err') : '');
}

async function lreSaveImageFromUrl(cid){
  const panel = document.getElementById(`lre-panel-${cid}`);
  const input = panel?.querySelector('.lre-img-url');
  const url = (input?.value||'').trim();
  if(!url){ lreImgMsg(cid, 'Paste an image address first.', false); return; }
  lreImgMsg(cid, 'Fetching image…', true);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`,
      {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
    if(res.ok) lreAfterImageSaved(cid, res.image_url);
    else lreImgMsg(cid, res.error||'Could not save that image.', false);
  }catch(e){ lreImgMsg(cid, 'Could not save that image.', false); }
}

async function lreSaveImageFromFile(cid, fileObj){
  lreImgMsg(cid, 'Saving…', true);
  const fd = new FormData();
  fd.append('file', fileObj);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`,
      {method:'POST', body:fd});
    if(res.ok) lreAfterImageSaved(cid, res.image_url);
    else lreImgMsg(cid, res.error||'Could not save.', false);
  }catch(e){ lreImgMsg(cid, 'Could not save.', false); }
}

function lreAfterImageSaved(cid, imageUrl){
  const m = LINKED_RELEASES.find(r => r.id === cid);
  if(m) m.image_url = imageUrl;
  // Refresh the image section inside the open panel
  if(LRE_OPEN === cid){
    const section = document.getElementById(`lre-img-section-${cid}`);
    if(section && m) section.outerHTML = renderLreImageSection(m);
  }
  // Refresh the thumbnail on the collapsed row
  lreRefreshThumb(cid, imageUrl);
  // Refresh the gallery if it's showing a slide from this model
  lreRefreshGallerySlide(cid, imageUrl);
}

async function lreClearImage(cid){
  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {method:'DELETE'});
    if(!r.ok){
      const json = await r.json().catch(()=>({}));
      lreImgMsg(cid, json.error||`Server error (${r.status}).`, false);
      return;
    }
    const m = LINKED_RELEASES.find(r => r.id === cid);
    if(m) m.image_url = null;
    if(LRE_OPEN === cid){
      const section = document.getElementById(`lre-img-section-${cid}`);
      if(section && m) section.outerHTML = renderLreImageSection(m);
    }
    lreRefreshThumb(cid, null);
    lreRefreshGallerySlide(cid, null);
  }catch(e){ lreImgMsg(cid, 'Could not remove image.', false); }
}

async function lreSaveFields(cid){
  const panel = document.getElementById(`lre-panel-${cid}`);
  if(!panel) return;
  const name = panel.querySelector('.lre-field-name')?.value.trim();
  if(!name){ lreSaveMsg(cid, 'Name cannot be empty.', false); return; }
  const release_date = panel.querySelector('.lre-field-date')?.value.trim();
  if(release_date && !/^\d{4}(-\d{2})?$/.test(release_date)){
    lreSaveMsg(cid, 'Date must be YYYY or YYYY-MM.', false); return;
  }
  const payload = {
    name,
    release_date,
    material: panel.querySelector('.lre-field-material')?.value,
    status:   panel.querySelector('.lre-field-status')?.value,
    note:     panel.querySelector('.lre-field-note')?.value.trim()||'',
  };
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}`,
      {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if(!res.ok) throw new Error(res.error||'Save failed');
    const m = LINKED_RELEASES.find(r => r.id === cid);
    if(m) Object.assign(m, payload, {release_year: release_date?parseInt(release_date,10):m.release_year});
    // Update the collapsed row's name/meta display
    const item = document.querySelector(`.linked-release-item[data-cid="${CSS.escape(cid)}"]`);
    if(item && m){
      const nameEl = item.querySelector('.linked-release-name');
      const metaEl = item.querySelector('.linked-release-meta');
      if(nameEl) nameEl.textContent = m.name;
      const meta = [m.release_year, m.material].filter(Boolean).join(' · ');
      if(metaEl) metaEl.textContent = meta;
    }
    lreSaveMsg(cid, '✓ Saved.', true);
  }catch(e){ lreSaveMsg(cid, e.message||'Could not save.', false); }
}

async function lreDelete(cid){
  const m = LINKED_RELEASES.find(r => r.id === cid);
  if(!confirm(`Delete "${m?.name||cid}"?\n\nThis cannot be undone.`)) return;
  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}`, {method:'DELETE'});
    const json = await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(json.error||`HTTP ${r.status}`);
    LINKED_RELEASES = LINKED_RELEASES.filter(r => r.id !== cid);
    const item = document.querySelector(`.linked-release-item[data-cid="${CSS.escape(cid)}"]`);
    item?.remove();
    if(!LINKED_RELEASES.length){
      document.getElementById('linkedReleases')?.remove();
    }
    LRE_OPEN = null;
  }catch(e){ alert(`Could not delete: ${e.message}`); }
}

function lreRefreshThumb(cid, imageUrl){
  const wrap = document.querySelector(`.linked-release-item[data-cid="${CSS.escape(cid)}"] .linked-release-thumb-wrap`);
  if(!wrap) return;
  if(imageUrl){
    wrap.innerHTML = `<img class="linked-release-thumb" id="lre-thumb-${esc(cid)}" src="${esc(imageUrl)}?v=${Date.now()}" alt="" loading="lazy">`;
  } else {
    wrap.innerHTML = `<div class="linked-release-thumb linked-release-no-img" id="lre-thumb-${esc(cid)}"></div>`;
  }
}

function lreRefreshGallerySlide(cid, imageUrl){
  if(CURRENT) showUnit(CURRENT.did);
}

/* ---- exports to window for inline onclick handlers ---------------------- */
Object.assign(window, {
  openLightbox,
  saveMiniLabel, setMiniStage, cycleMiniStage,
  editGroupLabel, saveGroupLabel,
  editGroupGear, saveGroupGear,
  openGroupOverlay, closeGroupOverlay,
  saveMiniNotesDebounced,
  startDuplicate, cancelDuplicate, submitDuplicate,
  deleteMini, deleteOneFromGroup,
  uploadToMini, deletePhoto,
});
