import { api, esc } from './utils.js';
import { refreshLedger, setBreadcrumb } from './header.js';
import { openLightbox, initLightbox } from './lightbox.js';

let state = {
  items: [],
  factions: [],
  summary: {},
  army: 'All',
  linkFilter: 'all',
  q: '',
};

/* ---- editor state (only one open at a time) ----------------------------- */
let ed = {
  cid: null,
  factionId: '',
  selected: [],   // [{datasheet_id, datasheet_name, faction_id, role}]
};

let fed = { cid: null, focusLinks: false }; // field editor state

/* ---- load --------------------------------------------------------------- */

async function load(){
  const data = await api('/api/model-catalogue');
  state.items = data.items || [];
  state.factions = data.factions || [];
  state.summary = data.summary || {};
  renderControls();
  render();
  focusCatalogueTarget();
}

function renderControls(){
  const armyOptions = [
    `<option value="All">All armies (${state.summary.model_count || 0})</option>`,
    ...state.factions.map(f => `<option value="${esc(f.id)}">${esc(f.display_name || f.name)} (${f.count})</option>`),
  ];
  document.getElementById('catalogueArmy').innerHTML = armyOptions.join('');
  document.getElementById('catalogueArmy').value = state.army;
  document.getElementById('catalogueSearch').value = state.q;
  document.getElementById('catalogueLinkFilter').value = state.linkFilter;
}

/* ---- filter + render ---------------------------------------------------- */

function filteredItems(){
  const q = state.q.trim().toLowerCase();
  return state.items.filter(item => {
    if(state.army !== 'All' && !(item.army_ids || []).includes(state.army)) return false;
    const linked = (item.datasheet_links || []).length > 0;
    if(state.linkFilter === 'linked' && !linked) return false;
    if(state.linkFilter === 'unlinked' && linked) return false;
    if(!q) return true;
    const hay = [
      item.name,
      item.faction_label,
      item.faction_label_display,
      item.release_date,
      item.material,
      item.note,
      item.resolution_notes,
      ...((item.datasheet_links || []).flatMap(l => [
        l.datasheet_name, l.datasheet_id, l.faction_id, l.role,
      ])),
    ].join(' ').toLowerCase();
    return hay.includes(q);
  });
}

/* ---- progressive rendering ---------------------------------------------
   The catalogue can hold ~900 cards. Painting them all at once produced a
   page tens of thousands of pixels tall and made scrolling and editing
   sluggish. Instead we flatten the grouped items into one ordered sequence
   and paint it in chunks, appending more as an IntersectionObserver sentinel
   nears the viewport. Grouping headers and the faction grid are preserved. */
const CHUNK_FIRST = 60;   // cards painted on the first pass
const CHUNK_MORE  = 48;   // cards added each time the sentinel is reached
let rstate = { flat: [], counts: new Map(), rendered: 0, observer: null, curGridEl: null, curGroupName: null };

function render(){
  const items = filteredItems();
  document.getElementById('reviewProgress').innerHTML = `
    <b>${items.length}</b><span>shown</span>
    <b>${state.summary.linked_count || 0}</b><span>linked</span>
  `;
  const list = document.getElementById('catalogueList');

  if(rstate.observer) rstate.observer.disconnect();
  rstate = { flat: [], counts: new Map(), rendered: 0, observer: null, curGridEl: null, curGroupName: null };

  if(!items.length){
    list.innerHTML = '<div class="review-empty">No catalogue models match this filter.</div>';
    return;
  }

  for(const group of grouped(items)){
    rstate.counts.set(group.name, group.rows.length);
    for(const item of group.rows) rstate.flat.push({ group: group.name, item });
  }

  list.innerHTML = '';
  appendCards(CHUNK_FIRST);
  setupInfiniteScroll();
}

// Paint up to `count` more cards, opening a new faction section when the group changes.
function appendCards(count){
  const list = document.getElementById('catalogueList');
  let added = 0;
  while(added < count && rstate.rendered < rstate.flat.length){
    const { group, item } = rstate.flat[rstate.rendered];
    if(group !== rstate.curGroupName || !rstate.curGridEl){
      const section = document.createElement('section');
      section.className = 'catalogue-group';
      section.innerHTML =
        `<h3 class="role-head">${esc(group)} <span>${rstate.counts.get(group) || 0}</span></h3>` +
        `<div class="catalogue-grid"></div>`;
      list.appendChild(section);
      rstate.curGridEl = section.querySelector('.catalogue-grid');
      rstate.curGroupName = group;
    }
    rstate.curGridEl.insertAdjacentHTML('beforeend', renderItem(item));
    rstate.rendered++;
    added++;
  }
  return rstate.rendered < rstate.flat.length;   // true while more remain
}

function setupInfiniteScroll(){
  const list = document.getElementById('catalogueList');
  if(rstate.rendered >= rstate.flat.length) return;   // everything already fits
  const sentinel = document.createElement('div');
  sentinel.className = 'catalogue-sentinel';
  sentinel.setAttribute('aria-hidden', 'true');
  list.appendChild(sentinel);
  rstate.observer = new IntersectionObserver(entries => {
    if(!entries.some(en => en.isIntersecting)) return;
    if(appendCards(CHUNK_MORE)){
      list.appendChild(sentinel);   // keep the sentinel as the last element
    } else {
      rstate.observer.disconnect();
      rstate.observer = null;
      sentinel.remove();
    }
  }, { rootMargin: '900px 0px' });
  rstate.observer.observe(sentinel);
}

// Paint chunks until a specific card exists (used for scroll-to-target and post-duplicate).
function ensureRendered(cid){
  let guard = 0;
  while(rstate.rendered < rstate.flat.length &&
        !document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`) &&
        guard++ < 2000){
    appendCards(CHUNK_MORE);
  }
}

function catalogueTargetId(){
  const queryId = new URLSearchParams(location.search).get('model');
  if(queryId) return queryId;
  const hash = decodeURIComponent((location.hash || '').replace(/^#\/?/, '').trim());
  if(!hash) return '';
  return hash.startsWith('model=') ? hash.slice(6) : hash;
}

function focusCatalogueTarget(){
  const cid = catalogueTargetId();
  if(!cid) return;
  if(!state.items.some(item => item.id === cid)) return;
  let card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  if(!card){
    // paint up to it within the current filter set
    ensureRendered(cid);
    card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  }
  if(!card){
    // a filter is hiding it: clear filters, repaint, then paint up to it
    state.army = 'All';
    state.linkFilter = 'all';
    state.q = '';
    renderControls();
    render();
    ensureRendered(cid);
    card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  }
  if(!card) return;
  document.querySelectorAll('.catalogue-card.is-targeted')
    .forEach(el => el.classList.remove('is-targeted'));
  card.classList.add('is-targeted');
  card.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function grouped(items){
  // Group rows by canonical faction_label so collapsed/expanded state stays
  // stable, but render the heading with the display label (common_name when
  // the faction has one).
  const groups = new Map();
  for(const item of items){
    const key = state.army === 'All' ? item.faction_label : armyName(state.army);
    const heading = state.army === 'All'
      ? (item.faction_label_display || item.faction_label)
      : armyDisplayName(state.army);
    if(!groups.has(key)) groups.set(key, { heading, rows: [] });
    groups.get(key).rows.push(item);
  }
  return [...groups.entries()].map(([_, g]) => ({ name: g.heading, rows: g.rows }));
}

function armyName(fid){
  return state.factions.find(f => f.id === fid)?.name || fid;
}

function armyDisplayName(fid){
  const f = state.factions.find(f => f.id === fid);
  return f?.display_name || f?.name || fid;
}

function factionForItem(item){
  const fid = item.faction_id || (item.army_ids || [])[0] || '';
  return state.factions.find(f => f.id === fid) || null;
}

function cardSurfaceForItem(item){
  const faction = factionForItem(item);
  if(!faction) return { cls:'', style:'', mark:'' };
  const markLetterSource = faction.display_name || faction.name || item.faction_label_display || item.faction_label || '?';
  const mark = faction.icon_url
    ? `<div class="faction-bg-mark catalogue-card-mark" aria-hidden="true"><img src="${esc(faction.icon_url)}" alt="" loading="lazy"></div>`
    : `<div class="faction-bg-mark catalogue-card-mark" aria-hidden="true"><span class="faction-bg-letter">${esc(markLetterSource[0])}</span></div>`;
  return {
    cls: ' faction-surface catalogue-faction-card',
    style: ` style="--cardarmy:${faction.primary};--cardaccent:${faction.accent};--cardglow:${faction.accent}"`,
    mark,
  };
}

function renderItem(item){
  const links = item.datasheet_links || [];
  const date  = item.release_date || item.release_year || 'date unknown';
  const surface = cardSurfaceForItem(item);
  const flagHtml = (item.flags || []).length
    ? `<p class="catalogue-flags">${(item.flags).map(f => `<span class="catalogue-flag">${esc(f)}</span>`).join('')}</p>`
    : '';
  return `
    <article class="catalogue-card ${item.image ? 'has-image' : ''}${surface.cls}"${surface.style} data-cid="${esc(item.id)}">
      ${surface.mark}
      ${item.image ? `
        <div class="catalogue-image catalogue-image-clickable" data-lightbox-url="${esc(item.image.url)}" data-lightbox-cap="${esc(item.name)}">
          <img src="${esc(item.image.url)}" alt="${esc(item.name)}" loading="lazy">
        </div>
      ` : '<div class="catalogue-image catalogue-image-empty"></div>'}
      <div class="catalogue-card-head">
        <div>
          <h4><span class="catalogue-name-text">${esc(item.name)}</span></h4>
          <p class="catalogue-meta">${esc(item.faction_label_display || item.faction_label)} · ${esc(date)} · ${esc(item.material || 'material unknown')}${item.status === 'discontinued' ? ' · <em>Discontinued</em>' : ''}</p>
        </div>
        <span class="catalogue-year">${esc(item.release_year || '')}</span>
      </div>
      ${item.note ? `<p class="catalogue-note">${esc(item.note)}</p>` : ''}
      ${item.resolution_notes ? `<p class="catalogue-note">${esc(item.resolution_notes)}</p>` : ''}
      ${flagHtml}
      <div class="catalogue-links" id="clinks-${esc(item.id)}">
        ${renderLinks(links)}
      </div>
      <div class="catalogue-card-actions">
        <button class="btn-secondary btn-sm cle-open-btn cfe-open-btn" data-cid="${esc(item.id)}">Edit</button>
        <button class="btn-secondary btn-sm catalogue-dup-btn" data-cid="${esc(item.id)}" data-name="${esc(item.name)}" title="Duplicate this entry">Duplicate</button>
        <button class="btn-danger btn-sm catalogue-delete-btn" data-cid="${esc(item.id)}" title="Delete this model">Delete</button>
      </div>
      <p class="catalogue-id">ID: ${esc(item.id)}</p>
    </article>
  `;
}

function renderLinks(links){
  return links.length
    ? links.map(l => `
        <a href="/#/unit/${esc(l.datasheet_id)}" class="catalogue-link">
          <b>${esc(l.datasheet_name)}</b>
          <small>${esc(l.faction_id)} · ${esc(l.role || 'role unknown')} · ${esc(l.datasheet_id)}</small>
        </a>`).join('')
    : '<span class="catalogue-unlinked">No current datasheet</span>';
}

/* ---- link editor -------------------------------------------------------- */

function openLinkEditor(cid, defaultFid){
  openFieldEditor(cid, { focusLinks: true, defaultFid });
  return;
  if(ed.cid === cid){ closeLinkEditor(); return; }
  if(ed.cid) closeLinkEditor();
  if(fed.cid) closeFieldEditor();

  const item = state.items.find(i => i.id === cid);
  if(!item) return;

  ed.cid      = cid;
  ed.factionId = defaultFid || item.faction_id || '';
  ed.selected  = (item.datasheet_links || []).map(l => ({...l}));

  const card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  if(!card) return;
  card.classList.add('is-editing');

  const factionOptions = [
    `<option value="">All factions</option>`,
    ...state.factions.map(f =>
      `<option value="${esc(f.id)}" ${f.id === ed.factionId ? 'selected' : ''}>${esc(f.display_name || f.name)}</option>`
    ),
  ].join('');

  const panel = document.createElement('div');
  panel.className = 'catalogue-link-editor';
  panel.innerHTML = `
    <div class="cle-head">Edit Datasheet Links</div>
    <div class="cle-selected" id="cle-chips"></div>
    <div class="cle-search-row">
      <select class="cle-faction-sel" id="cle-faction">${factionOptions}</select>
      <input class="cle-search-input" id="cle-search" type="search"
             placeholder="Search datasheets…" autocomplete="off">
    </div>
    <div class="cle-results" id="cle-results">
      <div class="cle-hint">Choose a faction or type to search all armies.</div>
    </div>
    <div class="cle-actions">
      <button class="btn-primary cle-save-btn">Save Links</button>
      <button class="btn-ghost  cle-cancel-btn">Cancel</button>
    </div>`;

  card.appendChild(panel);
  refreshChips();

  let searchTimer;
  panel.querySelector('#cle-faction').addEventListener('change', e => {
    ed.factionId = e.target.value;
    searchDatasheets(panel.querySelector('#cle-search').value);
  });
  panel.querySelector('#cle-search').addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchDatasheets(e.target.value), 220);
  });
  panel.querySelector('.cle-save-btn').addEventListener('click', saveLinkEdits);
  panel.querySelector('.cle-cancel-btn').addEventListener('click', closeLinkEditor);
  panel.querySelector('#cle-chips').addEventListener('click', e => {
    const btn = e.target.closest('.cle-chip-del');
    if(!btn) return;
    ed.selected = ed.selected.filter(l => l.datasheet_id !== btn.dataset.did);
    refreshChips();
    refreshResultHighlights();
  });

  // Load immediately if a faction is set
  if(ed.factionId) searchDatasheets('');
  panel.querySelector('#cle-search').focus();
}

function closeLinkEditor(){
  if(!ed.cid) return;
  const card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(ed.cid)}"]`);
  if(card){
    card.classList.remove('is-editing');
    card.querySelector('.catalogue-link-editor')?.remove();
  }
  ed.cid = null; ed.selected = []; ed.factionId = '';
}

function renderCfeLinkSection(item, defaultFid){
  ed.cid = item.id;
  ed.factionId = defaultFid || item.faction_id || '';
  ed.selected = (item.datasheet_links || []).map(l => ({...l}));

  const factionOptions = [
    `<option value="">All factions</option>`,
    ...state.factions.map(f =>
      `<option value="${esc(f.id)}" ${f.id === ed.factionId ? 'selected' : ''}>${esc(f.display_name || f.name)}</option>`
    ),
  ].join('');

  return `
    <div class="cfe-link-section" id="cfeLinkSection">
      <div class="cle-head">Datasheet Links</div>
      <div class="cle-selected" id="cle-chips"></div>
      <div class="cle-search-row">
        <select class="cle-faction-sel" id="cle-faction">${factionOptions}</select>
        <input class="cle-search-input" id="cle-search" type="search"
               placeholder="Search datasheets..." autocomplete="off">
      </div>
      <div class="cle-results" id="cle-results">
        <div class="cle-hint">Choose a faction or type to search all armies.</div>
      </div>
    </div>`;
}

function wireCfeLinkControls(panel){
  refreshChips();

  let searchTimer;
  panel.querySelector('#cle-faction')?.addEventListener('change', e => {
    ed.factionId = e.target.value;
    searchDatasheets(panel.querySelector('#cle-search')?.value || '');
  });
  panel.querySelector('#cle-search')?.addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchDatasheets(e.target.value), 220);
  });
  panel.querySelector('#cle-chips')?.addEventListener('click', e => {
    const btn = e.target.closest('.cle-chip-del');
    if(!btn) return;
    ed.selected = ed.selected.filter(l => l.datasheet_id !== btn.dataset.did);
    refreshChips();
    refreshResultHighlights();
  });

  if(ed.factionId) searchDatasheets('');
}

function refreshChips(){
  const el = document.getElementById('cle-chips');
  if(!el) return;
  if(!ed.selected.length){
    el.innerHTML = '<span class="cle-none">No datasheets selected — search below to add</span>';
    return;
  }
  el.innerHTML = ed.selected.map(l => `
    <span class="cle-chip">
      <span class="cle-chip-name">${esc(l.datasheet_name)}</span>
      <span class="cle-chip-meta">${esc(l.faction_id)}</span>
      <button class="cle-chip-del" data-did="${esc(l.datasheet_id)}" title="Remove">×</button>
    </span>`).join('');
}

async function searchDatasheets(q){
  const resultsEl = document.getElementById('cle-results');
  if(!resultsEl) return;

  const trimmed = (q || '').trim();
  if(!ed.factionId && !trimmed){
    resultsEl.innerHTML = '<div class="cle-hint">Choose a faction or type to search all armies.</div>';
    return;
  }

  resultsEl.innerHTML = '<div class="cle-hint">Searching…</div>';
  try{
    const params = new URLSearchParams();
    if(ed.factionId) params.set('faction_id', ed.factionId);
    if(trimmed)      params.set('q', trimmed);
    const results = await api(`/api/units/search?${params}`);
    renderResults(resultsEl, results);
  } catch(e){
    resultsEl.innerHTML = `<div class="cle-hint cle-err">Search failed: ${esc(e.message)}</div>`;
  }
}

function renderResults(el, results){
  if(!results || !results.length){
    el.innerHTML = '<div class="cle-hint">No datasheets found.</div>';
    return;
  }
  const selectedIds = new Set(ed.selected.map(l => l.datasheet_id));
  el.innerHTML = results.map(u => `
    <div class="cle-result-row ${selectedIds.has(u.id) ? 'is-selected' : ''}"
         data-did="${esc(u.id)}" data-name="${esc(u.name)}"
         data-fid="${esc(u.faction_id || '')}" data-role="${esc(u.role || '')}">
      <span class="cle-result-name">${esc(u.name)}</span>
      <span class="cle-result-meta">${esc(u.role || '')}${u.faction_id ? ' · '+esc(u.faction_id) : ''}</span>
      <span class="cle-result-id">${esc(u.id)}</span>
      <a class="cle-result-link" href="/#/unit/${esc(u.id)}" target="_blank" rel="noopener"
         title="View datasheet">↗</a>
      <span class="cle-result-tick">${selectedIds.has(u.id) ? '✓' : '+'}</span>
    </div>`).join('');

  el.querySelectorAll('.cle-result-row').forEach(row => {
    row.addEventListener('click', e => {
      if(e.target.closest('.cle-result-link')) return;
      toggleResultRow(row);
    });
  });
}

function toggleResultRow(row){
  const did  = row.dataset.did;
  const already = ed.selected.find(l => l.datasheet_id === did);
  if(already){
    ed.selected = ed.selected.filter(l => l.datasheet_id !== did);
  } else {
    ed.selected.push({
      datasheet_id:   did,
      datasheet_name: row.dataset.name,
      faction_id:     row.dataset.fid,
      role:           row.dataset.role,
    });
  }
  refreshChips();
  refreshResultHighlights();
}

function refreshResultHighlights(){
  const selectedIds = new Set(ed.selected.map(l => l.datasheet_id));
  document.querySelectorAll('.cle-result-row').forEach(row => {
    const sel = selectedIds.has(row.dataset.did);
    row.classList.toggle('is-selected', sel);
    const tick = row.querySelector('.cle-result-tick');
    if(tick) tick.textContent = sel ? '✓' : '+';
  });
}

async function saveLinkSelection(cid){
  if(!cid) return;
  const ids    = ed.selected.map(l => l.datasheet_id);
  const action = ids.length === 0 ? 'no_current_datasheet'
               : ids.length === 1 ? 'link_datasheet'
               :                    'link_multiple_datasheets';

  const res = await api(`/api/catalogue-review/${encodeURIComponent(cid)}/resolution`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ action, datasheet_ids: ids }),
  });
  if(!res.ok) throw new Error(res.error || 'Link save failed');
}

async function saveLinkEdits(){
  if(!ed.cid) return;
  const saveBtn = document.querySelector('.cle-save-btn');
  if(saveBtn){ saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }

  const ids    = ed.selected.map(l => l.datasheet_id);
  const action = ids.length === 0 ? 'no_current_datasheet'
               : ids.length === 1 ? 'link_datasheet'
               :                    'link_multiple_datasheets';

  try{
    const res = await api(`/api/catalogue-review/${encodeURIComponent(ed.cid)}/resolution`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action, datasheet_ids: ids }),
    });
    if(!res.ok) throw new Error(res.error || 'Save failed');

    const savedCid = ed.cid;
    closeLinkEditor();
    await load();
    document.querySelector(`.catalogue-card[data-cid="${CSS.escape(savedCid)}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  } catch(e){
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Links'; }
    const hint = document.getElementById('cle-results');
    if(hint) hint.insertAdjacentHTML('beforebegin',
      `<p class="cle-err" style="margin:6px 0">${esc(e.message)}</p>`);
  }
}

/* ---- field editor ------------------------------------------------------- */

function catalogueGoogleImagesUrl(item){
  return 'https://www.google.com/search?tbm=isch&q=' +
    encodeURIComponent(`${item.name} ${item.faction_label} Warhammer 40k miniature`);
}

function renderCfeImageSection(item){
  if(item.image){
    return `
      <div class="cfe-img-section" id="cfeImgSection">
        <div class="am-label">Image</div>
        <div class="cfe-img-preview">
          <img src="${esc(item.image.url)}?v=${Date.now()}" alt="${esc(item.name)}">
          <button class="link-btn ref-clear cfe-img-clear-btn">Remove Image</button>
        </div>
      </div>`;
  }
  return `
    <div class="cfe-img-section" id="cfeImgSection">
      <div class="am-label">Image</div>
      <a class="ref-search" href="${catalogueGoogleImagesUrl(item)}" target="_blank" rel="noopener noreferrer">Find an image ↗</a>
      <div class="ref-row">
        <input class="cfe-input" id="cfe-img-url" placeholder="Paste image address here…" autocomplete="off">
        <button class="btn-primary" id="cfe-img-save-btn">Save</button>
      </div>
      <p class="ref-alt">or <label class="link-btn ref-file">choose a file<input type="file" id="cfe-img-file" accept="image/*" hidden></label></p>
      <p class="ref-msg" id="cfe-img-msg"></p>
    </div>`;
}

function openFieldEditor(cid, opts = {}){
  if(fed.cid === cid){ closeFieldEditor(); return; }
  if(fed.cid) closeFieldEditor();
  if(ed.cid) closeLinkEditor();

  const item = state.items.find(i => i.id === cid);
  if(!item) return;
  fed.cid = cid;
  fed.focusLinks = !!opts.focusLinks;

  const card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"]`);
  if(!card) return;
  card.classList.add('is-editing');

  const matOpts = ['Plastic','Resin','Metal','Finecast','Other'].map(m =>
    `<option value="${m}"${(item.material||'Plastic')===m?' selected':''}>${m}</option>`
  ).join('');

  const armyOpts = [
    `<option value="">— None —</option>`,
    ...state.factions.map(f =>
      `<option value="${esc(f.id)}" data-canonical="${esc(f.name)}"${f.id === (item.faction_id||'') ? ' selected' : ''}>${esc(f.display_name || f.name)}</option>`
    ),
  ].join('');

  const backdrop = document.createElement('div');
  backdrop.className = 'cfe-backdrop';
  backdrop.id = 'catalogueFieldBackdrop';
  backdrop.innerHTML = `
    <div class="cfe-box" role="dialog" aria-modal="true" aria-labelledby="cfeTitle">
      <div class="am-head">
        <span class="am-title" id="cfeTitle">Edit Model</span>
        <button class="am-close cfe-close-btn" title="Close">×</button>
      </div>
      <div class="catalogue-field-editor">
        <div class="cfe-grid">
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="cfe-name">Name</label>
            <input class="cfe-input" id="cfe-name" type="text" value="${esc(item.name)}" maxlength="300" autocomplete="off">
          </div>
          <div class="cfe-field cfe-field--full">
            <label class="am-label" for="cfe-army">Army</label>
            <select class="cfe-input" id="cfe-army">${armyOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="cfe-date">Release Date</label>
            <input class="cfe-input" id="cfe-date" type="text" value="${esc(item.release_date||'')}"
                   placeholder="YYYY or YYYY-MM" maxlength="7" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label" for="cfe-material">Material</label>
            <select class="cfe-input" id="cfe-material">${matOpts}</select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="cfe-status">Status</label>
            <select class="cfe-input" id="cfe-status">
              <option value="current_or_unknown"${item.status==='current_or_unknown'?' selected':''}>Current / Unknown</option>
              <option value="discontinued"${item.status==='discontinued'?' selected':''}>Discontinued</option>
            </select>
          </div>
          <div class="cfe-field">
            <label class="am-label" for="cfe-note">Note</label>
            <input class="cfe-input" id="cfe-note" type="text" value="${esc(item.note||'')}" maxlength="500" autocomplete="off">
          </div>
          <div class="cfe-field">
            <label class="am-label" for="cfe-flags">Flags <span class="cfe-hint">(comma-separated)</span></label>
            <input class="cfe-input" id="cfe-flags" type="text" value="${esc((item.flags||[]).join(', '))}"
                   placeholder="e.g. exclusive, limited" autocomplete="off">
          </div>
        </div>
        ${renderCfeLinkSection(item, opts.defaultFid)}
        ${renderCfeImageSection(item)}
        <p class="cfe-err" id="cfe-err" hidden></p>
        <div class="am-foot">
          <button class="btn-primary cfe-save-btn">Save Changes</button>
          <button class="btn-ghost cfe-cancel-btn">Cancel</button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(backdrop);
  const editor = backdrop.querySelector('.catalogue-field-editor');
  editor.querySelector('#cfe-name').focus({ preventScroll: true });

  editor.querySelector('.cfe-save-btn').addEventListener('click', saveFieldEdits);
  editor.querySelector('.cfe-cancel-btn').addEventListener('click', closeFieldEditor);
  backdrop.querySelector('.cfe-close-btn').addEventListener('click', closeFieldEditor);
  backdrop.addEventListener('click', e => {
    if(e.target === backdrop) closeFieldEditor();
  });
  backdrop.addEventListener('keydown', e => {
    if(e.key === 'Escape') closeFieldEditor();
  });
  wireCfeImageControls(editor, cid);
  wireCfeLinkControls(editor);
  if(fed.focusLinks){
    document.getElementById('cfeLinkSection')?.scrollIntoView({ block: 'center' });
    editor.querySelector('#cle-search')?.focus({ preventScroll: true });
  }
}

function wireCfeImageControls(panel, cid){
  const saveBtn  = panel.querySelector('#cfe-img-save-btn');
  const clearBtn = panel.querySelector('.cfe-img-clear-btn');
  const fileIn   = panel.querySelector('#cfe-img-file');

  if(saveBtn) saveBtn.addEventListener('click', () => saveModelImageFromUrl(cid));
  if(clearBtn) clearBtn.addEventListener('click', () => clearModelImage(cid));
  if(fileIn) fileIn.addEventListener('change', () => {
    if(fileIn.files[0]) saveModelImageFromFile(cid, fileIn.files[0]);
  });

  const urlIn = panel.querySelector('#cfe-img-url');
  if(urlIn) urlIn.addEventListener('keydown', e => {
    if(e.key === 'Enter') saveModelImageFromUrl(cid);
  });
}

function cfeImgMsg(text, ok){
  const el = document.getElementById('cfe-img-msg');
  if(!el) return;
  el.textContent = text || '';
  el.className = 'ref-msg' + (text ? (ok ? ' ok' : ' err') : '');
}

async function saveModelImageFromUrl(cid){
  const input = document.getElementById('cfe-img-url');
  const url = (input?.value || '').trim();
  if(!url){ cfeImgMsg('Paste an image address first.', false); return; }
  cfeImgMsg('Fetching image…', true);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
    });
    if(res.ok) afterModelImageSaved(cid, res.image_url);
    else cfeImgMsg(res.error || 'Could not save that image.', false);
  } catch(e){ cfeImgMsg('Could not save that image.', false); }
}

async function saveModelImageFromFile(cid, fileObj){
  cfeImgMsg('Saving image…', true);
  const fd = new FormData();
  fd.append('file', fileObj);
  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {
      method: 'POST', body: fd,
    });
    if(res.ok) afterModelImageSaved(cid, res.image_url);
    else cfeImgMsg(res.error || 'Could not save.', false);
  } catch(e){ cfeImgMsg('Could not save.', false); }
}

function afterModelImageSaved(cid, imageUrl){
  const item = state.items.find(i => i.id === cid);
  if(item){
    item.image = { url: imageUrl, caption: '', source: 'user', lexicanum_page: '', file_page_url: '' };
  }
  // Only update the image section if it belongs to this card's editor
  if(fed.cid === cid){
    const section = document.getElementById('cfeImgSection');
    if(section && item) section.outerHTML = renderCfeImageSection(item);
    const newSection = document.getElementById('cfeImgSection');
    if(newSection){
      const panel = newSection.closest('.catalogue-field-editor');
      if(panel) wireCfeImageControls(panel, cid);
    }
  }
  const cardImg = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image img`);
  if(cardImg) cardImg.src = `${imageUrl}?v=${Date.now()}`;
  const emptyImg = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image-empty`);
  if(emptyImg){
    emptyImg.outerHTML = `<div class="catalogue-image catalogue-image-clickable" data-lightbox-url="${esc(imageUrl)}?v=${Date.now()}" data-lightbox-cap=""><img src="${esc(imageUrl)}?v=${Date.now()}" alt="" loading="lazy"></div>`;
  }
}

async function clearModelImage(cid){
  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}/image`, {method:'DELETE'});
    if(!r.ok){
      const json = await r.json().catch(()=>({}));
      cfeImgMsg(json.error || `Server error (${r.status}).`, false);
      return;
    }
    const item = state.items.find(i => i.id === cid);
    if(item) item.image = null;
    if(fed.cid === cid){
      const section = document.getElementById('cfeImgSection');
      if(section && item) section.outerHTML = renderCfeImageSection(item);
      const newSection = document.getElementById('cfeImgSection');
      if(newSection){
        const panel = newSection.closest('.catalogue-field-editor');
        if(panel) wireCfeImageControls(panel, cid);
      }
    }
    const cardImg = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(cid)}"] .catalogue-image`);
    if(cardImg) cardImg.outerHTML = '<div class="catalogue-image catalogue-image-empty"></div>';
  } catch(e){ cfeImgMsg('Could not remove image.', false); }
}

function closeFieldEditor(){
  if(!fed.cid) return;
  const card = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(fed.cid)}"]`);
  if(card) card.classList.remove('is-editing');
  document.getElementById('catalogueFieldBackdrop')?.remove();
  fed.cid = null;
  fed.focusLinks = false;
  ed.cid = null; ed.selected = []; ed.factionId = '';
}

async function saveFieldEdits(){
  if(!fed.cid) return;
  const cid = fed.cid;
  const saveBtn = document.querySelector('.cfe-save-btn');
  const errEl   = document.getElementById('cfe-err');
  if(saveBtn){ saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  if(errEl) errEl.hidden = true;

  const name = document.getElementById('cfe-name').value.trim();
  if(!name){
    showCfeErr('Name cannot be empty.');
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    return;
  }
  const release_date = document.getElementById('cfe-date').value.trim();
  if(release_date && !/^\d{4}(-\d{2})?$/.test(release_date)){
    showCfeErr('Release date must be YYYY or YYYY-MM (e.g. 2024-06).');
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    return;
  }
  const faction_id = document.getElementById('cfe-army').value;

  const payload = {
    name,
    release_date,
    material:   document.getElementById('cfe-material').value,
    status:     document.getElementById('cfe-status').value,
    note:       document.getElementById('cfe-note').value.trim(),
    flags:      document.getElementById('cfe-flags').value.split(',').map(f => f.trim()).filter(Boolean),
    faction_id,
  };

  try{
    const res = await api(`/api/model-catalogue/${encodeURIComponent(cid)}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if(!res.ok) throw new Error(res.error || 'Save failed');
    await saveLinkSelection(cid);

    const savedCid = cid;
    closeFieldEditor();
    await load();
    document.querySelector(`.catalogue-card[data-cid="${CSS.escape(savedCid)}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  } catch(e){
    showCfeErr(e.message);
    if(saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
  }
}

function showCfeErr(msg){
  const el = document.getElementById('cfe-err');
  if(el){ el.textContent = msg; el.hidden = false; }
}

/* ---- delete model ------------------------------------------------------- */

async function deleteModel(cid){
  const item = state.items.find(i => i.id === cid);
  if(!item) return;
  if(!confirm(`Delete "${item.name}"?\n\nThis cannot be undone.`)) return;

  try{
    const r = await fetch(`/api/model-catalogue/${encodeURIComponent(cid)}`, { method: 'DELETE' });
    const json = await r.json();
    if(!r.ok) throw new Error(json.error || `HTTP ${r.status}`);
    state.items = state.items.filter(i => i.id !== cid);
    render();
  } catch(e){
    alert(`Could not delete: ${e.message}`);
  }
}

/* ---- add model modal ---------------------------------------------------- */

const addModal = {
  backdrop: document.getElementById('addModelBackdrop'),
  nameEl:   document.getElementById('amName'),
  fLabel:   document.getElementById('amFactionLabel'),
  fId:      document.getElementById('amFactionId'),
  date:     document.getElementById('amReleaseDate'),
  material: document.getElementById('amMaterial'),
  status:   document.getElementById('amStatus'),
  note:     document.getElementById('amNote'),
  err:      document.getElementById('amErr'),
  saveBtn:  document.getElementById('amSave'),
};

function openAddModal(){
  // Populate faction select from current state. Show the user-facing
  // display_name in the option text, but stash the canonical name on a data
  // attribute - the saved faction_label MUST stay canonical (it's the
  // catalogue's grouping/join key against model_catalogue_manual.json).
  addModal.fLabel.innerHTML = [
    '<option value="">— None —</option>',
    ...state.factions.map(f =>
      `<option value="${esc(f.id)}" data-canonical="${esc(f.name)}">${esc(f.display_name || f.name)}</option>`
    ),
  ].join('');

  // Reset fields
  addModal.fLabel.value = '';
  addModal.fId.value = '';
  ['amName','amReleaseDate','amNote'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('amMaterial').value = 'Plastic';
  document.getElementById('amStatus').value = 'current_or_unknown';
  hideAddErr();

  addModal.backdrop.hidden = false;
  addModal.nameEl.focus();
}

function closeAddModal(){
  addModal.backdrop.hidden = true;
}

function showAddErr(msg){
  addModal.err.textContent = msg;
  addModal.err.hidden = false;
}

function hideAddErr(){
  addModal.err.hidden = true;
  addModal.err.textContent = '';
}

// Auto-fill faction ID when faction is selected
addModal.fLabel.addEventListener('change', () => {
  addModal.fId.value = addModal.fLabel.value;
});

async function saveNewModel(){
  hideAddErr();
  const name = addModal.nameEl.value.trim();
  if(!name){ showAddErr('Model name is required.'); addModal.nameEl.focus(); return; }

  const dateVal = addModal.date.value.trim();
  if(dateVal && !/^\d{4}(-\d{2})?$/.test(dateVal)){
    showAddErr('Release date must be YYYY or YYYY-MM (e.g. 2024 or 2024-06).');
    addModal.date.focus();
    return;
  }

  const selectedOpt = addModal.fLabel.options[addModal.fLabel.selectedIndex];
  const factionLabel = (selectedOpt && addModal.fLabel.value)
    ? (selectedOpt.dataset.canonical || selectedOpt.textContent)
    : '';

  addModal.saveBtn.disabled = true;
  addModal.saveBtn.textContent = 'Saving…';

  try{
    const r = await fetch('/api/model-catalogue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name,
        faction_label: factionLabel,
        faction_id:    addModal.fId.value.trim(),
        release_date:  dateVal,
        material:      addModal.material.value,
        status:        addModal.status.value,
        note:          addModal.note.value.trim(),
      }),
    });
    const json = await r.json();
    if(!r.ok) throw new Error(json.error || `HTTP ${r.status}`);
    closeAddModal();
    await load();  // Reload catalogue so the new card appears
  } catch(e){
    showAddErr(e.message);
  } finally{
    addModal.saveBtn.disabled = false;
    addModal.saveBtn.textContent = 'Save Model';
  }
}

document.getElementById('addModelBtn').addEventListener('click', openAddModal);
document.getElementById('addModelClose').addEventListener('click', closeAddModal);
document.getElementById('amCancel').addEventListener('click', closeAddModal);
document.getElementById('amSave').addEventListener('click', saveNewModel);
addModal.backdrop.addEventListener('click', e => {
  if(e.target === addModal.backdrop) closeAddModal();
});
document.addEventListener('keydown', e => {
  if(e.key === 'Escape' && !addModal.backdrop.hidden) closeAddModal();
});

/* ---- toolbar events ----------------------------------------------------- */

document.getElementById('catalogueSearch').addEventListener('input', e => {
  state.q = e.target.value;
  render();
});
document.getElementById('catalogueArmy').addEventListener('change', e => {
  state.army = e.target.value;
  render();
});
document.getElementById('catalogueLinkFilter').addEventListener('change', e => {
  state.linkFilter = e.target.value;
  render();
});

// Event delegation for card buttons (dynamically rendered)
document.getElementById('catalogueList').addEventListener('click', e => {
  const imgEl = e.target.closest('.catalogue-image-clickable');
  if(imgEl){ openLightbox(imgEl.dataset.lightboxUrl, imgEl.dataset.lightboxCap); return; }

  const delBtn = e.target.closest('.catalogue-delete-btn');
  if(delBtn){ e.preventDefault(); deleteModel(delBtn.dataset.cid); return; }

  const editBtn = e.target.closest('.cfe-open-btn');
  if(editBtn){ e.preventDefault(); openFieldEditor(editBtn.dataset.cid); return; }

  const dupBtn = e.target.closest('.catalogue-dup-btn');
  if(dupBtn){ e.preventDefault(); duplicateModel(dupBtn.dataset.cid, dupBtn.dataset.name); return; }

  const linksBtn = e.target.closest('.cle-open-btn');
  if(!linksBtn) return;
  e.preventDefault();
  openLinkEditor(linksBtn.dataset.cid, linksBtn.dataset.fid);
});

/* ---- duplicate ------------------------------------------------------------ */

async function duplicateModel(cid, originalName){
  try {
    const res = await api(`/api/model-catalogue/${cid}/duplicate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name: originalName }),
    });
    state.items.push(res.record);
    render();
    const newId = res.record.id;
    ensureRendered(newId);
    const newCard = document.querySelector(`.catalogue-card[data-cid="${CSS.escape(newId)}"]`);
    if(newCard) newCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    openFieldEditor(newId);
  } catch(err) {
    alert('Duplicate failed: ' + err.message);
  }
}

/* ---- init --------------------------------------------------------------- */

setBreadcrumb([
  {label:'My Armies', href:'/'},
  {label:'Model Catalogue'},
]);
refreshLedger();

initLightbox();

load().catch(err => {
  document.getElementById('catalogueList').innerHTML =
    `<div class="review-empty">Could not load catalogue data: ${esc(err.message)}</div>`;
});
