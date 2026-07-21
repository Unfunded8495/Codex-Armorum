import { esc, api, jsStr, intOr } from './utils.js';
import { clearFactionCache, buildUnitTiles } from './home.js';
import { setActiveNav, setBreadcrumb, updateLedger } from './header.js';
import { rlThemeMode, rlThemeToggleHtml, rlWireThemeToggle } from './rl-theme.js';

const view       = document.getElementById('view');

let boxSetCache   = null;
let boxEditor     = null;
let purchEditMode = false;
let _lastPurchases= [];
let activeTab     = 'purchases';
let purchViewMode = 'grid';
let purchSortMode = 'name';
let purchArmyFilter = '';
let selectedPurchaseId = null;
let boxCatalogueLoading = null;
let pageFactions = [];
let pageFactionNames = {};
const CARD_CHUNK_SIZE = 12;

// ══════════════════════════════════════════════════════════════
//  MAIN ENTRY
// ══════════════════════════════════════════════════════════════

export async function showPurchases(){
  selectedPurchaseId = null;
  setActiveNav('purchases');
  setBreadcrumb([
    {label:'My Armies', href:'#/'},
    {label:'Purchases'},
  ]);
  document.body.classList.add('rl-spa', 'purchases-ledger');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  view.innerHTML = _stripHtml() + _shellHtml(
    `<div class="rl-load"><div class="rl-load-bar"></div>` +
    `<div class="rl-load-note">Checking the armoury…</div></div>`);
  rlWireThemeToggle(document);
  let boxes, data, factions;
  try{
    data = await api('/api/purchases/page-data');
    boxes = boxSetCache || data.box_options || data.boxes || [];
    factions = data.factions || [];
    pageFactions = factions;
    pageFactionNames = data.faction_names || {};
  }catch(e){
    view.innerHTML = _stripHtml() + _shellHtml(
      `<div class="rl-error">Failed to load purchases.<small>${esc(e.message)}</small></div>`);
    rlWireThemeToggle(document);
    return;
  }

  _lastPurchases = data.purchases || [];
  if(purchArmyFilter && !_lastPurchases.some(p=>_purchaseArmyIds(p).includes(purchArmyFilter))){
    purchArmyFilter = '';
  }
  if(data.summary) updateLedger(data.summary);

  view.innerHTML = _stripHtml(_lastPurchases.length, boxes.length) + _shellHtml(_buildPage(boxes, data, factions));
  _wireTabs();
  _wireCatalogue(boxes);
  _wirePurchEditToggle();
  _wirePurchControls();
  _schedulePurchaseCards(_purchaseViewItems());
  if(activeTab === 'catalogue') document.getElementById('catSearch')?.dispatchEvent(new Event('input'));
  wireBoxEditor();
  rlWireThemeToggle(document);
}

/* ---- paper shell + reading strip (shared skin: spa-shell.css) --------
   The four tabs live as strip chips; each also carries the legacy
   .al-tab class + data-tab so the existing tab wiring works as-is. */
function _shellHtml(inner){
  return `<div class="rl-shell"><div class="rl-wrap">${inner}</div></div>`;
}
function _stripHtml(purchCount = null, boxCount = null){
  const chip = (tab, label, count) =>
    `<button type="button" class="rl-chip al-tab${activeTab===tab?' is-active':''}" data-tab="${tab}">` +
    `${label}${count!==null && count!==undefined ? `<b>${count}</b>` : ''}</button>`;
  const chips = (purchCount === null && boxCount === null) ? '' :
    chip('purchases', 'Purchases', purchCount) +
    chip('catalogue', 'Box Catalogue', boxCount) +
    chip('editor', 'Define Box', null) +
    chip('summary', 'Model Summary', null);
  return `
    <nav class="rl-strip" aria-label="Armoury ledger">
      <span class="rl-strip-label">The Armoury Ledger</span>
      ${chips}
      <span class="rl-strip-spacer"></span>
      ${rlThemeToggleHtml()}
    </nav>`;
}

// ══════════════════════════════════════════════════════════════
//  PAGE SCAFFOLD
// ══════════════════════════════════════════════════════════════

function _buildPage(boxes, data, factions){
  const purchases = data.purchases || [];
  const visiblePurchases = _filterPurchasesByArmy(purchases, purchArmyFilter);
  return `
  <div class="al-header">
    <div>
      <h2 class="view-title">Armoury Ledger</h2>
      <p class="view-sub">Kit acquisitions and physical model inventory</p>
    </div>
    <div class="al-stats">
      <div class="al-stat"><b>${data.total_bought||0}</b><span>Acquired</span></div>
      <div class="al-stat-div"></div>
      <div class="al-stat is-accent"><b>${data.total_unlogged||0}</b><span>Unlogged</span></div>
      <div class="al-stat-div"></div>
      <div class="al-stat"><b>${purchases.length}</b><span>Purchases</span></div>
    </div>
  </div>

  <!-- ── PURCHASES TAB ── -->
  <div class="al-panel" id="tab-purchases"${activeTab!=='purchases'?' hidden':''}>
    <div id="purchGridWrap">
      ${_renderQuickAdd(boxes)}
      <div class="al-plist-head">
        <span class="al-plist-count" id="purchCount">${_purchaseCountLabel(visiblePurchases.length, purchases.length)}</span>
        <div class="al-plist-controls">
          <select id="purchArmy" class="al-sort-sel al-army-sel" aria-label="Filter purchases by army" title="Filter purchases by army">
            <option value="">All armies</option>
            ${_purchaseArmyOptions(purchases).map(f=>`<option value="${esc(f.id)}"${purchArmyFilter===f.id?' selected':''}>${esc(f.name)}</option>`).join('')}
          </select>
          <select id="purchSort" class="al-sort-sel">
            <option value="name"${purchSortMode==='name'?' selected':''}>A–Z</option>
            <option value="release"${purchSortMode==='release'?' selected':''}>Release date</option>
          </select>
          <div class="al-view-toggle">
            <button class="al-view-btn${purchViewMode==='grid'?' is-active':''}" data-view="grid" title="Grid view">⊞</button>
            <button class="al-view-btn${purchViewMode==='list'?' is-active':''}" data-view="list" title="List view">☰</button>
          </div>
          <button class="al-edit-toggle${purchEditMode?' is-active':''}" id="purchEditToggle">${purchEditMode?'Done':'Edit'}</button>
        </div>
      </div>
      <div id="purchaseList" class="al-plist${purchEditMode?' is-editing':''}">${_renderPurchaseList(visiblePurchases)}</div>
    </div>
    <div id="purchDetailWrap" hidden></div>
  </div>

  <!-- ── CATALOGUE TAB ── -->
  <div class="al-panel" id="tab-catalogue"${activeTab!=='catalogue'?' hidden':''}>
    <div class="al-cat-toolbar">
      <input id="catSearch" class="al-cat-search" placeholder="Search box sets…" autocomplete="off">
      <select id="catFaction" class="al-cat-faction">
        <option value="">All armies</option>
        ${[...factions].sort((a,b)=>(a.display_name||a.name).localeCompare(b.display_name||b.name))
          .map(f=>`<option value="${esc(f.id)}">${esc(f.display_name||f.name)}</option>`).join('')}
      </select>
      <select id="catSort" class="al-sort-sel">
        <option value="name">A–Z</option>
        <option value="release">Release date</option>
      </select>
      <span class="al-cat-count" id="catCount">${boxes.length} box${boxes.length===1?'':'es'}</span>
    </div>
    <div id="catGrid" class="al-cat-grid">${boxSetCache ? _renderCatGrid(boxSetCache) : _catalogueLoadingNote()}</div>
  </div>

  <!-- ── EDITOR TAB ── -->
  <div class="al-panel" id="tab-editor"${activeTab!=='editor'?' hidden':''}>
    <div id="boxEditor">${renderBoxEditor(null, factions)}</div>
  </div>

  <!-- ── SUMMARY TAB ── -->
  <div class="al-panel" id="tab-summary"${activeTab!=='summary'?' hidden':''}>
    ${_renderModelSummary(purchases, factions)}
  </div>
  `;
}

// ══════════════════════════════════════════════════════════════
//  QUICK ADD
// ══════════════════════════════════════════════════════════════

function _renderQuickAdd(boxes){
  if(!boxes.length) return `<div class="al-qadd-empty">No boxes in catalogue yet — define one in the <b>Define Box</b> tab first.</div>`;
  const first = boxes[0];
  return `
  <div class="al-qadd">
    <div class="al-qadd-label">Record a purchase</div>
    <div class="al-qadd-row">
      <select id="purchaseBox" onchange="renderPurchasePreview()">
        <option value="">— select a box —</option>
        ${boxes.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('')}
      </select>
      <div class="al-qty-wrap">
        <span class="al-qty-x">&times;</span>
        <input id="purchaseQty" class="ff-qty" type="number" min="1" max="200" value="1">
      </div>
      <input id="purchaseNotes" class="ff-input al-notes-input" placeholder="Notes (optional)" autocomplete="off">
      <button class="btn-primary al-qadd-btn" onclick="submitPurchase()">Add Purchase</button>
    </div>
    <div id="purchasePreview"></div>
  </div>
  `;
}

function _contentYear(item){
  return item.release_year || item.catalogue_model?.release_year || null;
}

function _contentLabel(item){
  return item.summary_label || item.catalogue_label || item.catalogue_model?.name || item.display_name || item.name || 'Unknown miniature';
}

function _summarizedContents(contents){
  const groups = {};
  (contents || []).forEach(item => {
    if(item.multikit_group) (groups[item.multikit_group] = groups[item.multikit_group] || []).push(item);
  });
  const placed = new Set();
  const rows = [];
  (contents || []).forEach(item => {
    const gid = item.multikit_group;
    if(!gid || !groups[gid] || groups[gid].length < 2){
      rows.push(item);
      return;
    }
    if(placed.has(gid)) return;
    placed.add(gid);
    const alternatives = groups[gid];
    rows.push({
      ...alternatives[0],
      datasheet_count: alternatives[0].physical_miniatures || alternatives[0].datasheet_count,
      summary_label: `either ${alternatives.map(i => _contentLabel(i)).join(' or ')}`,
      release_year: null,
      catalogue_model: null,
    });
  });
  return rows;
}

function _renderMiniRow(item){
  const label = _contentLabel(item);
  const year  = _contentYear(item);
  const hasYear = year && label.includes(String(year));
  return `<div class="al-ccard-unit">
    <span class="al-cu-qty">${item.datasheet_count}&times;</span>
    <span class="al-cu-name">${esc(label)}</span>
    ${year && !hasYear ? `<span class="al-cu-year">${year}</span>` : ''}
  </div>`;
}

function _renderMiniList(contents, limit=5){
  const rows = _summarizedContents(contents || []);
  if(!rows.length) return `<div class="al-ccard-unit muted">Box contents unavailable</div>`;
  const shown = rows.slice(0, limit);
  return `
    ${shown.map(_renderMiniRow).join('')}
    ${rows.length>limit?`<div class="al-ccard-unit muted">&hellip;and ${rows.length-limit} more</div>`:''}
  `;
}

function _boxBadges(box, purchase=null){
  return `
    ${purchase?`<span class="al-cbadge bought">&times; ${purchase.quantity}</span>`:''}
    ${box.faction_id?`<span class="al-cbadge faction">${esc(_factionName(box.faction_id))}</span>`:'<span class="al-cbadge mixed">Mixed</span>'}
    <span class="al-cbadge ${box.source==='local'?'local':'gw'}">${box.source==='local'?'Custom':'GW'}</span>
  `;
}

function _factionData(fid){
  return pageFactions.find(f=>f.id===fid) || null;
}

function _factionName(fid){
  const f = _factionData(fid);
  return f?.display_name || f?.name || pageFactionNames[fid] || fid;
}

function _boxSurface(box){
  const f = box?.faction_id ? _factionData(box.faction_id) : null;
  if(!f) return { cls:'', style:'', mark:'' };
  const mark = f.icon_url
    ? `<div class="faction-bg-mark al-card-mark" aria-hidden="true"><img src="${esc(f.icon_url)}" alt="" loading="lazy"></div>`
    : `<div class="faction-bg-mark al-card-mark" aria-hidden="true"><span class="faction-bg-letter">${esc((f.display_name||f.name||box.faction_id)?.[0]||'?')}</span></div>`;
  return {
    cls: ' faction-surface al-faction-card',
    style: ` style="--cardarmy:${f.primary};--cardaccent:${f.accent};--cardglow:${f.accent}"`,
    mark,
  };
}

function _renderBoxCard(box, opts={}){
  const purchase = opts.purchase || null;
  const boxId = box.box_set_id || box.id;
  const surface = _boxSurface(box);
  const miniLimit = opts.miniLimit ?? 5;
  const actions = purchase
    ? `<button class="al-cedit" onclick='switchToEditor(${jsStr(boxId)})'>Edit</button>
       <button class="al-del-btn al-pcard-del" onclick='deletePurchase(${jsStr(purchase.id)})' title="Remove this purchase record">x</button>`
    : `<button class="al-cbuy" onclick='quickPurchase(${jsStr(boxId)})'>+ Log</button>
       <button class="al-cedit" onclick='switchToEditor(${jsStr(boxId)})'>Edit</button>`;
  const note = purchase?.notes ? `<div class="al-ccard-note">${esc(purchase.notes)}</div>` : '';
  return `
  <div class="al-ccard${purchase?' al-pcard':''}${surface.cls}"${surface.style} data-box-id="${esc(boxId)}">
    ${surface.mark}
    <div class="al-ccard-img-wrap">
      <img class="al-ccard-img" src="/api/box-sets/${esc(boxId)}/image" alt="${esc(box.name)}" loading="lazy">
    </div>
    <div class="al-ccard-top">
      <div class="al-ccard-name">${esc(box.name)}</div>
      <div class="al-ccard-badges">${_boxBadges(box, purchase)}</div>
    </div>
    <div class="al-ccard-units">${_renderMiniList(box.contents || [], miniLimit)}</div>
    ${note}
    <div class="al-ccard-foot">
      <span class="al-ccard-stat">${box.total_physical_miniatures} physical &middot; ${box.total_datasheet_models} tracked</span>
      <div class="al-ccard-actions">${actions}</div>
    </div>
  </div>`;
}

function _renderBoxPreview(box){
  if(!box) return '';
  return `
  <div class="al-bprev">
    <div class="al-bprev-units">
      ${box.contents.slice(0,8).map(i=>`<span class="al-bprev-unit"><b>${i.datasheet_count}&times;</b> ${esc(_contentLabel(i))}</span>`).join('')}
      ${box.contents.length>8?`<span class="al-bprev-unit muted">+${box.contents.length-8} more</span>`:''}
    </div>
    <div class="al-bprev-foot">
      <span>${box.total_physical_miniatures} physical &middot; ${box.total_datasheet_models} tracked</span>
      <button class="btn-ghost" onclick='switchToEditor(${jsStr(box.id)})'>Edit box</button>
    </div>
  </div>
  `;
}

export async function renderPurchasePreview(){
  const id  = document.getElementById('purchaseBox')?.value || '';
  if(id && !boxSetCache) await _ensureBoxCatalogueLoaded();
  const box = (boxSetCache||[]).find(b=>b.id===id);
  const el  = document.getElementById('purchasePreview');
  if(el) el.innerHTML = box ? _renderBoxPreview(box) : '';
}

// ══════════════════════════════════════════════════════════════
//  PURCHASE LIST
// ══════════════════════════════════════════════════════════════

function _sortPurchases(purchases, sort){
  const list = [...purchases];
  if(sort === 'release'){
    list.sort((a,b)=>{
      const da = a.release_date||'', db = b.release_date||'';
      if(da<db) return -1; if(da>db) return 1;
      return (a.box_name||'').localeCompare(b.box_name||'');
    });
  } else {
    list.sort((a,b)=>(a.box_name||'').localeCompare(b.box_name||''));
  }
  return list;
}

// A mixed box belongs to every army represented by its contents. For older or
// datasheet-less purchase records, fall back to the box-level army.
function _purchaseArmyIds(purchase){
  const contentIds = [...new Set((purchase.contents || []).map(i=>i.faction_id).filter(Boolean))];
  if(contentIds.length) return contentIds;
  return purchase.faction_id ? [purchase.faction_id] : [];
}

function _purchaseArmyOptions(purchases){
  const ids = new Set();
  purchases.forEach(p=>_purchaseArmyIds(p).forEach(fid=>ids.add(fid)));
  return [...ids]
    .map(id=>({id, name:_factionName(id)}))
    .sort((a,b)=>a.name.localeCompare(b.name));
}

function _filterPurchasesByArmy(purchases, factionId){
  if(!factionId) return purchases;
  return purchases.filter(p=>_purchaseArmyIds(p).includes(factionId));
}

function _purchaseViewItems(){
  return _sortPurchases(_filterPurchasesByArmy(_lastPurchases, purchArmyFilter), purchSortMode);
}

function _purchaseCountLabel(visible, total){
  if(visible === total) return `${total} record${total===1?'':'s'}`;
  return `${visible} of ${total} records`;
}

function _renderModelSummary(purchases, factions){
  if(!purchases.length) return `<div class="al-sum-empty">No purchases recorded yet.</div>`;

  const factionName = {};
  factions.forEach(f => { factionName[f.id] = f.display_name || f.name; });

  const byFaction = {};
  for(const p of purchases){
    for(const item of _modelSummaryRowsForPurchase(p)){
      const fid = item.faction_id || p.faction_id || '__mixed__';
      const key = item.key || item.name;
      if(!byFaction[fid]) byFaction[fid] = {};
      if(!byFaction[fid][key]){
        byFaction[fid][key] = {name: item.name, count: 0, buildOptions: 0};
      }
      byFaction[fid][key].count += item.physicalCount;
      byFaction[fid][key].buildOptions += item.buildOptions;
    }
  }

  const fids = Object.keys(byFaction).sort((a, b) => {
    if(a === '__mixed__') return 1;
    if(b === '__mixed__') return -1;
    return (factionName[a] || a).localeCompare(factionName[b] || b);
  });

  if(!fids.length) return `<div class="al-sum-empty">No model data found in purchases.</div>`;

  return `<div class="al-sum-grid">${fids.map(fid => {
    const fname = fid === '__mixed__' ? 'Mixed / Multi-faction' : (factionName[fid] || fid);
    const models = Object.values(byFaction[fid]).sort((a, b) => a.name.localeCompare(b.name));
    const totalMinis = models.reduce((s, m) => s + m.count, 0);
    const totalOptions = models.reduce((s, m) => s + m.buildOptions, 0);
    const totalLabel = totalOptions > totalMinis
      ? `${totalMinis} physical / ${totalOptions} build options`
      : `${totalMinis} mini${totalMinis===1?'':'s'}`;
    return `
    <div class="al-sum-faction">
      <div class="al-sum-fhead">
        <span class="al-sum-fname">${esc(fname)}</span>
        <span class="al-sum-ftotal">${totalLabel}</span>
      </div>
      <table class="al-sum-table">
        <tbody>
          ${models.map(m=>`
          <tr>
            <td class="al-sum-mname">${esc(m.name)}</td>
            <td class="al-sum-mcount">
              &times;${m.count}
              ${m.buildOptions > m.count ? `<small>${m.buildOptions} build options</small>` : ''}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
  }).join('')}</div>`;
}

function _modelSummaryRowsForPurchase(purchase){
  const contents = purchase.contents || [];
  const groups = {};
  contents.forEach(item => {
    if(item.multikit_group){
      (groups[item.multikit_group] = groups[item.multikit_group] || []).push(item);
    }
  });

  const placedGroups = new Set();
  const rows = [];
  contents.forEach(item => {
    const groupId = item.multikit_group;
    const group = groupId ? groups[groupId] : null;
    if(!group || group.length < 2){
      rows.push(_modelSummaryStandaloneRow(item));
      return;
    }
    if(placedGroups.has(groupId)) return;
    placedGroups.add(groupId);
    rows.push(_modelSummaryMultikitRow(purchase, groupId, group));
  });
  return rows;
}

function _modelSummaryStandaloneRow(item){
  const count = item.physical_miniatures || item.datasheet_count || 1;
  const name = _contentLabel(item);
  return {
    faction_id: item.faction_id || '__mixed__',
    key: `unit:${item.faction_id || ''}:${item.datasheet_id || name}`,
    name,
    physicalCount: count,
    buildOptions: count,
  };
}

function _modelSummaryMultikitRow(purchase, groupId, group){
  const factions = [...new Set(group.map(i => i.faction_id || purchase.faction_id || '').filter(Boolean))];
  const factionId = factions.length === 1 ? factions[0] : '__mixed__';
  const labels = group.map(i => _contentLabel(i));
  const physicalCount = group[0]?.physical_miniatures || group[0]?.datasheet_count || 1;
  const buildOptions = group.reduce((sum, item) => sum + (item.physical_miniatures || item.datasheet_count || 1), 0);
  return {
    faction_id: factionId,
    key: `mk:${factionId}:${labels.join('|')}`,
    name: `Either ${labels.join(' or ')}`,
    physicalCount,
    buildOptions,
  };
}

function _sortBoxes(boxes, sort){
  const list = [...boxes];
  if(sort === 'release'){
    list.sort((a,b)=>{
      const da = a.release_date||'', db = b.release_date||'';
      if(da<db) return -1; if(da>db) return 1;
      return (a.name||'').localeCompare(b.name||'');
    });
  } else {
    list.sort((a,b)=>(a.name||'').localeCompare(b.name||''));
  }
  return list;
}

function _renderPurchaseList(purchases){
  const sorted = _sortPurchases(purchases, purchSortMode);
  if(!sorted.length){
    const message = purchArmyFilter
      ? 'No purchases match this army.'
      : 'No purchases recorded yet. Use the form above to log a box.';
    return `<div class="al-plist-empty">${message}</div>`;
  }
  if(purchViewMode === 'list') return _renderPurchaseListView(sorted);
  return `<div id="purchaseCards" class="al-ptile-grid">${sorted.slice(0, CARD_CHUNK_SIZE).map(p=>_renderPurchaseTile(p)).join('')}</div>`;
}

function _renderPurchaseListView(purchases){
  return `<table class="al-plist-table">
    <thead><tr>
      <th>Name</th><th>Qty</th><th>Army</th><th>Release</th><th>Notes</th><th></th>
    </tr></thead>
    <tbody>
      ${purchases.map(p=>`<tr>
        <td class="al-plt-name">${esc(p.box_name)}</td>
        <td class="al-plt-qty">&times;${p.quantity}</td>
        <td class="al-plt-faction">${p.faction_id?esc(p.faction_id):'<span class="al-plt-dim">—</span>'}</td>
        <td class="al-plt-release">${p.release_date?esc(p.release_date.slice(0,7)):'<span class="al-plt-dim">—</span>'}</td>
        <td class="al-plt-notes">${p.notes?esc(p.notes):'<span class="al-plt-dim">—</span>'}</td>
        <td class="al-plt-actions">
          <button class="al-cedit" onclick='switchToEditor(${jsStr(p.box_set_id)})'>Edit</button>
          <button class="al-del-btn al-pcard-del" onclick='deletePurchase(${jsStr(p.id)})' title="Remove this purchase record">&times;</button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

// ── Purchase tile (grid view) ──────────────────────────────────
// Mimics the army-list tiles: box art forward, minimal text. Clicking a
// tile opens the box detail where its miniatures are grouped together.
function _renderPurchaseTile(p){
  const surface = _boxSurface({faction_id: p.faction_id});
  const minis   = p.total_physical_miniatures || 0;
  const faction = p.faction_id ? _factionName(p.faction_id) : 'Mixed';
  return `
  <div class="al-ptile${surface.cls}"${surface.style} data-purchase-id="${esc(p.id)}" onclick='openPurchaseDetail(${jsStr(p.id)})'>
    ${surface.mark}
    <button class="al-ptile-del" onclick='event.stopPropagation();deletePurchase(${jsStr(p.id)})' title="Remove this purchase record">✕</button>
    <div class="al-ptile-img-wrap">
      <img class="al-ptile-img" src="/api/box-sets/${esc(p.box_set_id)}/image" alt="${esc(p.box_name)}" loading="lazy">
      ${p.quantity>1?`<span class="al-ptile-qty">&times;${p.quantity}</span>`:''}
    </div>
    <div class="al-ptile-body">
      <div class="al-ptile-name">${esc(p.box_name)}</div>
      <div class="al-ptile-meta">${esc(faction)} &middot; ${minis} mini${minis===1?'':'s'}</div>
    </div>
  </div>`;
}

function _schedulePurchaseCards(purchases){
  const grid = document.getElementById('purchaseCards');
  if(!grid || purchases.length <= CARD_CHUNK_SIZE) return;
  let idx = CARD_CHUNK_SIZE;
  const append = () => {
    const batch = purchases.slice(idx, idx + CARD_CHUNK_SIZE);
    if(batch.length) grid.insertAdjacentHTML('beforeend', batch.map(_renderPurchaseTile).join(''));
    idx += CARD_CHUNK_SIZE;
    if(idx < purchases.length) _defer(append);
  };
  _defer(append);
}

// ── Purchase detail (box contents as collection tiles + list summary) ──

function _factionMarkInner(f){
  return f?.icon_url
    ? `<img src="${esc(f.icon_url)}" alt="" loading="lazy">`
    : `<span class="faction-bg-letter">${esc((f?.name||'?')[0]||'?')}</span>`;
}

// Pull the live collection tiles (same cards as the faction page, with paint
// progress + /mini links) for just the datasheets contained in this box.
async function _loadPurchaseDetailCards(p){
  const host = document.getElementById('pdCards');
  if(!host) return;
  const boxDids    = new Set((p.contents || []).map(i => i.datasheet_id));
  const factionIds = [...new Set((p.contents || []).map(i => i.faction_id || p.faction_id).filter(Boolean))];
  if(!factionIds.length){ host.innerHTML = `<p class="empty-note">No army data for this box.</p>`; return; }
  try{
    const perFaction = await Promise.all(factionIds.map(async fid => {
      const f = _factionData(fid);
      const [minis, unitPayload] = await Promise.all([
        api(`/api/collection?faction_id=${encodeURIComponent(fid)}`),
        api(`/api/factions/${encodeURIComponent(fid)}/units`),
      ]);
      const tiles = buildUnitTiles({
        fid, minis,
        units:   unitPayload?.units || [],
        primary: f?.primary || 'var(--panel)',
        accent:  f?.accent  || 'var(--gold)',
        facMark: _factionMarkInner(f),
      }).filter(t => boxDids.has(t.id));
      return { fid, name: f?.name || fid, tiles };
    }));
    if(selectedPurchaseId !== p.id) return;   // detail closed/changed while loading
    const groups = perFaction.filter(g => g.tiles.length);
    if(!groups.length){ host.innerHTML = `<p class="empty-note">No tracked models found for this box.</p>`; return; }
    const showHeads = groups.length > 1;
    host.innerHTML = groups.map(g => `
      <div class="al-pd-cardgroup">
        ${showHeads ? `<div class="al-pd-group-head">${esc(g.name)}</div>` : ''}
        <div class="unit-grid al-pd-cardgrid">${g.tiles.map(t => t.html).join('')}</div>
      </div>`).join('');
  }catch(e){
    host.innerHTML = `<p class="empty-note">Could not load model details.</p>`;
  }
}

function _renderPurchaseSummaryList(p){
  const rows = _summarizedContents(p.contents || []);
  if(!rows.length) return '';
  return `<div class="al-pd-sumlist">${rows.map(_renderMiniRow).join('')}</div>`;
}

function _renderPurchaseDetail(p){
  const surface = _boxSurface({faction_id: p.faction_id});
  const note    = p.notes ? `<div class="al-pd-note">${esc(p.notes)}</div>` : '';
  const release = p.release_date ? ` &middot; ${esc(p.release_date.slice(0,7))}` : '';
  return `
  <div class="al-pd">
    <button class="al-pd-back" onclick="closePurchaseDetail()">&larr; Back to purchases</button>
    <div class="al-pd-hero${surface.cls}"${surface.style}>
      ${surface.mark}
      <div class="al-pd-hero-img">
        <img src="/api/box-sets/${esc(p.box_set_id)}/image" alt="${esc(p.box_name)}">
      </div>
      <div class="al-pd-hero-info">
        <div class="al-pd-badges">${_boxBadges({faction_id: p.faction_id, source: p.source}, p)}</div>
        <h3 class="al-pd-name">${esc(p.box_name)}</h3>
        <div class="al-pd-stat">${p.total_physical_miniatures} physical &middot; ${p.total_datasheet_models} tracked${release}</div>
        ${note}
        <div class="al-pd-actions">
          <button class="al-cedit" onclick='switchToEditor(${jsStr(p.box_set_id)})'>Edit box</button>
          <button class="al-pd-del" onclick='deletePurchase(${jsStr(p.id)})'>Remove purchase</button>
        </div>
      </div>
      <aside class="al-pd-summary">
        <div class="al-pd-sec-label">Summary</div>
        ${_renderPurchaseSummaryList(p)}
        <div class="al-pd-sumtot">${p.total_physical_miniatures} physical &middot; ${p.total_datasheet_models} tracked</div>
      </aside>
    </div>
    <div class="al-pd-content">
      <div class="al-pd-main">
        <div class="al-pd-sec-label">Models in this box</div>
        <div id="pdCards" class="al-pd-cards"><p class="empty-note">Loading models…</p></div>
      </div>
    </div>
  </div>`;
}

// ── DOM-level open/close (no history change) ──
function _openDetailDom(pid){
  const p = (_lastPurchases || []).find(x => x.id === pid);
  if(!p) return;
  selectedPurchaseId = pid;
  const grid   = document.getElementById('purchGridWrap');
  const detail = document.getElementById('purchDetailWrap');
  if(grid)   grid.hidden = true;
  if(detail){ detail.hidden = false; detail.innerHTML = _renderPurchaseDetail(p); }
  window.scrollTo({top: 0, behavior: 'smooth'});
  _loadPurchaseDetailCards(p);
}

function _closeDetailDom(){
  selectedPurchaseId = null;
  const grid   = document.getElementById('purchGridWrap');
  const detail = document.getElementById('purchDetailWrap');
  if(detail){ detail.hidden = true; detail.innerHTML = ''; }
  if(grid)   grid.hidden = false;
}

// Drop the "/<pid>" off the hash without re-triggering the router (used after
// mutations / tab switches so the URL doesn't claim a detail is open).
function _resetPurchaseHash(){
  if(location.hash.startsWith('#/purchases/')) history.replaceState(null, '', '#/purchases');
}

// ── Navigation entry points ──
// Opening/closing the detail drives the hash so the browser Back button
// returns to the grid (and Forward re-opens the detail).
export function openPurchaseDetail(pid){
  location.hash = '/purchases/' + encodeURIComponent(pid);
}

export function closePurchaseDetail(){
  if(location.hash.startsWith('#/purchases/')) location.hash = '/purchases';
  else _closeDetailDom();
}

// Called by the router on every #/purchases[/pid] hashchange. Builds the page
// if we're arriving fresh, then syncs the detail open/closed to match the route
// — so navigating between grid and detail never refetches or rebuilds.
export async function routePurchases(openPid = null){
  // The router clears every paper scope before dispatching, including on the
  // grid<->detail hash hops that skip the rebuild below — re-assert it here.
  document.body.classList.add('rl-spa', 'purchases-ledger');
  document.body.setAttribute('data-rl-theme', rlThemeMode());
  if(!document.getElementById('purchGridWrap')){
    await showPurchases();
  }
  if(openPid){
    if(selectedPurchaseId !== openPid) _openDetailDom(openPid);
  } else if(selectedPurchaseId){
    _closeDetailDom();
  }
}

export async function submitPurchase(){
  const box_set_id = document.getElementById('purchaseBox')?.value || '';
  if(!box_set_id){ alert('Please select a box first.'); return; }
  const quantity   = Math.max(1, intOr(document.getElementById('purchaseQty')?.value, 1));
  const notes      = (document.getElementById('purchaseNotes')?.value || '').trim();
  await api('/api/purchases', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({box_set_id, quantity, notes})});
  clearFactionCache();
  showPurchases();
}

export async function deletePurchase(pid){
  if(!confirm('Remove this purchase?')) return;
  await fetch(`/api/purchases/${pid}`, {method:'DELETE'});
  clearFactionCache();
  _resetPurchaseHash();
  showPurchases();
}

// ══════════════════════════════════════════════════════════════
//  BOX CATALOGUE
// ══════════════════════════════════════════════════════════════

function _renderCatGrid(boxes, q='', fid=''){
  let list = boxes;
  const ql = q.toLowerCase();
  if(ql) list = list.filter(b=>b.name.toLowerCase().includes(ql)||(b.faction_id||'').toLowerCase().includes(ql));
  if(fid) list = list.filter(b=>b.faction_id===fid||!b.faction_id);
  if(!list.length) return `<p class="empty-note">No boxes match your filters.</p>`;
  return list.slice(0, CARD_CHUNK_SIZE).map(b=>_renderBoxCard(b)).join('');
}

function _wireCatalogue(boxes){
  const search  = document.getElementById('catSearch');
  const faction = document.getElementById('catFaction');
  const sortSel = document.getElementById('catSort');
  const update  = async ()=>{
    const fullBoxes = await _ensureBoxCatalogueLoaded();
    const q   = search?.value || '';
    const fid = faction?.value || '';
    const ql  = q.toLowerCase();
    let list = fullBoxes.filter(b=>
      (!ql||b.name.toLowerCase().includes(ql)||(b.faction_id||'').toLowerCase().includes(ql))&&
      (!fid||b.faction_id===fid||!b.faction_id)
    );
    list = _sortBoxes(list, sortSel?.value || 'name');
    const grid  = document.getElementById('catGrid');
    const count = document.getElementById('catCount');
    if(grid){
      grid.innerHTML = list.length ? list.slice(0, CARD_CHUNK_SIZE).map(b=>_renderBoxCard(b)).join('') : `<p class="empty-note">No boxes match your filters.</p>`;
      _scheduleCatalogueCards(list);
    }
    if(count) count.textContent = `${list.length} box${list.length===1?'':'es'}`;
  };
  search?.addEventListener('input', update);
  faction?.addEventListener('change', update);
  sortSel?.addEventListener('change', update);
}

function _catalogueLoadingNote(){
  return `<p class="empty-note">Open the box catalogue to load full box contents.</p>`;
}

function _defer(fn){
  if(window.requestIdleCallback) window.requestIdleCallback(fn, {timeout: 600});
  else setTimeout(fn, 0);
}

async function _ensureBoxCatalogueLoaded(){
  if(boxSetCache) return boxSetCache;
  if(!boxCatalogueLoading){
    boxCatalogueLoading = api('/api/box-sets').then(b => (boxSetCache = b)).catch(e => { boxCatalogueLoading = null; throw e; });
  }
  const grid = document.getElementById('catGrid');
  if(grid && activeTab === 'catalogue') grid.innerHTML = `<p class="empty-note">Loading box catalogue...</p>`;
  return boxCatalogueLoading;
}

function _scheduleCatalogueCards(boxes){
  const grid = document.getElementById('catGrid');
  if(!grid || boxes.length <= CARD_CHUNK_SIZE) return;
  let idx = CARD_CHUNK_SIZE;
  const append = () => {
    if(activeTab !== 'catalogue') return;
    const batch = boxes.slice(idx, idx + CARD_CHUNK_SIZE);
    if(batch.length) grid.insertAdjacentHTML('beforeend', batch.map(b=>_renderBoxCard(b)).join(''));
    idx += CARD_CHUNK_SIZE;
    if(idx < boxes.length) _defer(append);
  };
  _defer(append);
}

// ══════════════════════════════════════════════════════════════
//  TAB NAVIGATION
// ══════════════════════════════════════════════════════════════

function _wireTabs(){
  document.querySelectorAll('.al-tab').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      activeTab = btn.dataset.tab;
      document.querySelectorAll('.al-tab').forEach(b=>b.classList.toggle('is-active', b===btn));
      document.querySelectorAll('.al-panel').forEach(p=>{ p.hidden = p.id!==`tab-${activeTab}`; });
      if(activeTab === 'purchases' && selectedPurchaseId){
        _closeDetailDom();
        _resetPurchaseHash();
      }
      if(activeTab === 'catalogue'){
        document.getElementById('catSearch')?.dispatchEvent(new Event('input'));
      }
      if(activeTab === 'purchases' || activeTab === 'catalogue'){
        _nudgeLazyImages(`tab-${activeTab}`);
      }
    });
  });
}

function _nudgeLazyImages(panelId){
  const panel = document.getElementById(panelId);
  if(!panel) return;
  panel.querySelectorAll('img[loading="lazy"]').forEach(img => {
    if(!img.complete || img.naturalWidth === 0){
      img.loading = 'eager';
    }
  });
}

export function quickPurchase(boxId){
  activeTab = 'purchases';
  document.querySelectorAll('.al-tab').forEach(b=>b.classList.toggle('is-active', b.dataset.tab==='purchases'));
  document.querySelectorAll('.al-panel').forEach(p=>{ p.hidden = p.id!=='tab-purchases'; });
  if(selectedPurchaseId){ _closeDetailDom(); _resetPurchaseHash(); }
  const sel = document.getElementById('purchaseBox');
  if(sel){ sel.value = boxId; renderPurchasePreview(); }
  window.scrollTo({top: 0, behavior: 'smooth'});
}

export async function switchToEditor(boxId){
  activeTab = 'editor';
  document.querySelectorAll('.al-tab').forEach(b=>b.classList.toggle('is-active', b.dataset.tab==='editor'));
  document.querySelectorAll('.al-panel').forEach(p=>{ p.hidden = p.id!=='tab-editor'; });
  if(boxId && !boxSetCache) await _ensureBoxCatalogueLoaded();
  if(boxId) startBoxEditor(boxId);
  document.getElementById('tab-editor')?.scrollIntoView({behavior:'smooth', block:'start'});
}

// ══════════════════════════════════════════════════════════════
//  PURCHASE CONTROLS (army filter + sort + view toggle)
// ══════════════════════════════════════════════════════════════

function _wirePurchControls(){
  const armySel = document.getElementById('purchArmy');
  const sortSel = document.getElementById('purchSort');
  const refresh = ()=>{
    const items = _purchaseViewItems();
    const listEl = document.getElementById('purchaseList');
    const countEl = document.getElementById('purchCount');
    if(listEl) listEl.innerHTML = _renderPurchaseList(items);
    if(countEl) countEl.textContent = _purchaseCountLabel(items.length, _lastPurchases.length);
    if(purchViewMode === 'grid') _schedulePurchaseCards(items);
  };
  if(armySel) armySel.addEventListener('change', ()=>{
    purchArmyFilter = armySel.value;
    refresh();
  });
  if(sortSel) sortSel.addEventListener('change', ()=>{
    purchSortMode = sortSel.value;
    refresh();
  });
  document.querySelectorAll('.al-view-btn').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      purchViewMode = btn.dataset.view;
      document.querySelectorAll('.al-view-btn').forEach(b=>b.classList.toggle('is-active', b===btn));
      refresh();
    });
  });
}

// ══════════════════════════════════════════════════════════════
//  PURCHASE EDIT MODE
// ══════════════════════════════════════════════════════════════

function _wirePurchEditToggle(){
  document.getElementById('purchEditToggle')?.addEventListener('click', ()=>{
    purchEditMode = !purchEditMode;
    const btn  = document.getElementById('purchEditToggle');
    const list = document.getElementById('purchaseList');
    if(btn)  { btn.textContent = purchEditMode ? 'Done' : 'Edit'; btn.classList.toggle('is-active', purchEditMode); }
    if(list) { list.classList.toggle('is-editing', purchEditMode); }
  });
}

// ══════════════════════════════════════════════════════════════
//  BOX EDITOR
// ══════════════════════════════════════════════════════════════

function renderBoxEditor(box, factions){
  const editing = !!box;
  boxEditor = {
    id:       box?.id || '',
    editing,
    factions: factions || boxEditor?.factions || [],
    contents: (box?.contents||[]).map(i=>({
      datasheet_id: i.datasheet_id, catalogue_model_id: i.catalogue_model_id || null,
      catalogue_label: i.catalogue_label || '', catalogue_model: i.catalogue_model || null,
      name: i.name, faction_id: i.faction_id,
      datasheet_count: i.datasheet_count, physical_miniatures: i.physical_miniatures,
      notes: i.notes||'', multikit_group: i.multikit_group||null
    })),
    expected: box?.expected_minis ?? ''
  };
  const fid  = box?.faction_id || _commonBoxFaction(box) || '';
  const facs = factions || boxEditor.factions;
  return `
  <div class="al-ed">
    <div class="al-ed-head">
      <span class="al-ed-mode">${editing?`Editing: ${esc(box.name)}`:'New Box Set'}</span>
      <div class="al-ed-head-actions">
        ${editing?`<button class="btn-ghost" id="boxResetBtn">New Box</button>`:''}
        ${editing&&box.source==='local'?`<button class="btn-ghost danger" id="boxDeleteBtn">Delete</button>`:''}
      </div>
    </div>

    <div class="al-ed-grid">
      <div class="al-ed-field">
        <label class="ff-label">Army</label>
        <select id="boxFaction">
          <option value="">Mixed / any army</option>
          ${[...facs].sort((a,b)=>(a.display_name||a.name).localeCompare(b.display_name||b.name))
            .map(f=>`<option value="${esc(f.id)}" ${f.id===fid?'selected':''}>${esc(f.display_name||f.name)}</option>`).join('')}
        </select>
      </div>
      <div class="al-ed-field">
        <label class="ff-label">Box name</label>
        <input id="boxName" class="ff-input" value="${esc(box?.name||'')}" placeholder="e.g. Combat Patrol: Tyranids" autocomplete="off">
      </div>
      <div class="al-ed-field">
        <label class="ff-label">Release</label>
        <input id="boxRelease" class="ff-input" value="${esc(box?.release_date||'')}" placeholder="YYYY-MM" autocomplete="off">
      </div>
      <div class="al-ed-field">
        <label class="ff-label">Expected minis</label>
        <input id="boxExpected" class="ff-input" type="number" min="1" max="9999" value="${boxEditor.expected||''}" placeholder="e.g. 20" autocomplete="off">
      </div>
    </div>

    <div class="al-ed-section">
      <div class="al-ed-sec-label">Add units</div>
      <div class="al-ed-import">
        <textarea id="boxImportText" class="ff-input al-import-ta" placeholder="Paste box contents, e.g. 1x Belial – 5x Deathwing Knights"></textarea>
        <button class="btn-ghost" id="boxImportBtn">Quick Import</button>
        <div id="boxImportMsg" class="al-import-msg"></div>
      </div>
      <div class="box-unit-search">
        <input id="boxUnitSearch" class="ff-input" placeholder="Search and add unit by name…" autocomplete="off">
        <div id="boxUnitResults" class="box-unit-results"></div>
      </div>
    </div>

    <div id="boxContentRows">${renderBoxContentRowsHtml()}</div>
    <div id="boxMiniCheck" class="al-mini-check"></div>

    <div class="al-ed-section">
      <label class="ff-label">Notes</label>
      <input id="boxNotes" class="ff-input" value="${esc(box?.notes||'')}" placeholder="Source link, store notes…" autocomplete="off">
    </div>

    ${editing ? _renderBoxImageControls(box.id, box.name) : `
    <div class="al-box-img-new-hint">
      <span>✦</span> Save the box first, then you can add a cover image.
    </div>`}

    <div id="boxNameConflict" class="box-name-conflict" style="display:none"></div>

    <div class="al-ed-actions">
      <button class="btn-primary" id="boxSaveBtn">${editing?'Save Changes':'Create Box'}</button>
    </div>
  </div>
  `;
}

function _commonBoxFaction(box){
  if(!box||!box.contents?.length) return '';
  const first = box.contents[0].faction_id;
  return box.contents.every(i=>i.faction_id===first) ? first : '';
}

export function startBoxEditor(boxId){
  // Switch to editor tab if needed
  if(document.getElementById('tab-editor') && activeTab!=='editor'){
    activeTab = 'editor';
    document.querySelectorAll('.al-tab').forEach(b=>b.classList.toggle('is-active', b.dataset.tab==='editor'));
    document.querySelectorAll('.al-panel').forEach(p=>{ p.hidden = p.id!=='tab-editor'; });
  }
  const box    = (boxSetCache||[]).find(b=>b.id===boxId);
  const editor = document.getElementById('boxEditor');
  if(editor&&box){
    editor.innerHTML = renderBoxEditor(box, boxEditor?.factions||[]);
    wireBoxEditor();
  }
  editor?.scrollIntoView({behavior:'smooth', block:'start'});
}

export function resetBoxEditor(){
  const editor = document.getElementById('boxEditor');
  if(editor){
    editor.innerHTML = renderBoxEditor(null, boxEditor?.factions||[]);
    wireBoxEditor();
  }
}

function _updateMiniCheck(){
  const el = document.getElementById('boxMiniCheck');
  if(!el) return;
  const inp      = document.getElementById('boxExpected');
  const expected = inp ? (parseInt(inp.value, 10) || 0) : 0;
  if(inp) boxEditor.expected = expected || '';

  const contents = boxEditor.contents || [];

  // Mirrors backend _normalize_box: multikit groups share a physical pool, count each once.
  const seenGroups = new Set();
  let actual = 0;
  contents.forEach(i => {
    if(i.multikit_group){
      if(!seenGroups.has(i.multikit_group)){ seenGroups.add(i.multikit_group); actual += i.physical_miniatures; }
    } else {
      actual += i.physical_miniatures;
    }
  });

  // Linked items must have identical datasheet_count (they come from the same sprue).
  const groupItems = {};
  contents.forEach(i => { if(i.multikit_group){ (groupItems[i.multikit_group] = groupItems[i.multikit_group]||[]).push(i); } });
  const qtyMismatches = Object.values(groupItems).filter(items => items.some(i => i.datasheet_count !== items[0].datasheet_count));

  const lines = [];
  if(expected){
    if(actual === expected){
      lines.push(`✓ ${actual} / ${expected} physical minis — count matches`);
    } else {
      const diff = actual - expected;
      lines.push(`${actual} / ${expected} physical minis — ${diff > 0 ? diff + ' over' : Math.abs(diff) + ' short'}`);
    }
  }
  qtyMismatches.forEach(items => {
    lines.push(`Linked quantities differ: ${items.map(i=>`${i.datasheet_count}x ${esc(i.name)}`).join(' vs ')}`);
  });

  if(!lines.length){ el.className = 'al-mini-check'; el.innerHTML = ''; return; }

  const countOk  = !expected || actual === expected;
  const linksOk  = qtyMismatches.length === 0;
  el.className   = (countOk && linksOk) ? 'al-mini-check is-ok' : 'al-mini-check is-warn';
  el.innerHTML   = lines.map(l=>`<div>${l}</div>`).join('');
}

function wireBoxEditor(){
  const faction = document.getElementById('boxFaction');
  if(faction) faction.onchange = ()=>{boxEditor.contents=[];renderBoxContentRows();searchBoxUnits();};
  const search = document.getElementById('boxUnitSearch');
  if(search) search.oninput = ()=>searchBoxUnits();
  const nameInput = document.getElementById('boxName');
  if(nameInput) nameInput.oninput = ()=>{
    const warn = document.getElementById('boxNameConflict');
    if(warn) warn.style.display = 'none';
  };
  const expected = document.getElementById('boxExpected');
  if(expected) expected.oninput = ()=>_updateMiniCheck();
  const save  = document.getElementById('boxSaveBtn');  if(save)  save.onclick  = ()=>saveBoxSet();
  const reset = document.getElementById('boxResetBtn'); if(reset) reset.onclick = ()=>resetBoxEditor();
  const del   = document.getElementById('boxDeleteBtn'); if(del)  del.onclick   = ()=>deleteBoxSet(boxEditor.id);
  const imp   = document.getElementById('boxImportBtn'); if(imp)  imp.onclick   = ()=>quickImportBoxText();
  _wireBoxRefFile();
  renderBoxContentRows();
}

// ── Box content rows ──────────────────────────────────────────

function _mkGroups(){
  const g = {};
  (boxEditor?.contents||[]).forEach(i=>{
    if(i.multikit_group){ (g[i.multikit_group]=g[i.multikit_group]||[]).push(i.name); }
  });
  return g;
}

function _mkLabel(gid, groups){
  return (groups[gid]||[]).slice(0,2).map(n=>n.split(' ').slice(-1)[0]).join(' / ');
}

function _unitRowLabel(item){
  return item.catalogue_label || item.name;
}

function _cleanOrphanGroups(){
  const counts = {};
  boxEditor.contents.forEach(i=>{ if(i.multikit_group) counts[i.multikit_group]=(counts[i.multikit_group]||0)+1; });
  boxEditor.contents.forEach(i=>{ if(i.multikit_group && counts[i.multikit_group]<2) i.multikit_group=null; });
}

function renderBoxContentRowsHtml(){
  if(!boxEditor?.contents?.length) return `<div class="al-units-empty">No units added yet. Search above or use Quick Import.</div>`;

  // Sort contents in place so linked items sit next to each other.
  // Walk the original order; when we hit a linked item for the first time,
  // immediately pull in the rest of that group before continuing.
  const placed = new Set();
  const order  = [];
  boxEditor.contents.forEach((item, idx) => {
    if(placed.has(idx)) return;
    placed.add(idx);
    order.push(idx);
    if(item.multikit_group){
      boxEditor.contents.forEach((other, oidx) => {
        if(!placed.has(oidx) && other.multikit_group === item.multikit_group){
          placed.add(oidx);
          order.push(oidx);
        }
      });
    }
  });
  const sorted = order.map(i => boxEditor.contents[i]);
  boxEditor.contents.splice(0, boxEditor.contents.length, ...sorted);

  const groups  = _mkGroups();
  const hasAlt  = boxEditor.contents.length > 1;

  const linkedToIdx = (currentIdx) => {
    const gid = boxEditor.contents[currentIdx].multikit_group;
    if(!gid) return '';
    const other = boxEditor.contents.findIndex((o,oi)=>oi!==currentIdx&&o.multikit_group===gid);
    return other>=0 ? String(other) : '';
  };

  const unitOpts = (currentIdx) => {
    const linked = linkedToIdx(currentIdx);
    const opts = [`<option value="" ${!linked?'selected':''}>Standalone</option>`];
    boxEditor.contents.forEach((item,idx)=>{
      if(idx!==currentIdx)
        opts.push(`<option value="${idx}" ${linked===String(idx)?'selected':''}>${esc(item.name)}</option>`);
    });
    return opts.join('');
  };

  return `<div class="al-unit-rows${hasAlt?' has-alt':''}">
    <div class="al-unit-row-head">
      <span>Unit</span><span>Qty</span>${hasAlt?'<span>Alt of</span>':''}<span></span>
    </div>
    ${boxEditor.contents.map((i,idx)=>`
    <div class="al-unit-row${i.multikit_group?' is-linked':''}">
      <div class="al-unit-row-name">
        <span class="al-unit-rname">${esc(_unitRowLabel(i))}</span>
        ${i.catalogue_label?`<span class="al-unit-sculpt">${esc(i.name)}</span>`:''}
        ${i.multikit_group?`<span class="al-link-badge">⇄ ${esc(_mkLabel(i.multikit_group,groups))}</span>`:''}
      </div>
      <input class="al-unit-qty" type="number" min="1" max="500" value="${i.datasheet_count}" data-box-qty="${idx}">
      ${hasAlt?`<select class="al-unit-altsel" data-box-mk="${idx}">${unitOpts(idx)}</select>`:''}
      <button class="al-unit-del" data-box-remove="${idx}" title="Remove unit">✕</button>
    </div>`).join('')}
  </div>`;
}

export function renderBoxContentRows(){
  const el = document.getElementById('boxContentRows');
  if(!el) return;
  el.innerHTML = renderBoxContentRowsHtml();
  el.querySelectorAll('[data-box-qty]').forEach(input=>{
    input.onchange = ()=>{
      const idx  = intOr(input.dataset.boxQty, 0);
      const item = boxEditor.contents[idx];
      if(!item) return;
      const oldQty = item.datasheet_count;
      const newQty = Math.max(1, intOr(input.value, 1));
      if(item.physical_miniatures !== oldQty){
        item.physical_miniatures = Math.max(1, Math.round(item.physical_miniatures * newQty / Math.max(1, oldQty)));
      } else {
        item.physical_miniatures = newQty;
      }
      item.datasheet_count = newQty;
      _updateMiniCheck();
    };
  });
  el.querySelectorAll('[data-box-mk]').forEach(sel=>{
    sel.onchange = ()=>{
      const thisIdx   = intOr(sel.dataset.boxMk, 0);
      const targetIdx = sel.value==='' ? -1 : intOr(sel.value, -1);
      const thisItem  = boxEditor.contents[thisIdx];
      const oldGroup  = thisItem.multikit_group;
      if(targetIdx<0){
        thisItem.multikit_group = null;
      } else {
        const targetItem = boxEditor.contents[targetIdx];
        if(targetItem.multikit_group){
          thisItem.multikit_group = targetItem.multikit_group;
        } else {
          const newId = 'mk-' + Math.random().toString(36).slice(2,7);
          thisItem.multikit_group = newId;
          targetItem.multikit_group = newId;
        }
      }
      if(oldGroup && oldGroup!==thisItem.multikit_group){
        const orphans = boxEditor.contents.filter(i=>i.multikit_group===oldGroup);
        if(orphans.length===1) orphans[0].multikit_group=null;
      }
      renderBoxContentRows();
    };
  });
  el.querySelectorAll('[data-box-remove]').forEach(btn=>{
    btn.onclick = ()=>{
      boxEditor.contents.splice(intOr(btn.dataset.boxRemove, 0), 1);
      _cleanOrphanGroups();
      renderBoxContentRows();
    };
  });
  _updateMiniCheck();
}

// ── Unit search ───────────────────────────────────────────────

let _boxSearchTimer = null;
export function searchBoxUnits(){
  clearTimeout(_boxSearchTimer);
  _boxSearchTimer = setTimeout(async()=>{
    const q   = (document.getElementById('boxUnitSearch')?.value || '').trim();
    const fid = document.getElementById('boxFaction')?.value || '';
    const out = document.getElementById('boxUnitResults');
    if(!out) return;
    if(q.length<2){out.innerHTML='';return;}
    const units = await api(`/api/model-catalogue/search?faction_id=${encodeURIComponent(fid)}&q=${encodeURIComponent(q)}`);
    if(!units.length){ out.innerHTML=`<p class="empty-note">No matching units.</p>`; return; }
    out.innerHTML = units.slice(0,12).map(u=>_renderCatalogueResult(u)).join('');
    out.querySelectorAll('[data-add-catalogue-model]').forEach(btn=>{
      btn.onclick = ()=>addCatalogueModelToBox({
        id: btn.dataset.addCatalogueModel,
        name: btn.dataset.addName,
        label: btn.dataset.addLabel || btn.dataset.addName,
        links: JSON.parse(btn.dataset.addLinks || '[]')
      });
    });
    out.querySelectorAll('[data-add-model-only]').forEach(btn=>{
      btn.onclick = ()=>addCatalogueModelOnlyToBox({
        id: btn.dataset.addModelOnly,
        name: btn.dataset.addName,
        label: btn.dataset.addLabel || btn.dataset.addName,
        faction_id: btn.dataset.addFaction || ''
      });
    });
    out.querySelectorAll('[data-add-single-link]').forEach(btn=>{
      const link = JSON.parse(btn.dataset.addSingleLink);
      const item = JSON.parse(btn.dataset.addItem);
      btn.onclick = ()=>{
        addUnitToBox(link.datasheet_id, link.datasheet_name, link.faction_id||'', item.id, item.label, null, true);
        document.getElementById('boxUnitSearch').value = '';
        out.innerHTML = '';
      };
    });
  }, 180);
}

function _renderCatalogueResult(u){
  const links = u.datasheet_links || [];
  if(u.datasheet_less || !links.length){
    // Datasheet-less model: tracked by catalogue model id only, no game unit behind it.
    return `
      <button type="button" class="box-unit-modelonly"
        data-add-model-only="${esc(u.catalogue_model_id||u.id)}"
        data-add-name="${esc(u.name)}"
        data-add-label="${esc(u.display_label||u.catalogue_label||u.name)}"
        data-add-faction="${esc(u.faction_id||'')}">
        <span>${esc(u.display_label||u.name)}</span>
        <small>${esc([(u.faction_label_display || u.faction_label), 'model only — no datasheet'].filter(Boolean).join(' · '))}</small>
      </button>`;
  }
  if(links.length <= 1){
    return `
      <button type="button" data-add-catalogue-model="${esc(u.catalogue_model_id||u.id)}"
        data-add-name="${esc(u.name)}"
        data-add-label="${esc(u.display_label||u.catalogue_label||u.name)}"
        data-add-links="${esc(JSON.stringify(links))}">
        <span>${esc(u.display_label||u.name)}</span>
        <small>${esc(_catalogueResultMeta(u))}</small>
      </button>`;
  }
  const itemJson = esc(JSON.stringify({id: u.catalogue_model_id||u.id, label: u.display_label||u.catalogue_label||u.name}));
  return `
    <div class="box-unit-group">
      <div class="box-unit-group-head">
        <span>${esc(u.display_label||u.name)}</span>
        <small>${esc(u.faction_label_display || u.faction_label || '')} · ${links.length} versions — pick one</small>
      </div>
      ${links.map(l=>`
        <button type="button" class="box-unit-sub-result"
          data-add-single-link="${esc(JSON.stringify(l))}"
          data-add-item="${itemJson}">
          <span>${esc(l.datasheet_name)}</span>
          <small>${[l.faction_id, l.role, l.datasheet_id].filter(Boolean).join(' · ')}</small>
        </button>`).join('')}
    </div>`;
}

function _catalogueResultMeta(item){
  const bits = [];
  const facLabel = item.faction_label_display || item.faction_label;
  if(facLabel) bits.push(facLabel);
  const links = item.datasheet_links || [];
  bits.push(links.length === 1 ? links[0].datasheet_name : `${links.length} linked units`);
  return bits.filter(Boolean).join(' · ');
}

export function addCatalogueModelToBox(item){
  const links = item.links || [];
  if(!links.length) return;
  const groupId = links.length > 1
    ? _existingCatalogueGroup(item.id) || `cat-${item.id}-${Math.random().toString(36).slice(2,7)}`
    : null;
  links.forEach(link => addUnitToBox(
    link.datasheet_id,
    link.datasheet_name || item.name,
    link.faction_id || '',
    item.id,
    item.label,
    groupId,
    false
  ));
  document.getElementById('boxUnitSearch').value = '';
  document.getElementById('boxUnitResults').innerHTML = '';
  renderBoxContentRows();
}

// Add a datasheet-less model as a standalone box row, keyed by the synthetic
// "cat:<catalogue_model_id>" id. addUnitToBox clears the search + re-renders.
export function addCatalogueModelOnlyToBox(item){
  addUnitToBox('cat:' + item.id, item.name, item.faction_id || '', item.id, item.label, null, true);
}

function _existingCatalogueGroup(catalogueModelId){
  const existing = boxEditor.contents.find(i=>i.catalogue_model_id===catalogueModelId && i.multikit_group);
  return existing?.multikit_group || null;
}

export function addUnitToBox(did, name, fid, catalogueModelId=null, catalogueLabel='', multikitGroup=null, shouldRender=true){
  const cmid = catalogueModelId || null;
  const existing = boxEditor.contents.find(i=>i.datasheet_id===did && (i.catalogue_model_id||null)===cmid);
  if(existing){
    existing.datasheet_count += 1;
    existing.physical_miniatures += 1;
    if(shouldRender) renderBoxContentRows();
    return;
  }
  const groupId = multikitGroup || null;
  const notes = groupId ? `Catalogue model: ${catalogueLabel || name}` : '';
  const rowLabel = catalogueLabel && catalogueLabel !== name ? catalogueLabel : '';
  boxEditor.contents.push({
    datasheet_id: did, catalogue_model_id: cmid, catalogue_label: rowLabel,
    name, faction_id: fid, datasheet_count: 1, physical_miniatures: 1,
    notes, multikit_group: groupId
  });
  if(shouldRender){
    document.getElementById('boxUnitSearch').value = '';
    document.getElementById('boxUnitResults').innerHTML = '';
    renderBoxContentRows();
  }
}

// ── Quick import ──────────────────────────────────────────────

export async function quickImportBoxText(){
  const text = (document.getElementById('boxImportText')?.value || '').trim();
  const msg  = document.getElementById('boxImportMsg');
  if(!text){if(msg) msg.textContent='Paste box contents first.';return;}
  const faction_id = document.getElementById('boxFaction')?.value || '';
  const res = await api('/api/box-sets/parse', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({text, faction_id})});
  (res.matches||[]).forEach(m=>{
    const existing = boxEditor.contents.find(i=>i.datasheet_id===m.datasheet_id);
    if(existing){
      existing.datasheet_count     += m.datasheet_count;
      existing.physical_miniatures += m.physical_miniatures;
    }else{
      boxEditor.contents.push({
        datasheet_id: m.datasheet_id, name: m.name, faction_id: m.faction_id,
        catalogue_model_id: m.catalogue_model_id || null,
        catalogue_label: m.catalogue_label || '',
        datasheet_count: m.datasheet_count, physical_miniatures: m.physical_miniatures,
        multikit_group: null,
        notes: m.alternatives?.length
          ? `Matched from "${m.source_text}". Alternatives: ${m.alternatives.map(a=>a.name).join(', ')}`
          : ''
      });
    }
  });
  renderBoxContentRows();
  const unresolved = res.unresolved || [];
  if(msg) msg.textContent = `Imported ${(res.matches||[]).length} unit${(res.matches||[]).length===1?'':'s'}`
    + (unresolved.length ? `; review unresolved: ${unresolved.map(u=>`${u.quantity}x ${u.text}`).join(', ')}` : '') + '.';
}

// ══════════════════════════════════════════════════════════════
//  BOX IMAGE (reference photo)
// ══════════════════════════════════════════════════════════════

function _renderBoxImageControls(boxId, boxName){
  const searchUrl = `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(boxName + ' Warhammer 40k box set')}`;
  return `
  <div class="al-ed-section al-box-img-section">
    <div class="al-ed-sec-label">Box cover image</div>
    <div class="al-box-img-panel">
      <div class="al-box-img-preview">
        <img id="boxRefImg" class="al-box-img" src="/api/box-sets/${esc(boxId)}/image" alt="${esc(boxName)}">
      </div>
      <div class="al-box-img-controls">
        <a class="ref-search" href="${esc(searchUrl)}" target="_blank" rel="noopener noreferrer">Search Google Images for box art ↗</a>
        <div class="ref-row">
          <input id="boxRefUrl" class="ff-input" placeholder="Paste image address here…" autocomplete="off"
                 onkeydown="if(event.key==='Enter')saveBoxRef()">
          <button class="btn-primary" onclick="saveBoxRef()">Save</button>
        </div>
        <div class="al-box-img-upload-row">
          <label class="btn-ghost al-upload-label">
            Upload image…
            <input type="file" id="boxRefFile" accept="image/*" style="display:none">
          </label>
          <button class="btn-ghost ref-clear" onclick="clearBoxRef()">Clear image</button>
        </div>
        <div class="ref-msg" id="boxRefMsg"></div>
      </div>
    </div>
  </div>
  `;
}

function _wireBoxRefFile(){
  const file = document.getElementById('boxRefFile');
  if(file) file.onchange = ()=>{ if(file.files[0]) _saveBoxRefFromFile(file.files[0]); };
}

function _boxRefMsg(text, ok){
  const el = document.getElementById('boxRefMsg');
  if(!el) return;
  el.textContent = text || '';
  el.className   = 'ref-msg' + (text ? (ok ? ' ok' : ' err') : '');
}

function _refreshBoxImg(){
  const img = document.getElementById('boxRefImg');
  if(img && boxEditor?.id) img.src = `/api/box-sets/${boxEditor.id}/image?v=${Date.now()}`;
  if(!boxEditor?.id) return;
  const newSrc = `/api/box-sets/${boxEditor.id}/image?v=${Date.now()}`;
  document.querySelectorAll(`.al-ccard-img[src*="${boxEditor.id}"]`).forEach(el => {
    el.loading = 'eager';
    el.src = newSrc;
  });
}

export async function saveBoxRef(){
  const boxId = boxEditor?.id;
  if(!boxId){ _boxRefMsg('Save the box first before adding an image.', false); return; }
  const input = document.getElementById('boxRefUrl');
  const url   = (input?.value || '').trim();
  if(!url){ _boxRefMsg('Paste an image address first.', false); return; }
  _boxRefMsg('Fetching image…', true);
  try{
    const res = await api(`/api/box-sets/${boxId}/reference`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url})
    });
    if(res.ok){ if(input) input.value=''; _refreshBoxImg(); _boxRefMsg('✓ Image saved.', true); }
    else _boxRefMsg(res.error || 'Could not save that image.', false);
  }catch(e){ _boxRefMsg('Could not save that image.', false); }
}

async function _saveBoxRefFromFile(fileObj){
  const boxId = boxEditor?.id;
  if(!boxId) return;
  _boxRefMsg('Saving image…', true);
  const fd = new FormData();
  fd.append('file', fileObj);
  try{
    const res = await api(`/api/box-sets/${boxId}/reference`, {method:'POST', body:fd});
    if(res.ok){ _refreshBoxImg(); _boxRefMsg('✓ Image saved.', true); }
    else _boxRefMsg(res.error || 'Could not save.', false);
  }catch(e){ _boxRefMsg('Could not save.', false); }
}

export async function clearBoxRef(){
  const boxId = boxEditor?.id;
  if(!boxId) return;
  await fetch(`/api/box-sets/${boxId}/reference`, {method:'DELETE'});
  _refreshBoxImg();
  _boxRefMsg('Image removed.', true);
}

// ── Save / Delete ─────────────────────────────────────────────

function _boxSlug(name){
  return (name||'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,80)||'box-set';
}

export async function saveBoxSet(forceConflict=false){
  const nameInput  = document.getElementById('boxName');
  const name       = (nameInput?.value || '').trim();
  const conflictEl = document.getElementById('boxNameConflict');

  if(!boxEditor.editing && !forceConflict){
    const slug     = _boxSlug(name);
    const conflict = (boxSetCache||[]).find(b=>b.id===slug);
    if(conflict){
      if(conflictEl){
        conflictEl.style.display = '';
        conflictEl.innerHTML = `A box named <strong>${esc(conflict.name)}</strong> already exists with this ID.
          Rename your box, or <a id="boxSaveAnyway">save anyway</a> to assign a unique ID.`;
        document.getElementById('boxSaveAnyway')?.addEventListener('click', e=>{
          e.preventDefault();
          saveBoxSet(true);
        });
      }
      nameInput?.focus();
      nameInput?.select();
      return;
    }
  }
  if(conflictEl) conflictEl.style.display = 'none';

  const payload = {
    name,
    faction_id:    document.getElementById('boxFaction')?.value || '',
    release_date:  (document.getElementById('boxRelease')?.value || '').trim(),
    notes:         (document.getElementById('boxNotes')?.value || '').trim(),
    expected_minis: parseInt(document.getElementById('boxExpected')?.value, 10) || null,
    contents:      boxEditor.contents
  };
  const url = boxEditor.editing ? `/api/box-sets/${boxEditor.id}` : '/api/box-sets';
  let res;
  try {
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    res = await r.json();
  } catch(e) {
    alert('Could not reach the server. Please try again.');
    return;
  }
  if(!res.ok){ alert(res.error || 'Could not save box set.'); return; }
  const sync = res.minis;
  if(sync && (sync.created || sync.removed || sync.kept)){
    const parts = [];
    if(sync.created) parts.push(`${sync.created} new mini${sync.created===1?'':'s'} added to your collection`);
    if(sync.removed) parts.push(`${sync.removed} unbuilt mini${sync.removed===1?'':'s'} removed`);
    if(sync.kept) parts.push(`${sync.kept} kept because you have already worked on them`);
    alert(`This box has purchases, so they were updated too: ${parts.join('; ')}.`);
  }
  const savedBoxId = res.id || (boxEditor.editing ? boxEditor.id : _boxSlug(name));
  boxSetCache = null; boxCatalogueLoading = null;
  activeTab = 'catalogue';
  _resetPurchaseHash();
  await showPurchases();
  _defer(() => {
    const el = document.querySelector(`[data-box-id="${CSS.escape(savedBoxId)}"]`);
    el?.scrollIntoView({behavior:'smooth', block:'center'});
  });
}

export async function deleteBoxSet(boxId){
  if(!confirm('Delete this box set from your local catalogue?')) return;
  const res = await fetch(`/api/box-sets/${boxId}`, {method:'DELETE'});
  if(!res.ok){alert('Could not delete this box. Remove purchases for it first.');return;}
  boxSetCache = null; boxCatalogueLoading = null;
  _resetPurchaseHash();
  showPurchases();
}
