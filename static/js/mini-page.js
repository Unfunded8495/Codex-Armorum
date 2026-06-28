import { esc, api, jsStr, readableInk, withTimeout } from './utils.js';
import { clearFactionCache } from './home.js';
import { refreshLedger, setActiveNav, setBreadcrumb } from './header.js';
import { openLightbox } from './lightbox.js';

/* ---- constants ---- */
const STAGES = ['unbuilt','assembled','primed','base_coated','washed','highlighted','finished','display'];
const STAGE_LABELS = {
  unbuilt:'Unbuilt', assembled:'Assembled', primed:'Primed', base_coated:'Base Coated',
  washed:'Washed', highlighted:'Highlighted', finished:'Finished', display:'Display',
};

/* ---- paint-stage buckets (drive ledger counts, diamonds, summaries) ---- */
const BUCKET_LABEL = { raw:'To build', bench:'Undergoing rites', done:'Blessed' };
/* unbuilt → raw; finished/display → done; everything in between → bench */
function mpBucketOf(stage){
  const s = stage || 'unbuilt';
  return s === 'unbuilt' ? 'raw' : (s === 'finished' || s === 'display') ? 'done' : 'bench';
}
function mpBucketCounts(){
  const c = { raw:0, bench:0, done:0 };
  for(const m of mpMinis) c[mpBucketOf(m.stage)]++;
  return c;
}

/* ---- page state ---- */
let mpMinis        = [];
let mpUnit         = null;
let mpDatasheetId  = null;
let mpPendingLoadoutMiniId = null;
const MP_GROUP_PHOTOS = new Map();
const MP_NOTE_TIMERS  = {};
let mpOverlayPhotos = [];
let mpOverlayIndex  = 0;
let mpCarouselResizeHandler = null;

/* ---- catalogue card state ---- */
let mpCatalogueItems    = [];
let mpCatalogueFactions = [];
let mpCatEd  = { cid: null, selected: [], factionId: '' };
let mpCatFed = { cid: null, focusLinks: false };

/* ---- DOM ---- */
const view       = document.getElementById('view');

/* ====================================================================
   ENTRY POINT
   ==================================================================== */
export async function showMiniPage(did){
  setActiveNav('armies');
  refreshLedger();
  mpDatasheetId = did;
  mpMinis = [];
  mpUnit  = null;
  view.innerHTML = `<div class="loading">Mustering your minis…</div>`;

  // A datasheet-less catalogue model ("cat:<id>") has no datasheet, so skip the
  // unit fetch and render a reduced page (paint tracker + owned sculpt card only).
  const isCat = did.startsWith('cat:');
  try{
    if(isCat){
      mpMinis = await withTimeout(api(`/api/collection?datasheet_id=${encodeURIComponent(did)}`));
      mpUnit  = null;
    }else{
      [mpMinis, mpUnit] = await withTimeout(Promise.all([
        api(`/api/collection?datasheet_id=${encodeURIComponent(did)}`),
        api(`/api/units/${did}`),
      ]));
    }
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

  if(!mpMinis.length){
    view.innerHTML = `<div class="loading">No minis found for this unit.</div>`;
    return;
  }

  const rep = mpMinis[0];
  setBreadcrumb([
    {label:'My Armies', href:'#/'},
    {label:rep.faction_display_name || rep.faction_name, href:`#/faction/${rep.faction_id}`},
    {label:rep.datasheet_name},
  ]);

  // Fetch full catalogue card data for every sculpt the user actually owns under this
  // datasheet. The collection API remaps each mini's catalogue_model_id to the sculpt
  // matching the datasheet it's shown under, so the distinct owned models ARE the releases
  // to show — including ones the datasheet hasn't been formally linked to yet (e.g. owning
  // both the standard box and the Easy-To-Build set). The most-owned sculpt leads. Fall
  // back to the datasheet's linked releases only when no mini carries a catalogue model.
  mpCatalogueItems = [];
  mpCatalogueFactions = [];
  const ownedCounts = new Map();
  for(const m of mpMinis){
    if(m.catalogue_model_id) ownedCounts.set(m.catalogue_model_id, (ownedCounts.get(m.catalogue_model_id) || 0) + 1);
  }
  const ownedModelIds = [...ownedCounts.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]);
  const allLinkedIds  = (mpUnit?.linked_catalogue_models || []).map(m => m.id).filter(Boolean);
  const linkedIds = ownedModelIds.length ? ownedModelIds : allLinkedIds;
  if(linkedIds.length){
    try{
      const results = await Promise.all(
        linkedIds.map(id => api(`/api/model-catalogue/${encodeURIComponent(id)}`))
      );
      mpCatalogueItems = results.map(r => r.item).filter(Boolean);
      mpCatalogueFactions = results.find(r => r.factions?.length)?.factions || [];
    }catch(e){ /* fall back to hero image */ }
  }

  mpRenderPage();
}

/* ====================================================================
   PAGE RENDERING
   ==================================================================== */
function mpRenderPage(){
  const rep    = mpMinis[0];
  const isCat  = (mpDatasheetId || '').startsWith('cat:');
  const groups = mpGroupMinis(mpMinis);

  const accent  = mpUnit?.accent || 'var(--gold)';
  const name    = mpUnit?.name   || rep.datasheet_name;
  const role    = mpUnit?.role   || '';
  const legend  = mpUnit?.legend || '';
  const faction = mpUnit?.faction_display_name || mpUnit?.faction_name
                || rep.faction_display_name || rep.faction_name;

  view.innerHTML = `
    <div class="detail-wrap mp-page">
      <div class="detail-media">
        ${mpLeftMediaHtml()}${mpReliquaryLedgerHtml()}
      </div>
      <div class="detail-info">
        <h1 class="detail-name" style="color:${readableInk(accent)}">${esc(name)}</h1>
        <p class="detail-role"><span class="mp-tick" aria-hidden="true"></span>${esc(faction)}${role?' · '+esc(role):''}</p>
        ${legend?`<p class="legend">${esc(legend)}</p>`:''}
        <div class="mp-mini-list" id="mpMiniList">
          ${groups.map(g=>mpRenderGroup(g)).join('')}
        </div>
        ${isCat ? '' : `<div class="mp-ds-link-row">
          <a class="mp-ds-link" href="/#/unit/${esc(rep.datasheet_id)}">View Full Datasheet <span class="mp-ds-arrow" aria-hidden="true">→</span></a>
        </div>`}
        ${isCat ? '' : mpRenderWipSection()}
      </div>
    </div>`;

  mpWireLeftMedia();
  mpWireDropZones();
  if(!isCat) mpWireWipDropZone();
}

/* The bolted data-plate strip across the top of a sculpt card: unit role on the left,
   the owned-model count on the right. Both are unit-wide, so every sculpt slide shows
   the same plate (it reads as part of the armour frame, not the individual release). */
function mpDataPlateHtml(){
  const role  = mpUnit?.role || '';
  const total = mpMinis.length;
  return `<div class="mp-dataplate">
    <span class="mp-dataplate-role">${esc(role || 'Model')}</span>
    <span class="mp-dataplate-count"><b>${total}</b> Model${total===1?'':'s'}</span>
  </div>`;
}

/* Faction emblem watermark, bottom-left of a sculpt stage. Reuses the server's
   accent-tinted single-colour icon endpoint; omitted when the faction is unknown. */
function mpEmblemHtml(factionId){
  const fid = factionId || mpUnit?.faction_id || mpMinis[0]?.faction_id || '';
  if(!fid) return '';
  return `<div class="mp-emblem" aria-hidden="true"><img src="/api/factions/${encodeURIComponent(fid)}/icon" alt="" loading="lazy"></div>`;
}

/* Reliquary Ledger: armour-plate panel summarising the whole pool — total minis, the
   painted %, and the three paint-stage buckets. Counts are recomputed live on every
   stage change by mpRefreshProgress() (matching element ids). */
function mpReliquaryLedgerHtml(){
  const total = mpMinis.length;
  const c     = mpBucketCounts();
  const pct   = total > 0 ? Math.round(c.done / total * 100) : 0;
  return `<div class="mp-ledger mp-rivets">
    <div class="mp-ledger-head"><span class="mp-diamond-sm"></span><span>Reliquary Ledger</span></div>
    <div class="mp-ledger-total"><b id="mpTotal">${total}</b><span>mini${total===1?'':'s'} in collection</span></div>
    <div class="mp-ledger-pctrow"><span>Company Painted</span><span id="mpPct">${pct}%</span></div>
    <div class="mp-bar-track"><div class="mp-bar-fill" id="mpBarFill" style="width:${pct}%"></div></div>
    <div class="mp-ledger-rows">
      <div class="mp-ledger-row"><span class="mp-diamond" data-b="done"></span><span class="mp-ledger-label">Blessed by the Omnissiah</span><span class="mp-ledger-count" id="mpDone">${c.done}</span></div>
      <div class="mp-ledger-row"><span class="mp-diamond" data-b="bench"></span><span class="mp-ledger-label">Undergoing Rites</span><span class="mp-ledger-count" id="mpBench">${c.bench}</span></div>
      <div class="mp-ledger-row"><span class="mp-diamond" data-b="raw"></span><span class="mp-ledger-label">To build</span><span class="mp-ledger-count" id="mpRaw">${c.raw}</span></div>
    </div>
  </div>`;
}

/* Build the left-column media: a swipeable carousel of the owned sculpt cards when the
   user owns more than one, a single card when they own one, or the hero image fallback. */
function mpLeftMediaHtml(){
  if(mpCatalogueItems.length){
    const cards = mpCatalogueItems.map(item => mpCatRenderCard(item)).join('');
    if(mpCatalogueItems.length === 1) return `<div id="mpCatalogueCol">${cards}</div>`;
    const dots = mpCatalogueItems.map((it, i) =>
      `<button class="mp-cat-dot${i===0?' is-active':''}" data-idx="${i}" type="button" aria-label="Show ${esc(it.name)}"></button>`
    ).join('');
    return `<div class="mp-cat-carousel" id="mpCatCarousel">
      <div class="mp-cat-track" id="mpCatalogueCol">${cards}</div>
      <button class="mp-cat-nav mp-cat-prev" type="button" aria-label="Previous model">‹</button>
      <button class="mp-cat-nav mp-cat-next" type="button" aria-label="Next model">›</button>
      <div class="mp-cat-dots">${dots}</div>
    </div>`;
  }
  const rep    = mpMinis[0];
  const name   = mpUnit?.name   || rep.datasheet_name;
  const heroImg = (mpUnit?.linked_catalogue_models || []).find(m=>m.image_url)?.image_url
    || `/api/units/${esc(rep.datasheet_id)}/image`;
  // Reuse the sculpt-card frame so the no-catalogue fallback matches the design.
  return `<div class="catalogue-card mp-sculpt mp-rivets has-image" id="mpCatalogueCol">
    <div class="catalogue-image mp-stage">
      ${mpDataPlateHtml()}
      <img src="${esc(heroImg)}" alt="${esc(name)}">
      ${mpEmblemHtml()}
    </div>
    <div class="catalogue-card-head"><div><h4>${esc(name)}</h4></div></div>
  </div>`;
}

function mpWireLeftMedia(){
  if(!mpCatalogueItems.length) return;
  mpCatWireCards();
  mpCatWireCarousel();
}

/* Re-render just the left-column media (used after a card is added/removed/edited). */
function mpRerenderLeftMedia(){
  const media = document.querySelector('.detail-media');
  if(!media) return;
  const ledger = media.querySelector('.mp-ledger');
  const next = document.createElement('div');
  next.innerHTML = mpLeftMediaHtml();
  [...media.children].forEach(ch => { if(ch !== ledger) ch.remove(); });
  if(next.firstElementChild) media.insertBefore(next.firstElementChild, ledger);
  mpWireLeftMedia();
}

function mpCatWireCarousel(){
  const car = document.getElementById('mpCatCarousel');
  if(!car) return;
  const track = car.querySelector('#mpCatalogueCol');
  const cards = [...track.querySelectorAll('.catalogue-card')];
  const dots  = [...car.querySelectorAll('.mp-cat-dot')];
  const prev  = car.querySelector('.mp-cat-prev');
  const next  = car.querySelector('.mp-cat-next');
  if(cards.length < 2) return;

  const indexFor = () => Math.min(cards.length - 1, Math.max(0, Math.round(track.scrollLeft / track.clientWidth)));
  const goTo = i => cards[i]?.scrollIntoView({behavior:'smooth', inline:'start', block:'nearest'});

  prev?.addEventListener('click', () => goTo(indexFor() - 1));
  next?.addEventListener('click', () => goTo(indexFor() + 1));
  dots.forEach(d => d.addEventListener('click', () => goTo(+d.dataset.idx)));

  // Pin the overlay controls to the artwork: arrows at its vertical centre, dots near
  // its lower edge. The artwork is the tallest element, so the card itself runs longer.
  const dotsEl = car.querySelector('.mp-cat-dots');
  const placeArrows = () => {
    const img = track.querySelector('.catalogue-image');
    if(!img) return;
    const imgTop = img.getBoundingClientRect().top - car.getBoundingClientRect().top;
    [prev, next].forEach(b => { if(b) b.style.top = `${imgTop + img.offsetHeight / 2}px`; });
    if(dotsEl) dotsEl.style.top = `${imgTop + img.offsetHeight - 22}px`;
  };
  const sync = () => {
    const i = indexFor();
    dots.forEach((d, j) => d.classList.toggle('is-active', j === i));
    if(prev) prev.disabled = i === 0;
    if(next) next.disabled = i === cards.length - 1;
  };

  let raf = 0;
  track.addEventListener('scroll', () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(sync); });
  track.querySelectorAll('.catalogue-image img').forEach(im => {
    if(!im.complete) im.addEventListener('load', placeArrows, {once:true});
  });
  if(mpCarouselResizeHandler) window.removeEventListener('resize', mpCarouselResizeHandler);
  mpCarouselResizeHandler = () => { placeArrows(); sync(); };
  window.addEventListener('resize', mpCarouselResizeHandler);
  placeArrows();
  sync();
}

function mpRefreshProgress(){
  const total = mpMinis.length;
  const c     = mpBucketCounts();
  const pct   = total > 0 ? Math.round(c.done / total * 100) : 0;
  const set = (id, val) => { const el = document.getElementById(id); if(el) el.textContent = val; };
  set('mpTotal', total);
  set('mpDone',  c.done);
  set('mpBench', c.bench);
  set('mpRaw',   c.raw);
  set('mpPct',   pct + '%');
  const bar = document.getElementById('mpBarFill');
  if(bar) bar.style.width = pct + '%';
}

function mpGroupMinis(minis){
  const map = new Map();
  for(const m of minis){
    const key = `${m.label||''}\x01${[...(m.wargear||[])].sort().join('\x00')}\x01${m.catalogue_model_id||''}`;
    if(!map.has(key)) map.set(key, []);
    map.get(key).push(m);
  }
  // Order: the all-unbuilt card(s) first, then the rest alphanumerically by label.
  const isUnbuiltGroup = g => g.every(m => (m.stage || 'unbuilt') === 'unbuilt');
  return [...map.values()].sort((a, b) => {
    const au = isUnbuiltGroup(a), bu = isUnbuiltGroup(b);
    if(au !== bu) return au ? -1 : 1;
    const al = a[0].label || 'Standard';
    const bl = b[0].label || 'Standard';
    return al.localeCompare(bl, undefined, {numeric:true, sensitivity:'base'});
  });
}

function mpCatalogueUrl(cid){
  return `/catalogue-review?model=${encodeURIComponent(cid)}`;
}

function mpCatalogueModel(cid){
  return (mpUnit?.linked_catalogue_models || []).find(m=>m.id===cid) || null;
}

function mpCatalogueLinkForMini(mini){
  const cid = mini.catalogue_model_id;
  if(!cid) return '';
  const model = mpCatalogueModel(cid);
  const meta = model
    ? [model.release_year, model.material].filter(Boolean).join(' · ')
    : '';
  return `<a class="mc-sculpt mp-catalogue-link" href="${esc(mpCatalogueUrl(cid))}">
    <span>${esc(model?.name || cid)}</span>
    ${meta ? `<small>${esc(meta)}</small>` : '<small>Model catalogue</small>'}
  </a>`;
}

function mpRefreshUnitMiniList(){
  const listEl = document.getElementById('mpMiniList');
  if(!listEl) return;
  const openGroups = [...listEl.querySelectorAll('.mgc-details[open]')]
    .map(details => details.closest('.mini-group-card')?.id)
    .filter(Boolean);
  const groups = mpGroupMinis(mpMinis);
  listEl.innerHTML = groups.map(g=>mpRenderGroup(g)).join('');
  openGroups.forEach(id => {
    const details = listEl.querySelector(`#${CSS.escape(id)} .mgc-details`);
    if(details) details.open = true;
  });
  mpWireDropZones();
  mpRefreshProgress();
  mpOpenPendingLoadoutEditor();
}

/* ====================================================================
   MINI GROUP CARD RENDERING
   ==================================================================== */
function mpStageSelect(mid, stage, multikitGroup){
  const isMk = !!(multikitGroup && stage === 'unbuilt');
  const opts  = STAGES.map(s=>`<option value="${s}" ${stage===s?'selected':''}>${STAGE_LABELS[s]||s}</option>`).join('');
  const mkClass = isMk ? ' is-multikit' : '';
  const mkTitle = isMk ? ' title="Multikit — choose unit when building"' : '';
  return `<select class="stage-sel${mkClass}" data-mid="${esc(mid)}" data-stage="${esc(stage)}"${mkTitle}
    onchange="mpSetMiniStage('${mid}',this.value);this.dataset.stage=this.value">${opts}</select>`;
}


/* A single photo tile in the left-hand media column. Clicking the image opens the
   group carousel overlay; the × deletes it from whichever mini actually owns it. */
function mpMediaTile(p, mid, gcid, idx){
  return `<div class="shot" data-id="${p.id}">
    <img src="${esc(p.url)}" alt="${esc(p.caption||'')}" onclick="mpOpenGroupOverlay('${gcid}',${idx})">
    <button class="del" onclick="mpDeletePhoto('${p.id}','${mid}')">&times;</button>
  </div>`;
}

/* The card's single photo surface, pinned to the left of the card. It pools every
   photo across the minis in the group so a shot is never shown twice: uploads attach
   to the lead mini, while each delete targets the photo's own mini. */
function mpMediaColumn(group, gcid){
  const rep = group[0];
  const allPhotos = group.flatMap(m => (m.photos||[]).map(p => ({...p, _mid:m.id})));
  MP_GROUP_PHOTOS.set(gcid, allPhotos.map(p => ({url:p.url, caption:p.caption||''})));
  return `<div class="mgc-media">
    <div class="mc-gallery mgc-media-gallery" id="mpcgal-${rep.id}">
      ${allPhotos.map((p,i)=>mpMediaTile(p, p._mid, gcid, i)).join('')}
      ${mpUploaderTile(rep.id)}
    </div>
  </div>`;
}

function mpRenderGearChips(gear, isUnbuilt=false){
  if(gear && gear.length){
    return gear.map(g=>`<span class="gear-chip">${esc(g)}</span>`).join('');
  }
  return isUnbuilt ? '' : `<span class="gear-chip muted">No loadout specified</span>`;
}

function mpUploaderTile(mid){
  return `<label class="uploader" data-mid="${mid}">
    + Add Photos
    <input type="file" accept="image/*" multiple hidden onchange="mpUploadToMini('${mid}',this.files)">
  </label>`;
}

function mpRenderGroup(group){
  const rep   = group[0];
  const count = group.length;
  const did   = rep.datasheet_id || '';
  const ids   = group.map(m=>m.id).join(',');
  const gcid  = `mpg-${rep.id}`;

  const isUnbuilt = count === 1
    ? (rep.stage || 'unbuilt') === 'unbuilt'
    : group.every(m=>(m.stage || 'unbuilt') === 'unbuilt');

  // The all-unbuilt "to build" card is tinted with the army colour, matching the
  // faction box on the left (e.g. red for Skitarii / Adeptus Mechanicus).
  // The all-unbuilt "to build" card stays a muted plate (bare plastic); built cards get
  // the faction-coloured diagonal fade driven by the --faction var. The army colour is
  // still exposed on unbuilt cards via --cardarmy/--cardaccent for the existing tint.
  const army  = mpUnit?.primary || mpMinis[0]?.primary || '';
  const glow  = mpUnit?.accent || army;
  const faction = army || '#22468c';
  const unbuiltCls = isUnbuilt ? ' mp-unbuilt-card' : ' mp-built-card';
  const cardStyle = isUnbuilt
    ? (army ? ` style="--cardarmy:${esc(army)};--cardaccent:${esc(glow)};--cardglow:${esc(glow)}"` : '')
    : ` style="--faction:${esc(faction)}"`;

  const chips = mpRenderGearChips(rep.wargear, isUnbuilt);

  const labelText = rep.label || 'Standard';

  const badge = count > 1 ? `<span class="mgc-badge"><span class="mgc-badge-x">×</span>${count}</span>` : '';
  const deleteButton = count > 1
    ? `<button class="mc-del" onclick="mpDeleteOneFromGroup('${gcid}')" title="Remove one mini">−1</button>`
    : `<button class="mc-del" onclick="mpDeleteMini('${rep.id}')" title="Remove mini">✕</button>`;

  const head = `<div class="mc-head">
      ${badge}
      <span class="mgc-label" id="mplabel-${gcid}">${esc(labelText)}</span>
      <button class="link-btn mgc-label-btn" onclick="mpEditGroupLabel('${gcid}')" title="Rename">✎ Rename</button>
      ${deleteButton}
    </div>
    <div class="mc-label-ed" id="mpled-${gcid}" hidden></div>`;

  // Loadout row is hidden entirely for all-unbuilt groups (nothing built to equip yet).
  const gearBlock = isUnbuilt ? '' : `<div class="mc-gear-row">
      <div class="gear-chips" id="mpgear-${gcid}">${chips}</div>
      <button class="link-btn" onclick="mpEditGroupGear('${gcid}')">Edit loadout</button>
    </div>
    <div class="mc-gear-ed" id="mpged-${gcid}" hidden></div>`;

  // Photos sit in one column pinned to the left of the card; the body (right) holds
  // the head, loadout and (solo) stage controls. Only built minis get a photo column,
  // so the unbuilt "to build" cards stay compact.
  const hasPhotos = group.some(m => (m.photos||[]).length);
  const media = (!isUnbuilt || hasPhotos) ? mpMediaColumn(group, gcid) : '';

  let bodyInner;
  if(count === 1){
    const s = rep.stage || 'unbuilt';
    const notes = s !== 'unbuilt'
      ? `<textarea class="mc-notes" placeholder="Notes — paint scheme, kitbash, magnets…"
          oninput="mpSaveMiniNotes('${rep.id}',this.value)">${esc(rep.notes||'')}</textarea>`
      : '';
    bodyInner = `${head}
      ${mpSoloStageHtml(rep.id, s, rep.multikit_group)}
      ${gearBlock}
      ${notes}`;
  }else{
    bodyInner = `${head}${gearBlock}`;
  }
  const body = `<div class="mgc-body">${bodyInner}</div>`;
  const toprow = `<div class="mgc-toprow">${media}${body}</div>`;

  // The squad manager lives full-width BELOW the photo+body row, so opening it never
  // changes the photo height.
  const details = count > 1
    ? `<details class="mgc-details">
        <summary class="mgc-summary">
          <span class="mgc-summary-label">Manage ${count} minis individually</span>
          <span class="mgc-summary-tally">${esc(mpGroupSummary(group))}</span>
        </summary>
        <div class="mgc-minis">
          ${group.map((m,i)=>mpRenderSubCard(m,i+1)).join('')}
        </div>
      </details>`
    : '';

  const soloCls = count === 1 ? ' is-solo' : '';
  return `<div class="mini-group-card mp-rivets${soloCls}${unbuiltCls}" id="${gcid}" data-mini-ids="${ids}" data-did="${esc(did)}"${cardStyle}>
    ${toprow}${details}
  </div>`;
}

/* Solo stage control: a bucket diamond beside the stage select. */
function mpSoloStageHtml(mid, stage, multikitGroup){
  const b = mpBucketOf(stage);
  return `<div class="mc-stage-row">
    <span class="mp-diamond" data-b="${b}"></span>
    ${mpStageSelect(mid, stage, multikitGroup)}
  </div>`;
}

/* The per-mini summary shown on the right of a squad's expander bar. */
function mpGroupSummary(group){
  const b = group.map(m => mpBucketOf(m.stage));
  const d = b.filter(x=>x==='done').length;
  const be = b.filter(x=>x==='bench').length;
  const r = b.filter(x=>x==='raw').length;
  const parts = [];
  if(d)  parts.push(d + ' blessed');
  if(be) parts.push(be + ' in rites');
  if(r)  parts.push(r + ' to build');
  return parts.join(' · ');
}

function mpRenderSubCard(m, num){
  const mid = m.id;
  const s   = m.stage || 'unbuilt';
  const b   = mpBucketOf(s);
  const chips = mpRenderGearChips(m.wargear, false);
  return `<div class="mini-sub-card" id="mpsc-${mid}">
    <div class="msc-head">
      <span class="msc-num">#${num}</span>
      <span class="mp-diamond" data-b="${b}"></span>
      ${mpStageSelect(mid, s, m.multikit_group)}
      <span class="msc-bucket">${BUCKET_LABEL[b]}</span>
      <button class="mc-del" onclick="mpDeleteMini('${mid}')" title="Remove this mini">✕</button>
    </div>
    ${s !== 'unbuilt' ? `<div class="mc-gear-row msc-gear-row">
      <div class="gear-chips" id="mpmgear-${mid}">${chips}</div>
      <button class="link-btn" onclick="mpEditMiniGear('${mid}')">Edit loadout</button>
    </div>
    <div class="mc-gear-ed" id="mpmed-${mid}" hidden></div>` : ''}
    ${s !== 'unbuilt' ? `<textarea class="mc-notes" placeholder="Notes — paint scheme, kitbash, magnets…"
              oninput="mpSaveMiniNotes('${mid}',this.value)">${esc(m.notes||'')}</textarea>` : ''}
  </div>`;
}

function mpWireDropZones(){
  document.querySelectorAll('#mpMiniList [data-mid]').forEach(up=>{
    if(!up.classList.contains('uploader')) return;
    const mid = up.dataset.mid;
    ['dragover','dragenter'].forEach(ev=>up.addEventListener(ev,e=>{e.preventDefault();up.classList.add('drag');}));
    ['dragleave','drop'].forEach(ev=>up.addEventListener(ev,e=>{e.preventDefault();up.classList.remove('drag');}));
    up.addEventListener('drop',e=>mpUploadToMini(mid, e.dataTransfer.files));
  });
}

/* ====================================================================
   STAGE CHANGES
   ==================================================================== */
async function mpApplyStageChange(mid, stage){
  const m = mpMinis.find(x=>x.id===mid);
  if(!m) return;
  if(m.multikit_group && stage !== 'unbuilt'){
    try{
      const res = await api(`/api/minis/${mid}/multikit-options`);
      if(res.options && res.options.length){
        mpShowMultikitModal(res.options, did=>mpCommitStageChange(mid, stage, did));
        return;
      }
    }catch(e){ console.error('Could not load multikit options', e); }
  }
  await mpCommitStageChange(mid, stage, null);
}

async function mpCommitStageChange(mid, stage, datasheet_id){
  const body = {stage};
  if(datasheet_id) body.datasheet_id = datasheet_id;
  try{
    const result = await api(`/api/minis/${mid}/stage`, {method:'PATCH',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const m = mpMinis.find(x=>x.id===mid);
    if(m){
      m.stage = stage;
      if(result.datasheet_id){
        const targetDid = result.datasheet_id;
        m.datasheet_id = targetDid;
        m.multikit_group = null;
        if(targetDid !== mpDatasheetId){
          location.hash = `/mini/${encodeURIComponent(targetDid)}`;
          clearFactionCache();
          refreshLedger();
          return;
        }
      }
    }
    clearFactionCache();
    mpPendingLoadoutMiniId = stage === 'finished' ? mid : null;
    mpRefreshUnitMiniList();
    refreshLedger();
  }catch(e){ console.error('Stage update failed', e); }
}

export async function mpSetMiniStage(mid, stage){
  const sel = document.querySelector(`.stage-sel[data-mid="${CSS.escape(mid)}"]`);
  const prev = sel?.dataset.stage || stage;
  if(sel) sel.value = prev;
  await mpApplyStageChange(mid, stage);
}


/* ====================================================================
   LABEL EDITOR
   ==================================================================== */
export function mpEditGroupLabel(gcid){
  const ed = document.getElementById('mpled-'+gcid);
  if(!ed.hidden){ ed.hidden=true; ed.innerHTML=''; return; }
  const labelEl = document.getElementById('mplabel-'+gcid);
  const cur = labelEl?.textContent === 'Standard' ? '' : (labelEl?.textContent || '');
  ed.innerHTML = `
    <div class="mc-label-ed-inner">
      <input class="ff-input" id="mplinp-${gcid}" value="${esc(cur)}"
             placeholder="Leave blank for Standard" autocomplete="off"
             onkeydown="if(event.key==='Enter')mpSaveGroupLabel('${gcid}');else if(event.key==='Escape')mpEditGroupLabel('${gcid}')">
      <button class="btn-primary" onclick="mpSaveGroupLabel('${gcid}')">Save</button>
      <button class="btn-ghost"   onclick="mpEditGroupLabel('${gcid}')">Cancel</button>
    </div>`;
  ed.hidden = false;
  document.getElementById('mplinp-'+gcid)?.focus();
}

export async function mpSaveGroupLabel(gcid){
  const card  = document.getElementById(gcid);
  const ids   = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  const label = (document.getElementById('mplinp-'+gcid)?.value||'').trim();
  await Promise.all(ids.map(mid=>
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({label})})
  ));
  ids.forEach(mid=>{ const m=mpMinis.find(x=>x.id===mid); if(m) m.label=label; });
  mpRefreshUnitMiniList();
}

/* ====================================================================
   GEAR EDITOR
   ==================================================================== */
function mpNormGear(value){
  return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function mpGearGroups(){
  const groups = mpUnit?.wargear_choice_groups || [];
  if(groups.length) return groups;
  const choices = mpUnit?.wargear_choices || [];
  return choices.length ? [{title:'Loadout', description:'', choices}] : [];
}

function mpKnownGearSet(){
  const known = new Set();
  for(const group of mpGearGroups()){
    for(const choice of group.choices || []) known.add(mpNormGear(choice));
  }
  return known;
}

function mpGearEditorHtml(containerId, currentGear, saveCall, cancelCall, saveLabel){
  const groups = mpGearGroups();
  const current = new Set((currentGear || []).map(mpNormGear));
  const sections = [];
  groups.forEach((group, gi) => {
    // Dedupe within a group only: each option is a distinct rule context, so a
    // weapon legitimately appears under several (e.g. a chainsword swap offered
    // both to the champion and the rank and file). Deduping across groups would
    // hide whole options whose weapons happened to appear earlier.
    const rendered = new Set();
    const choices = [];
    (group.choices || []).forEach((choice, ci) => {
      const key = mpNormGear(choice);
      if(!key || rendered.has(key)) return;
      rendered.add(key);
      const inputId = `${containerId}-opt-${gi}-${ci}`;
      choices.push(`<label class="gear-opt" for="${esc(inputId)}">
        <input id="${esc(inputId)}" type="checkbox" value="${esc(choice)}" ${current.has(key) ? 'checked' : ''}>
        <span>${esc(choice)}</span>
      </label>`);
    });
    if(!choices.length) return;
    sections.push(`<div class="gear-rule">
      <div class="gear-rule-title">${esc(group.title || 'Loadout')}</div>
      ${group.description ? `<div class="gear-rule-desc">${esc(group.description)}</div>` : ''}
      <div class="gear-grid">${choices.join('')}</div>
    </div>`);
  });

  const known = mpKnownGearSet();
  const extras = (currentGear || []).filter(g => !known.has(mpNormGear(g)));
  return `
    <div class="loadout-editor" id="${esc(containerId)}-inner">
      ${sections.join('') || '<div class="gear-rule-desc">No rules-backed loadout options found for this datasheet.</div>'}
      <input class="ff-input gear-custom" placeholder="Other / custom loadout, comma separated"
             value="${esc(extras.join(', '))}" style="margin-top:6px">
      <div class="ff-actions" style="margin-top:8px">
        <button class="btn-primary" onclick="${saveCall}">${esc(saveLabel || 'Save Loadout')}</button>
        <button class="btn-ghost" onclick="${cancelCall}">Cancel</button>
      </div>
    </div>`;
}

function mpCollectGear(containerId){
  const ed = document.getElementById(containerId);
  if(!ed) return [];
  const picked = [...ed.querySelectorAll('.gear-opt input:checked')].map(input => input.value.trim()).filter(Boolean);
  const custom = (ed.querySelector('.gear-custom')?.value || '').split(',').map(s=>s.trim()).filter(Boolean);
  const seen = new Set();
  return [...picked, ...custom].filter(item => {
    const key = mpNormGear(item);
    if(!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function mpEditGroupGear(gcid, forceOpen=false){
  const ed = document.getElementById('mpged-'+gcid);
  if(!ed) return;
  if(!ed.hidden && !forceOpen){ ed.hidden=true; ed.innerHTML=''; return; }
  if(!ed.hidden && forceOpen) return;
  const chipsEl = document.getElementById('mpgear-'+gcid);
  const cur = [...(chipsEl?.querySelectorAll('.gear-chip:not(.muted)')||[])].map(c=>c.textContent);
  const multi = (document.getElementById(gcid)?.dataset.miniIds||'').split(',').filter(Boolean).length > 1;
  ed.innerHTML = mpGearEditorHtml(`mpged-${gcid}`, cur, `mpSaveGroupGear('${gcid}')`, `mpEditGroupGear('${gcid}')`, multi ? 'Save for all' : 'Save Loadout');
  ed.hidden = false;
  ed.querySelector('input')?.focus();
}

export async function mpSaveGroupGear(gcid){
  const card = document.getElementById(gcid);
  const ids  = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  const gear = mpCollectGear(`mpged-${gcid}`);
  await Promise.all(ids.map(mid=>
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wargear:gear})})
  ));
  ids.forEach(mid=>{ const m=mpMinis.find(x=>x.id===mid); if(m) m.wargear=gear; });
  mpRefreshUnitMiniList();
}

export function mpEditMiniGear(mid, forceOpen=false){
  const ed = document.getElementById('mpmed-'+mid);
  if(!ed) return;
  if(!ed.hidden && !forceOpen){ ed.hidden=true; ed.innerHTML=''; return; }
  if(!ed.hidden && forceOpen) return;
  const m = mpMinis.find(x=>x.id===mid);
  const cur = m?.wargear || [];
  ed.innerHTML = mpGearEditorHtml(`mpmed-${mid}`, cur, `mpSaveMiniGear('${mid}')`, `mpEditMiniGear('${mid}')`, 'Save Loadout');
  ed.hidden = false;
  ed.querySelector('input')?.focus();
}

export async function mpSaveMiniGear(mid){
  const gear = mpCollectGear(`mpmed-${mid}`);
  await api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({wargear:gear})});
  const m = mpMinis.find(x=>x.id===mid);
  if(m) m.wargear = gear;
  mpPendingLoadoutMiniId = null;
  mpRefreshUnitMiniList();
}

function mpOpenPendingLoadoutEditor(){
  const mid = mpPendingLoadoutMiniId;
  if(!mid) return;
  const card = [...document.querySelectorAll('.mini-group-card')]
    .find(el => (el.dataset.miniIds || '').split(',').includes(mid));
  if(!card){ mpPendingLoadoutMiniId = null; return; }
  const ids = (card.dataset.miniIds || '').split(',').filter(Boolean);
  if(ids.length === 1){
    mpEditGroupGear(card.id, true);
    card.scrollIntoView({block:'nearest'});
  }else{
    const sub = document.getElementById('mpsc-'+mid);
    const details = sub?.closest('details');
    if(details) details.open = true;
    mpEditMiniGear(mid, true);
    sub?.scrollIntoView({block:'nearest'});
  }
  mpPendingLoadoutMiniId = null;
}

/* ====================================================================
   NOTES
   ==================================================================== */
export function mpSaveMiniNotes(mid, value){
  clearTimeout(MP_NOTE_TIMERS[mid]);
  MP_NOTE_TIMERS[mid] = setTimeout(()=>{
    api(`/api/minis/${mid}`, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({notes:value})}).catch(()=>{});
    const m = mpMinis.find(x=>x.id===mid);
    if(m) m.notes = value;
  }, 600);
}

/* ====================================================================
   PHOTOS
   ==================================================================== */
export async function mpUploadToMini(mid, files){
  if(!files||!files.length) return;
  const up = document.querySelector(`#mpcgal-${mid} .uploader`);
  if(up){ up.classList.add('busy'); up.childNodes[0].textContent='Uploading…'; }
  const fd = new FormData();
  [...files].forEach(f=>fd.append('photos',f));
  const res = await api(`/api/minis/${mid}/photos`, {method:'POST', body:fd});
  const m   = mpMinis.find(x=>x.id===mid);
  if(m && res.photos) m.photos = [...(m.photos||[]), ...res.photos];
  mpRefreshUnitMiniList();
}

export async function mpDeletePhoto(pid, mid){
  if(!confirm('Remove this photo?')) return;
  await fetch(`/api/photos/${pid}`, {method:'DELETE'});
  const m = mpMinis.find(x=>x.id===mid);
  if(m) m.photos = (m.photos||[]).filter(p=>p.id!==pid);
  mpRefreshUnitMiniList();
}

/* ====================================================================
   WORK IN PROGRESS NOTES (unit-level)
   ==================================================================== */
function mpWipPhotoTile(p){
  return `<div class="shot" data-id="${p.id}">
    <img src="${esc(p.url)}" alt="${esc(p.caption||'')}" onclick="openLightbox(${esc(jsStr(p.url))},${esc(jsStr(p.caption||''))})">
    <button class="del" onclick="mpDeleteWipPhoto('${p.id}')" title="Remove photo">&times;</button>
  </div>`;
}

function mpWipUploaderTile(){
  return `<label class="uploader" id="mpWipUploader">
    + Add Photos
    <input type="file" accept="image/*" multiple hidden onchange="mpUploadWipPhotos(this.files)">
  </label>`;
}

function mpRenderWipSection(){
  const notes  = mpUnit?.wip_notes  || '';
  const photos = mpUnit?.wip_photos || [];
  return `<details class="mp-wip mp-rivets" id="mpWip"${notes||photos.length?' open':''}>
    <summary class="mgc-summary mp-wip-summary"><span class="mp-diamond-sm"></span>Work in Progress Notes</summary>
    <div class="mp-wip-body">
      <textarea class="mc-notes mp-wip-notes" id="mpWipNotes"
        placeholder="General notes — colour recipes, conversion ideas, basing plans…"
        oninput="mpSaveUnitNotes(this.value)">${esc(notes)}</textarea>
      <div class="mc-gallery" id="mpWipGallery">
        ${photos.map(p=>mpWipPhotoTile(p)).join('')}
        ${mpWipUploaderTile()}
      </div>
    </div>
  </details>`;
}

function mpRefreshWipGallery(){
  const gal = document.getElementById('mpWipGallery');
  if(!gal) return;
  const photos = mpUnit?.wip_photos || [];
  gal.innerHTML = photos.map(p=>mpWipPhotoTile(p)).join('') + mpWipUploaderTile();
  mpWireWipDropZone();
}

function mpWireWipDropZone(){
  const up = document.getElementById('mpWipUploader');
  if(!up) return;
  ['dragover','dragenter'].forEach(ev=>up.addEventListener(ev,e=>{e.preventDefault();up.classList.add('drag');}));
  ['dragleave','drop'].forEach(ev=>up.addEventListener(ev,e=>{e.preventDefault();up.classList.remove('drag');}));
  up.addEventListener('drop',e=>mpUploadWipPhotos(e.dataTransfer.files));
}

export function mpSaveUnitNotes(value){
  if(mpUnit) mpUnit.wip_notes = value;
  clearTimeout(MP_NOTE_TIMERS.__wip);
  MP_NOTE_TIMERS.__wip = setTimeout(()=>{
    api(`/api/units/${encodeURIComponent(mpDatasheetId)}/wip-notes`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({notes:value})}).catch(()=>{});
  }, 600);
}

export async function mpUploadWipPhotos(files){
  if(!files||!files.length) return;
  const up = document.getElementById('mpWipUploader');
  if(up){ up.classList.add('busy'); up.childNodes[0].textContent='Uploading…'; }
  const fd = new FormData();
  [...files].forEach(f=>fd.append('photos',f));
  try{
    const res = await api(`/api/units/${encodeURIComponent(mpDatasheetId)}/wip-photos`, {method:'POST', body:fd});
    if(mpUnit && res.photos) mpUnit.wip_photos = [...(mpUnit.wip_photos||[]), ...res.photos];
  }catch(e){ console.error('WIP photo upload failed', e); }
  mpRefreshWipGallery();
}

export async function mpDeleteWipPhoto(pid){
  if(!confirm('Remove this photo?')) return;
  await fetch(`/api/wip-photos/${pid}`, {method:'DELETE'});
  if(mpUnit) mpUnit.wip_photos = (mpUnit.wip_photos||[]).filter(p=>p.id!==pid);
  mpRefreshWipGallery();
}

/* ====================================================================
   DELETE
   ==================================================================== */
export async function mpDeleteMini(mid){
  const m = mpMinis.find(x=>x.id===mid);
  const isUnbuilt = !m || m.stage === 'unbuilt';
  const msg = isUnbuilt
    ? 'Remove this mini from your collection entirely? (It will no longer count toward your pool.)'
    : 'Reset this mini to unbuilt? It will go back into your build pool.';
  if(!confirm(msg)) return;
  const res = await fetch(`/api/minis/${mid}`, {method:'DELETE'});
  const data = await res.json().catch(()=>({}));
  if(data.action === 'reset'){
    const idx = mpMinis.findIndex(x=>x.id===mid);
    if(idx !== -1){
      mpMinis[idx] = {...mpMinis[idx], stage:'unbuilt', wargear:[], notes:'', photos:[]};
    }
  } else {
    mpMinis = mpMinis.filter(m=>m.id!==mid);
    if(!mpMinis.length){ history.back(); return; }
  }
  mpRefreshUnitMiniList();
}

export async function mpDeleteOneFromGroup(gcid){
  const card = document.getElementById(gcid);
  const ids  = (card?.dataset.miniIds||'').split(',').filter(Boolean);
  if(!ids.length) return;
  const mid = ids[ids.length-1];
  const m = mpMinis.find(x=>x.id===mid);
  const isUnbuilt = !m || m.stage === 'unbuilt';
  const msg = isUnbuilt
    ? `Remove 1 mini from this group entirely? (${ids.length} total)`
    : `Reset 1 mini in this group to unbuilt? (${ids.length} total)`;
  if(!confirm(msg)) return;
  const res = await fetch(`/api/minis/${mid}`, {method:'DELETE'});
  const data = await res.json().catch(()=>({}));
  if(data.action === 'reset'){
    const idx = mpMinis.findIndex(x=>x.id===mid);
    if(idx !== -1){
      mpMinis[idx] = {...mpMinis[idx], stage:'unbuilt', wargear:[], notes:'', photos:[]};
    }
  } else {
    mpMinis = mpMinis.filter(x=>x.id!==mid);
    if(!mpMinis.length){ history.back(); return; }
  }
  mpRefreshUnitMiniList();
}

/* ====================================================================
   PHOTO OVERLAY
   ==================================================================== */
export function mpOpenGroupOverlay(gcid, startIndex){
  const photos = MP_GROUP_PHOTOS.get(gcid) || [];
  if(!photos.length) return;
  mpOverlayPhotos = photos;
  mpOverlayIndex  = startIndex || 0;

  let ov = document.getElementById('mpPhotoOverlay');
  if(!ov){
    ov = document.createElement('div');
    ov.id = 'mpPhotoOverlay';
    ov.className = 'mgc-overlay';
    ov.setAttribute('hidden','');
    document.body.appendChild(ov);
    ov.addEventListener('click', e=>{ if(e.target===ov) mpCloseGroupOverlay(); });
    document.addEventListener('keydown', e=>{
      if(document.getElementById('mpPhotoOverlay')?.hasAttribute('hidden')) return;
      if(e.key==='Escape')      mpCloseGroupOverlay();
      if(e.key==='ArrowLeft')   mpOverlayNav(-1);
      if(e.key==='ArrowRight')  mpOverlayNav(1);
    });
  }

  const multi = photos.length > 1;
  ov.innerHTML = `
    <button class="mgc-overlay-close" onclick="mpCloseGroupOverlay()" aria-label="Close">✕</button>
    ${multi ? `<button class="mgc-overlay-prev" onclick="mpOverlayNav(-1)" aria-label="Previous">‹</button>` : ''}
    <div class="mgc-overlay-viewer">
      <img id="mpovImg" src="" alt="">
      <p class="mgc-ov-cap" id="mpovCap"></p>
    </div>
    ${multi ? `<button class="mgc-overlay-next" onclick="mpOverlayNav(1)" aria-label="Next">›</button>` : ''}
    ${multi ? `<div class="mgc-overlay-counter" id="mpovCounter"></div>` : ''}`;

  ov.removeAttribute('hidden');
  mpOverlayRender();
}

function mpOverlayRender(){
  const p = mpOverlayPhotos[mpOverlayIndex];
  if(!p) return;
  const img = document.getElementById('mpovImg');
  if(img){ img.src = p.url; img.alt = p.caption || ''; }
  const cap = document.getElementById('mpovCap');
  if(cap) cap.textContent = p.caption || '';
  const counter = document.getElementById('mpovCounter');
  if(counter) counter.textContent = `${mpOverlayIndex + 1} / ${mpOverlayPhotos.length}`;
  const n = mpOverlayPhotos.length;
  const prev = document.querySelector('#mpPhotoOverlay .mgc-overlay-prev');
  const next = document.querySelector('#mpPhotoOverlay .mgc-overlay-next');
  if(prev) prev.style.opacity = mpOverlayIndex === 0 ? '0.25' : '';
  if(next) next.style.opacity = mpOverlayIndex === n - 1 ? '0.25' : '';
}

export function mpOverlayNav(delta){
  const n = mpOverlayPhotos.length;
  if(!n) return;
  mpOverlayIndex = (mpOverlayIndex + delta + n) % n;
  mpOverlayRender();
}

export function mpCloseGroupOverlay(){
  document.getElementById('mpPhotoOverlay')?.setAttribute('hidden','');
}

/* ====================================================================
   MULTIKIT MODAL
   ==================================================================== */
function mpShowMultikitModal(options, onPick){
  let modal = document.getElementById('mpMkModal');
  if(!modal){
    modal = document.createElement('div');
    modal.id = 'mpMkModal';
    modal.className = 'mmk-overlay';
    document.body.appendChild(modal);
  }
  modal.innerHTML = `
    <div class="mmk-panel">
      <div class="mmk-title">What are you building?</div>
      <p class="mmk-sub">This kit can be assembled as multiple units. Pick one:</p>
      <div class="mmk-options">
        ${options.map(o=>`
          <button class="mmk-opt" data-did="${esc(o.datasheet_id)}">
            <span class="mmk-opt-name">${esc(o.name)}</span>
            <span class="mmk-opt-faction">${esc(o.faction_display_name || o.faction_name)}</span>
          </button>`).join('')}
      </div>
      <button class="btn-ghost mmk-cancel">Cancel</button>
    </div>`;
  modal.removeAttribute('hidden');
  modal.querySelectorAll('.mmk-opt').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      modal.setAttribute('hidden','');
      onPick(btn.dataset.did);
    });
  });
  modal.querySelector('.mmk-cancel').addEventListener('click', ()=>modal.setAttribute('hidden',''));
}

/* ====================================================================
   CATALOGUE CARD IN LEFT COLUMN
   ==================================================================== */
function mpCatRenderCard(item){
  const faction = mpCatalogueFactions.find(f => f.id === item.faction_id);
  let cls = '', style = '', mark = '';
  if(faction){
    cls = ' faction-surface catalogue-faction-card';
    style = ` style="--cardarmy:${faction.primary};--cardaccent:${faction.accent};--cardglow:${faction.accent}"`;
    mark = faction.icon_url
      ? `<div class="faction-bg-mark catalogue-card-mark" aria-hidden="true"><img src="${esc(faction.icon_url)}" alt="" loading="lazy"></div>`
      : `<div class="faction-bg-mark catalogue-card-mark" aria-hidden="true"><span class="faction-bg-letter">${esc(((faction.display_name||faction.name)||'?')[0])}</span></div>`;
  }
  const date = item.release_date || item.release_year || 'date unknown';
  const links = item.datasheet_links || [];
  const flagHtml = (item.flags||[]).length
    ? `<p class="catalogue-flags">${item.flags.map(f=>`<span class="catalogue-flag">${esc(f)}</span>`).join('')}</p>`
    : '';
  const linksHtml = links.length
    ? links.map(l=>`<a href="/#/unit/${esc(l.datasheet_id)}" class="catalogue-link">
        <b>${esc(l.datasheet_name)}</b>
        <small>${esc(l.faction_id)} · ${esc(l.role||'role unknown')} · ${esc(l.datasheet_id)}</small>
      </a>`).join('')
    : '<span class="catalogue-unlinked">No current datasheet</span>';
  return `
    <article class="catalogue-card mp-sculpt mp-rivets${item.image?' has-image':''}${cls}"${style} data-cid="${esc(item.id)}">
      ${mark}
      ${item.image
        ? `<div class="catalogue-image mp-stage catalogue-image-clickable" data-lightbox-url="${esc(item.image.url)}" data-lightbox-cap="${esc(item.name)}">
             ${mpDataPlateHtml()}
             <img src="${esc(item.image.url)}" alt="${esc(item.name)}" loading="lazy">
             ${mpEmblemHtml(item.faction_id)}
           </div>`
        : `<div class="catalogue-image mp-stage">
             ${mpDataPlateHtml()}
             <img src="/api/units/${esc(mpDatasheetId)}/image" alt="${esc(item.name)}" loading="lazy">
             ${mpEmblemHtml(item.faction_id)}
           </div>`}
      <div class="catalogue-card-head">
        <div>
          <h4><span class="catalogue-name-text">${esc(item.name)}</span></h4>
          <p class="catalogue-meta">${esc(item.faction_label_display || item.faction_label)} · ${esc(date)} · ${esc(item.material||'material unknown')}${item.status==='discontinued'?' · <em>Discontinued</em>':''}</p>
        </div>
        <span class="catalogue-year">${esc(item.release_year||'')}</span>
      </div>
      ${item.note?`<p class="catalogue-note">${esc(item.note)}</p>`:''}
      ${item.resolution_notes?`<p class="catalogue-note">${esc(item.resolution_notes)}</p>`:''}
      ${flagHtml}
      <div class="catalogue-links">${linksHtml}</div>
      <div class="catalogue-card-actions">
        <button class="btn-secondary btn-sm cle-open-btn cfe-open-btn" data-cid="${esc(item.id)}">Edit</button>
        <button class="btn-secondary btn-sm catalogue-dup-btn" data-cid="${esc(item.id)}" data-name="${esc(item.name)}">Duplicate</button>
        <button class="btn-danger btn-sm catalogue-delete-btn" data-cid="${esc(item.id)}">Delete</button>
      </div>
      <p class="catalogue-id">ID: ${esc(item.id)}</p>
    </article>`;
}

function mpCatWireCards(){
  const col = document.getElementById('mpCatalogueCol');
  if(!col) return;
  col.addEventListener('click', e => {
    const imgEl = e.target.closest('.catalogue-image-clickable');
    if(imgEl){ openLightbox(imgEl.dataset.lightboxUrl, imgEl.dataset.lightboxCap); return; }

    const delBtn = e.target.closest('.catalogue-delete-btn');
    if(delBtn){ mpCatDelete(delBtn.dataset.cid); return; }

    const editBtn = e.target.closest('.cfe-open-btn');
    if(editBtn){ mpCatOpenFieldEditor(editBtn.dataset.cid); return; }

    const dupBtn = e.target.closest('.catalogue-dup-btn');
    if(dupBtn){ mpCatDuplicate(dupBtn.dataset.cid, dupBtn.dataset.name); return; }

    const linksBtn = e.target.closest('.cle-open-btn');
    if(linksBtn){ mpCatOpenLinkEditor(linksBtn.dataset.cid, linksBtn.dataset.fid); }
  });
}

async function mpRefreshCatalogueCards(){
  const ids = mpCatalogueItems.map(i => i.id).filter(Boolean);
  if(!ids.length) return;
  try{
    const results = await Promise.all(
      ids.map(id => api(`/api/model-catalogue/${encodeURIComponent(id)}`))
    );
    mpCatalogueItems = results.map(r => r.item).filter(Boolean);
    const f = results.find(r => r.factions?.length)?.factions;
    if(f) mpCatalogueFactions = f;
  }catch(e){ return; }
  mpRerenderLeftMedia();
}

async function mpCatDelete(cid){
  const item = mpCatalogueItems.find(i => i.id === cid);
  if(!item) return;
  if(!confirm(`Delete "${item.name}"?\n\nThis cannot be undone.`)) return;
  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}`, {method:'DELETE'});
    const json = await r.json();
    if(!r.ok) throw new Error(json.error || `HTTP ${r.status}`);
    mpCatalogueItems = mpCatalogueItems.filter(i => i.id !== cid);
    mpRerenderLeftMedia();
  }catch(e){ alert(`Could not delete: ${e.message}`); }
}

async function mpCatDuplicate(cid, name){
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/duplicate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name}),
    });
    const newId = res.record?.id;
    if(newId) window.location.href = `/catalogue-review?model=${encodeURIComponent(newId)}`;
  }catch(e){ alert('Duplicate failed: ' + e.message); }
}

/* ---- catalogue field editor ---- */

function mpCatOpenFieldEditor(cid, opts = {}){
  if(mpCatFed.cid === cid){ mpCatCloseFieldEditor(); return; }
  if(mpCatFed.cid) mpCatCloseFieldEditor();
  if(mpCatEd.cid) mpCatCloseLinkEditor();

  const item = mpCatalogueItems.find(i => i.id === cid);
  if(!item) return;
  mpCatFed.cid = cid;
  mpCatFed.focusLinks = !!opts.focusLinks;

  const card = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  if(card) card.classList.add('is-editing');

  const matOpts = ['Plastic','Resin','Metal','Finecast','Other'].map(m =>
    `<option value="${m}"${(item.material||'Plastic')===m?' selected':''}>${m}</option>`
  ).join('');
  const armyOpts = [
    `<option value="">— None —</option>`,
    ...mpCatalogueFactions.map(f =>
      `<option value="${esc(f.id)}"${f.id===(item.faction_id||'')?'  selected':''}>${esc(f.name)}</option>`
    ),
  ].join('');

  const backdrop = document.createElement('div');
  backdrop.className = 'cfe-backdrop';
  backdrop.id = 'mpCatalogueFieldBackdrop';
  backdrop.innerHTML = `
    <div class="cfe-box" role="dialog" aria-modal="true" aria-labelledby="mpCfeTitle">
      <div class="am-head">
        <span class="am-title" id="mpCfeTitle">Edit Model</span>
        <button class="am-close mpCfeClose" title="Close">×</button>
      </div>
      <div class="catalogue-field-editor" id="mpCfeEditor">
        <div class="cfe-grid">
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="mpCfeName">Name</label>
            <input class="cfe-input" id="mpCfeName" type="text" value="${esc(item.name)}" maxlength="300" autocomplete="off">
          </div>
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="mpCfeArmy">Army</label>
            <select class="cfe-input" id="mpCfeArmy">${armyOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="mpCfeDate">Release Date</label>
            <input class="cfe-input" id="mpCfeDate" type="text" value="${esc(item.release_date||'')}"
                   placeholder="YYYY or YYYY-MM" maxlength="7" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label" for="mpCfeMaterial">Material</label>
            <select class="cfe-input" id="mpCfeMaterial">${matOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="mpCfeStatus">Status</label>
            <select class="cfe-input" id="mpCfeStatus">
              <option value="current_or_unknown"${item.status==='current_or_unknown'?' selected':''}>Current / Unknown</option>
              <option value="discontinued"${item.status==='discontinued'?' selected':''}>Discontinued</option>
            </select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="mpCfeNote">Note</label>
            <input class="cfe-input" id="mpCfeNote" type="text" value="${esc(item.note||'')}" maxlength="500" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label" for="mpCfeFlags">Flags <span class="cfe-hint">(comma-separated)</span></label>
            <input class="cfe-input" id="mpCfeFlags" type="text" value="${esc((item.flags||[]).join(', '))}"
                   placeholder="e.g. exclusive, limited" autocomplete="off">
          </div>
        </div>
        ${mpCatRenderLinkSection(item, opts.defaultFid)}
        ${mpCatRenderImageSection(item)}
        <p class="cfe-err" id="mpCfeErr" hidden></p>
        <div class="am-foot">
          <button class="btn-primary mpCfeSave">Save Changes</button>
          <button class="btn-ghost mpCfeCancel">Cancel</button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(backdrop);
  backdrop.querySelector('#mpCfeName').focus({ preventScroll: true });
  backdrop.querySelector('.mpCfeSave').addEventListener('click', mpCatSaveFieldEdits);
  backdrop.querySelector('.mpCfeCancel').addEventListener('click', mpCatCloseFieldEditor);
  backdrop.querySelector('.mpCfeClose').addEventListener('click', mpCatCloseFieldEditor);
  backdrop.addEventListener('click', e => { if(e.target === backdrop) mpCatCloseFieldEditor(); });
  backdrop.addEventListener('keydown', e => { if(e.key === 'Escape') mpCatCloseFieldEditor(); });
  mpCatWireImageControls(backdrop.querySelector('#mpCfeEditor'), cid);
  mpCatWireLinkControls(backdrop.querySelector('#mpCfeEditor'));
  if(mpCatFed.focusLinks){
    document.getElementById('mpCfeLinkSection')?.scrollIntoView({ block: 'center' });
    backdrop.querySelector('#mpCleSearch')?.focus({ preventScroll: true });
  }
}

function mpCatRenderImageSection(item){
  if(item.image){
    return `
      <div class="cfe-img-section" id="mpCfeImgSection">
        <div class="am-label">Image</div>
        <div class="cfe-img-preview">
          <img src="${esc(item.image.url)}?v=${Date.now()}" alt="${esc(item.name)}">
          <button class="link-btn ref-clear mpCfeImgClear">Remove Image</button>
        </div>
      </div>`;
  }
  const googleUrl = 'https://www.google.com/search?tbm=isch&q=' +
    encodeURIComponent(`${item.name} ${item.faction_label} Warhammer 40k miniature`);
  return `
    <div class="cfe-img-section" id="mpCfeImgSection">
      <div class="am-label">Image</div>
      <a class="ref-search" href="${esc(googleUrl)}" target="_blank" rel="noopener noreferrer">Find an image ↗</a>
      <div class="ref-row">
        <input class="cfe-input" id="mpCfeImgUrl" placeholder="Paste image address here…" autocomplete="off">
        <button class="btn-primary" id="mpCfeImgSave">Save</button>
      </div>
      <p class="ref-alt">or <label class="link-btn ref-file">choose a file<input type="file" id="mpCfeImgFile" accept="image/*" hidden></label></p>
      <p class="ref-msg" id="mpCfeImgMsg"></p>
    </div>`;
}

function mpCatWireImageControls(panel, cid){
  const saveBtn = panel.querySelector('#mpCfeImgSave');
  const clearBtn = panel.querySelector('.mpCfeImgClear');
  const fileIn  = panel.querySelector('#mpCfeImgFile');
  const urlIn   = panel.querySelector('#mpCfeImgUrl');
  if(saveBtn)  saveBtn.addEventListener('click', () => mpCatSaveImageFromUrl(cid));
  if(clearBtn) clearBtn.addEventListener('click', () => mpCatClearImage(cid));
  if(fileIn)   fileIn.addEventListener('change', () => { if(fileIn.files[0]) mpCatSaveImageFromFile(cid, fileIn.files[0]); });
  if(urlIn)    urlIn.addEventListener('keydown', e => { if(e.key==='Enter') mpCatSaveImageFromUrl(cid); });
}

function mpCatImgMsg(text, ok){
  const el = document.getElementById('mpCfeImgMsg');
  if(!el) return;
  el.textContent = text || '';
  el.className = 'ref-msg' + (text ? (ok ? ' ok' : ' err') : '');
}

async function mpCatSaveImageFromUrl(cid){
  const input = document.getElementById('mpCfeImgUrl');
  const url = (input?.value || '').trim();
  if(!url){ mpCatImgMsg('Paste an image address first.', false); return; }
  mpCatImgMsg('Fetching image…', true);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}),
    });
    if(res.ok) mpCatAfterImageSaved(cid, res.image_url);
    else mpCatImgMsg(res.error || 'Could not save that image.', false);
  }catch(e){ mpCatImgMsg('Could not save that image.', false); }
}

async function mpCatSaveImageFromFile(cid, fileObj){
  mpCatImgMsg('Saving image…', true);
  const fd = new FormData();
  fd.append('file', fileObj);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {method:'POST', body:fd});
    if(res.ok) mpCatAfterImageSaved(cid, res.image_url);
    else mpCatImgMsg(res.error || 'Could not save.', false);
  }catch(e){ mpCatImgMsg('Could not save.', false); }
}

function mpCatAfterImageSaved(cid, imageUrl){
  const item = mpCatalogueItems.find(i => i.id === cid);
  if(item) item.image = {url: imageUrl, caption:'', source:'user', lexicanum_page:'', file_page_url:''};
  if(mpCatFed.cid === cid){
    const section = document.getElementById('mpCfeImgSection');
    if(section && item){
      section.outerHTML = mpCatRenderImageSection(item);
      const newSection = document.getElementById('mpCfeImgSection');
      if(newSection){ const panel = newSection.closest('#mpCfeEditor'); if(panel) mpCatWireImageControls(panel, cid); }
    }
  }
  const cardImg = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image img`);
  if(cardImg) cardImg.src = `${imageUrl}?v=${Date.now()}`;
  const emptyDiv = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image-empty`);
  if(emptyDiv) emptyDiv.outerHTML = `<div class="catalogue-image catalogue-image-clickable" data-lightbox-url="${esc(imageUrl)}" data-lightbox-cap=""><img src="${esc(imageUrl)}" alt="" loading="lazy"></div>`;
}

async function mpCatClearImage(cid){
  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {method:'DELETE'});
    if(!r.ok){ const json = await r.json().catch(()=>({})); mpCatImgMsg(json.error||`Server error (${r.status}).`, false); return; }
    const item = mpCatalogueItems.find(i => i.id === cid);
    if(item) item.image = null;
    if(mpCatFed.cid === cid){
      const section = document.getElementById('mpCfeImgSection');
      if(section && item){
        section.outerHTML = mpCatRenderImageSection(item);
        const newSection = document.getElementById('mpCfeImgSection');
        if(newSection){ const panel = newSection.closest('#mpCfeEditor'); if(panel) mpCatWireImageControls(panel, cid); }
      }
    }
    const cardImg = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image`);
    if(cardImg) cardImg.outerHTML = '<div class="catalogue-image catalogue-image-empty"></div>';
  }catch(e){ mpCatImgMsg('Could not remove image.', false); }
}

function mpCatCloseFieldEditor(){
  if(!mpCatFed.cid) return;
  const card = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(mpCatFed.cid)}"]`);
  if(card) card.classList.remove('is-editing');
  document.getElementById('mpCatalogueFieldBackdrop')?.remove();
  mpCatFed.cid = null;
  mpCatFed.focusLinks = false;
  mpCatEd.cid = null; mpCatEd.selected = []; mpCatEd.factionId = '';
}

async function mpCatSaveFieldEdits(){
  if(!mpCatFed.cid) return;
  const cid = mpCatFed.cid;
  const saveBtn = document.querySelector('.mpCfeSave');
  if(saveBtn){ saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  document.getElementById('mpCfeErr').hidden = true;

  const name = document.getElementById('mpCfeName').value.trim();
  if(!name){
    mpCatShowFieldErr('Name cannot be empty.');
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    return;
  }
  const release_date = document.getElementById('mpCfeDate').value.trim();
  if(release_date && !/^\d{4}(-\d{2})?$/.test(release_date)){
    mpCatShowFieldErr('Release date must be YYYY or YYYY-MM (e.g. 2024-06).');
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    return;
  }
  const payload = {
    name,
    release_date,
    material:   document.getElementById('mpCfeMaterial').value,
    status:     document.getElementById('mpCfeStatus').value,
    note:       document.getElementById('mpCfeNote').value.trim(),
    flags:      document.getElementById('mpCfeFlags').value.split(',').map(f=>f.trim()).filter(Boolean),
    faction_id: document.getElementById('mpCfeArmy').value,
  };
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    if(!res.ok) throw new Error(res.error || 'Save failed');
    await mpCatSaveLinkSelection(cid);
    mpCatCloseFieldEditor();
    await mpRefreshCatalogueCards();
  }catch(e){
    mpCatShowFieldErr(e.message);
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
  }
}

function mpCatShowFieldErr(msg){
  const el = document.getElementById('mpCfeErr');
  if(el){ el.textContent = msg; el.hidden = false; }
}

/* ---- catalogue link editor ---- */

function mpCatOpenLinkEditor(cid, defaultFid){
  mpCatOpenFieldEditor(cid, { focusLinks: true, defaultFid });
}

function mpCatCloseLinkEditor(){
  if(!mpCatEd.cid) return;
  const card = document.querySelector(`#mpCatalogueCol .catalogue-card[data-cid="${CSS.escape(mpCatEd.cid)}"]`);
  if(card){ card.classList.remove('is-editing'); card.querySelector('.catalogue-link-editor')?.remove(); }
  mpCatEd.cid = null; mpCatEd.selected = []; mpCatEd.factionId = '';
}

function mpCatRenderLinkSection(item, defaultFid){
  mpCatEd.cid = item.id;
  const firstLinkedFid = (item.datasheet_links || [])[0]?.faction_id || '';
  mpCatEd.factionId = defaultFid || firstLinkedFid || '';
  mpCatEd.selected = (item.datasheet_links || []).map(l => ({...l}));

  const factionOptions = [
    `<option value="">All factions</option>`,
    ...mpCatalogueFactions.map(f =>
      `<option value="${esc(f.id)}"${f.id===mpCatEd.factionId?' selected':''}>${esc(f.name)}</option>`
    ),
  ].join('');

  return `
    <div class="cfe-link-section" id="mpCfeLinkSection">
      <div class="cle-head">Datasheet Links</div>
      <div class="cle-selected" id="mpCleChips"></div>
      <div class="cle-search-row">
        <select class="cle-faction-sel" id="mpCleFaction">${factionOptions}</select>
        <input class="cle-search-input" id="mpCleSearch" type="search" placeholder="Search datasheets..." autocomplete="off">
      </div>
      <div class="cle-results" id="mpCleResults">
        <div class="cle-hint">Choose a faction or type to search all armies.</div>
      </div>
    </div>`;
}

function mpCatWireLinkControls(panel){
  mpCatRefreshChips();

  let searchTimer;
  panel.querySelector('#mpCleFaction')?.addEventListener('change', e => {
    mpCatEd.factionId = e.target.value;
    mpCatSearchDatasheets(panel.querySelector('#mpCleSearch')?.value || '');
  });
  panel.querySelector('#mpCleSearch')?.addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => mpCatSearchDatasheets(e.target.value), 220);
  });
  panel.querySelector('#mpCleChips')?.addEventListener('click', e => {
    const btn = e.target.closest('.cle-chip-del');
    if(!btn) return;
    mpCatEd.selected = mpCatEd.selected.filter(l => l.datasheet_id !== btn.dataset.did);
    mpCatRefreshChips();
    mpCatRefreshResultHighlights();
  });

  if(mpCatEd.factionId) mpCatSearchDatasheets('');
}

function mpCatRefreshChips(){
  const el = document.getElementById('mpCleChips');
  if(!el) return;
  if(!mpCatEd.selected.length){
    el.innerHTML = '<span class="cle-none">No datasheets selected — search below to add</span>';
    return;
  }
  el.innerHTML = mpCatEd.selected.map(l => `
    <span class="cle-chip">
      <span class="cle-chip-name">${esc(l.datasheet_name)}</span>
      <span class="cle-chip-meta">${esc(l.faction_id)}</span>
      <button class="cle-chip-del" data-did="${esc(l.datasheet_id)}" title="Remove">×</button>
    </span>`).join('');
}

async function mpCatSearchDatasheets(q){
  const resultsEl = document.getElementById('mpCleResults');
  if(!resultsEl) return;
  const trimmed = (q || '').trim();
  if(!mpCatEd.factionId && !trimmed){
    resultsEl.innerHTML = '<div class="cle-hint">Choose a faction or type to search all armies.</div>';
    return;
  }
  resultsEl.innerHTML = '<div class="cle-hint">Searching…</div>';
  try{
    const params = new URLSearchParams();
    if(mpCatEd.factionId) params.set('faction_id', mpCatEd.factionId);
    if(trimmed) params.set('q', trimmed);
    const results = await api(`/api/units/search?${params}`);
    mpCatRenderSearchResults(resultsEl, results);
  }catch(e){
    resultsEl.innerHTML = `<div class="cle-hint cle-err">Search failed: ${esc(e.message)}</div>`;
  }
}

function mpCatRenderSearchResults(el, results){
  if(!results || !results.length){ el.innerHTML = '<div class="cle-hint">No datasheets found.</div>'; return; }
  const selectedIds = new Set(mpCatEd.selected.map(l => l.datasheet_id));
  el.innerHTML = results.map(u => `
    <div class="cle-result-row${selectedIds.has(u.id)?' is-selected':''}"
         data-did="${esc(u.id)}" data-name="${esc(u.name)}"
         data-fid="${esc(u.faction_id||'')}" data-role="${esc(u.role||'')}">
      <span class="cle-result-name">${esc(u.name)}</span>
      <span class="cle-result-meta">${esc(u.role||'')}${u.faction_id?' · '+esc(u.faction_id):''}</span>
      <span class="cle-result-id">${esc(u.id)}</span>
      <a class="cle-result-link" href="/#/unit/${esc(u.id)}" target="_blank" rel="noopener" title="View datasheet">↗</a>
      <span class="cle-result-tick">${selectedIds.has(u.id)?'✓':'+'}</span>
    </div>`).join('');
  el.querySelectorAll('.cle-result-row').forEach(row => {
    row.addEventListener('click', e => {
      if(e.target.closest('.cle-result-link')) return;
      mpCatToggleResultRow(row);
    });
  });
}

function mpCatToggleResultRow(row){
  const did = row.dataset.did;
  const already = mpCatEd.selected.find(l => l.datasheet_id === did);
  if(already){ mpCatEd.selected = mpCatEd.selected.filter(l => l.datasheet_id !== did); }
  else{ mpCatEd.selected.push({datasheet_id:did, datasheet_name:row.dataset.name, faction_id:row.dataset.fid, role:row.dataset.role}); }
  mpCatRefreshChips();
  mpCatRefreshResultHighlights();
}

function mpCatRefreshResultHighlights(){
  const selectedIds = new Set(mpCatEd.selected.map(l => l.datasheet_id));
  document.querySelectorAll('#mpCleResults .cle-result-row').forEach(row => {
    const sel = selectedIds.has(row.dataset.did);
    row.classList.toggle('is-selected', sel);
    const tick = row.querySelector('.cle-result-tick');
    if(tick) tick.textContent = sel ? '✓' : '+';
  });
}

async function mpCatSaveLinkSelection(cid){
  if(!cid) return;
  const ids = mpCatEd.selected.map(l => l.datasheet_id);
  const action = ids.length === 0 ? 'no_current_datasheet'
               : ids.length === 1 ? 'link_datasheet'
               :                    'link_multiple_datasheets';
  const res = await api(`/api/catalogue-review/${encodeURIComponent(cid)}/resolution`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action, datasheet_ids: ids}),
  });
  if(!res.ok) throw new Error(res.error || 'Link save failed');
}


/* ====================================================================
   EXPOSE TO WINDOW (for inline onclick handlers in rendered HTML)
   ==================================================================== */
Object.assign(window, {
  openLightbox,
  mpSetMiniStage,
  mpEditGroupLabel, mpSaveGroupLabel,
  mpEditGroupGear,  mpSaveGroupGear,
  mpEditMiniGear,   mpSaveMiniGear,
  mpSaveMiniNotes,
  mpUploadToMini,   mpDeletePhoto,
  mpSaveUnitNotes,  mpUploadWipPhotos, mpDeleteWipPhoto,
  mpDeleteMini,     mpDeleteOneFromGroup,
  mpOpenGroupOverlay, mpCloseGroupOverlay, mpOverlayNav,
});
