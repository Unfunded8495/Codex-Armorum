/* /missions — "Mission Deck" reference, PDF-manual redesign.
   Renders /api/missions into a single scrolling manual: six numbered
   sections, a sticky category strip, a contents sidebar with search +
   scrollspy, mission cards, CSS deployment diagrams and a maps table.
   Light default + dark reading mode shared with /rules (localStorage
   "caRules.theme"). No scrollIntoView — jumps use scrollTop math. */
import { esc } from './utils.js';
import { openLightbox, initLightbox } from './lightbox.js';

const view = document.getElementById('view');
const stripChipsEl = document.getElementById('mzStripChips');
const tocEl = document.getElementById('mzToc');
const deckCountEl = document.getElementById('mzDeckCount');
const searchEl = document.getElementById('mzSearch');
const topBtn = document.getElementById('mzTopBtn');
const themeBtn = document.getElementById('mzThemeBtn');
const themeLabel = document.getElementById('mzThemeLabel');

const THEME_KEY = 'caRules.theme';
const EDITION = 'Warhammer 40,000 · 11th Edition';
const EPIGRAPH = 'No plan survives contact with the enemy. / Plan anyway.';

/* The six manual sections, in reading order. `key` indexes the API payload. */
const CATS = [
  { id: 'sec-primary',     label: 'Primary',     key: 'primary'     },
  { id: 'sec-secondary',   label: 'Secondary',   key: 'secondary'   },
  { id: 'sec-deployments', label: 'Deployments', key: 'deployments' },
  { id: 'sec-layouts',     label: 'Layouts',     key: 'layouts'     },
  { id: 'sec-presets',     label: 'Maps',        key: 'presets'     },
  { id: 'sec-twists',      label: 'Twists',      key: 'twists'      },
];

/* Deployment geometry is not in the data (the DB stores only id + name), so we
   map the known 11th-ed deployment names to their official zone maps (the PNGs
   shipped under static/images/deployments) plus a short reading note. Unknown
   names simply render without a map. */
const DEPLOY_MAPS = {
  'dawn of war': {
    img: 'ic_dawn_of_war.png',
    note: 'Deploy along opposite long board edges, the classic embattled line.',
  },
  'hammer and anvil': {
    img: 'ic_hammer_and_anvil.png',
    note: 'Deploy along the short board edges; a long advance separates the armies.',
  },
  'search and destroy': {
    img: 'ic_search_and_destroy.png',
    note: 'Deploy in diagonally opposite table quarters; everything between is No Man’s Land.',
  },
  'crucible of battle': {
    img: 'ic_crucible_of_battle.png',
    note: 'Deploy in opposite corners along the main diagonal of the battlefield.',
  },
  'sweeping engagement': {
    img: 'ic_sweeping_engagement.png',
    note: 'Angled zones sweep in from opposite corners toward the centre.',
  },
  'tipping point': {
    img: 'ic_tipping_point.png',
    note: 'Offset diagonal zones tilt in toward the contested centre line.',
  },
};

let DATA = null;
let activeSec = null;
let firstHit = null;

applyTheme(readTheme());   // before first paint — no flash
init();

async function init(){
  bindStatic();
  let data;
  try{
    const r = await fetch('/api/missions');
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
  }catch(err){
    view.innerHTML = `<div class="rl-error" data-testid="missions-view">Failed to load the mission deck (${esc(String(err))}).</div>`;
    return;
  }
  DATA = normalise(data);
  renderStrip();
  renderToc();
  renderMain();
  bindContentJumps();
  bindLayoutToggles();
  bindMapZoom();
  initLightbox();
  bindScrollSpy();
  if(location.hash) jumpTo(location.hash.slice(1), false);
}

/* Map the raw /api/missions payload onto the fields the manual renders.
   Production field names differ from the design prototype's sample. */
function normalise(d){
  const packName = (d.packs && d.packs[0] && d.packs[0].name || 'Matched Play').trim();
  return {
    packName,
    primary:   (d.primary || []).map(m => ({
      id: m.id, name: m.name || '', lore: m.lore || '',
      brief: m.description || '', objectives: m.objectives || [],
    })),
    secondary: (d.secondary || []).map(m => ({
      id: m.id, name: m.name || '', lore: m.lore || '', brief: m.description || '',
      fixed: !!m.fixed, turn1: !!m.scorable_first_turn,
      objectives: m.objectives || [],
    })),
    deployments: (d.deployments || []).map(x => ({ id: x.id, name: x.name || '' })),
    layouts:     (d.layouts || []).map(x => ({ id: x.id, name: x.name || '' })),
    presets:     (d.presets || []).map(m => ({
      id: m.id, name: m.name || '',
      deployment_id: m.mission_deployment_id || m.deployment_id || '',
      layout_id: m.mission_layout_id || m.layout_id || '',
      twist_id: m.mission_twist_id || m.twist_id || '',
    })),
    twists:    (d.twists || []).map(m => ({
      id: m.id, name: m.name || '', lore: m.lore || '', brief: m.rules || m.description || '',
    })),
  };
}

/* GW plain-text carries **bold** markers; escape first, then promote pairs. */
function fmt(s){ return esc(s || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
function count(key){ return (DATA[key] || []).length; }

/* One scoring line: the criteria on the left, the victory-point award on the
   right. Cumulative rows read as a "+N" bonus; secondary rows also carry the
   Fixed/Tactical mode they score in and an optional cap. */
function scoreRow(s){
  const vp = `${s.cumulative ? '+' : ''}${s.vp != null ? s.vp : 0}VP`;
  const tags = [];
  if(s.mode === 'fixed')    tags.push('<span class="mz-score-tag">Fixed</span>');
  if(s.mode === 'tactical') tags.push('<span class="mz-score-tag">Tactical</span>');
  if(s.cap)                 tags.push(`<span class="mz-score-tag">max ${esc(String(s.cap))}VP</span>`);
  if(s.cumulative)          tags.push('<span class="mz-score-tag">cumulative</span>');
  return `<div class="mz-score-row${s.cumulative ? ' mz-score-row--cumul' : ''}">
    <span class="mz-score-crit">${fmt(s.criteria || '')}</span>
    <span class="mz-score-award"><span class="mz-score-vp">${esc(vp)}</span>${tags.join('')}</span>
  </div>`;
}

/* One period of a mission card: the period header, its "when", and the
   scoring lines that score during it. Shared by primary and secondary cards. */
function objBlock(o){
  const when = o.when ? `<span class="mz-obj-when">${fmt(o.when)}</span>` : '';
  const scoring = (o.scoring || []).map(scoreRow).join('');
  return `<div class="mz-obj">
    <div class="mz-obj-head"><span class="mz-obj-name">${esc(o.name || '')}</span>${when}</div>
    ${scoring ? `<div class="mz-score">${scoring}</div>` : ''}
  </div>`;
}

/* --------------------------------------------------------- quick-ref strip */

function renderStrip(){
  stripChipsEl.innerHTML = CATS.map(c =>
    `<a class="rl-chip" data-sec="${c.id}" href="#${c.id}">${esc(c.label)}<b>${count(c.key)}</b></a>`
  ).join('');
}

/* ---------------------------------------------------------------- sidebar */

function renderToc(){
  const total = count('primary') + count('secondary') + count('twists');
  deckCountEl.textContent = `${total} mission cards`;
  tocEl.innerHTML = CATS.map((c, i) => {
    const items = (DATA[c.key] || []).map(m =>
      `<a class="mz-toc-item" href="#${m.id}">${esc(m.name)}</a>`).join('');
    return `<div class="mz-toc-group" data-sec="${c.id}">
      <a class="mz-toc-head" href="#${c.id}">
        <span class="mz-toc-num">0${i + 1}</span>
        <span class="mz-toc-title">${esc(c.label)}</span>
        <span class="mz-toc-count">${count(c.key)}</span>
      </a>
      <div class="mz-toc-items">${items}</div>
    </div>`;
  }).join('');
}

/* ------------------------------------------------------------------- main */

function renderMain(){
  const epLines = EPIGRAPH.split('/').map(t => t.trim()).filter(Boolean);
  const deckLine = `${count('primary')} primary · ${count('secondary')} secondary · ` +
    `${count('deployments')} deployments · ${count('layouts')} layouts · ${count('twists')} twists`;

  const out = [`<div data-testid="missions-view" class="mz-loaded">`];

  out.push(`<header class="rl-mast">
    <div>
      <div class="rl-mast-plate">Missions</div>
      <div class="rl-mast-meta">${esc(EDITION)} · ${esc(DATA.packName)}</div>
      <div class="rl-mast-sub">${esc(deckLine)}</div>
    </div>
    <div class="rl-mast-ep">
      ${epLines.map(l => `<div>${esc(l)}</div>`).join('')}
      <div class="rl-ep-credit">&mdash; tactica imperialis</div>
    </div>
  </header>`);

  out.push(sectionPrimary());
  out.push(sectionSecondary());
  out.push(sectionDeployments());
  out.push(sectionLayouts());
  out.push(sectionPresets());
  out.push(sectionTwists());

  out.push(`<div class="rl-colophon"><hr>
    <p>&#10016; &nbsp;Warhammer 40,000 Missions · Matched Play Deck&nbsp; &#10016;</p></div>`);
  out.push('</div>');
  view.innerHTML = out.join('');
}

function shead(num, title, tag){
  return `<div class="rl-shead">
    <span class="rl-snum">${num}</span>
    <span class="rl-stitle">${esc(title)}</span>
    <span class="rl-stag">${esc(tag)}</span>
  </div>`;
}

function sectionPrimary(){
  const cards = DATA.primary.map(m => `<article id="${m.id}" class="mz-pri">
    <div class="mz-pri-band">${esc(m.name)}<span class="mz-pri-chip">Primary</span></div>
    <div class="mz-pri-body">
      ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
      ${m.brief ? `<p class="mz-brief">${fmt(m.brief)}</p>` : ''}
      ${m.objectives.length ? `<div class="mz-objs">${m.objectives.map(objBlock).join('')}</div>` : ''}
    </div>
  </article>`).join('');
  return `<section class="rl-section" id="sec-primary">
    ${shead('01', 'Primary Missions', `${count('primary')} cards · draw one`)}
    <p class="rl-intro">The primary mission decides how the bulk of your victory points are earned. Draw one &mdash; or agree one &mdash; before deployment.</p>
    <div class="mz-pri-grid">${cards}</div>
  </section>`;
}

function sectionSecondary(){
  const cards = DATA.secondary.map(m => `<article id="${m.id}" class="mz-card">
    <div class="mz-card-head">
      <span class="mz-card-name">${esc(m.name)}</span>
      <span class="mz-badges">
        <span class="mz-badge ${m.fixed ? 'mz-badge--fixed' : 'mz-badge--tactical'}">${m.fixed ? 'Fixed' : 'Tactical'}</span>
        ${m.turn1 ? '<span class="mz-badge mz-badge--turn1">Scores turn 1</span>' : ''}
      </span>
    </div>
    ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
    ${m.brief ? `<p class="mz-brief">${fmt(m.brief)}</p>` : ''}
    ${m.objectives.length ? `<div class="mz-objs">${m.objectives.map(objBlock).join('')}</div>` : ''}
  </article>`).join('');
  return `<section class="rl-section" id="sec-secondary">
    ${shead('02', 'Secondary Missions', `${count('secondary')} cards`)}
    <p class="rl-intro"><b>Fixed</b> missions are chosen before the battle and kept throughout; <b>tactical</b> missions are drawn and discarded as the battle unfolds.</p>
    <div class="mz-card-grid">${cards}</div>
  </section>`;
}

function sectionDeployments(){
  const cards = DATA.deployments.map((d, i) => {
    const map = DEPLOY_MAPS[(d.name || '').trim().toLowerCase()];
    const num = `Dep ${String(i + 1).padStart(2, '0')}`;
    const board = map
      ? `<img class="mz-map" loading="lazy" src="/static/images/deployments/${map.img}" alt="${esc(d.name)} deployment zone map">`
      : '';
    const note = map
      ? `<p class="mz-fig-note">${esc(map.note)}</p>`
      : `<p class="mz-fig-plain">Deployment map &mdash; see the mission pack for the exact zones.</p>`;
    return `<figure id="${d.id}" class="mz-fig">
      <figcaption class="mz-fig-cap"><span class="mz-fig-kind">${num}</span>${esc(d.name)}</figcaption>
      ${board}${note}
    </figure>`;
  }).join('');
  return `<section class="rl-section" id="sec-deployments">
    ${shead('03', 'Deployment Zones', '44″ × 60″ battlefield')}
    <div class="mz-fig-grid">${cards}</div>
  </section>`;
}

/* 45 objective layouts carry no coordinates in the data, so we group them by
   their leading primary-mission family instead of drawing invented markers.
   Each layout keeps its own id anchor so the maps table can jump to it. */
function layoutFamily(name){
  const slash = name.indexOf(' / ');
  return slash >= 0 ? name.slice(0, slash).trim() : (name.split(' - ')[0] || name).trim();
}
function layoutVariant(name){
  const slash = name.indexOf(' / ');
  return slash >= 0 ? name.slice(slash + 3).trim() : name.trim();
}
function sectionLayouts(){
  const fams = [];
  const byFam = new Map();
  for(const x of DATA.layouts){
    const fam = layoutFamily(x.name) || 'Layouts';
    if(!byFam.has(fam)){ byFam.set(fam, []); fams.push(fam); }
    byFam.get(fam).push(x);
  }
  const body = fams.map(fam => {
    const items = byFam.get(fam);
    const cards = items.map((x, i) => {
      const slug = String(x.id).replace(/-/g, '_');
      const plain   = `/static/images/layouts/ic_layout_${slug}.png`;
      const measure = `/static/images/layouts/ic_measurement_layout_${slug}.png`;
      return `<figure id="${x.id}" class="mz-fig mz-lay-fig">
      <figcaption class="mz-fig-cap"><span class="mz-fig-kind">Lay ${String(i + 1).padStart(2, '0')}</span>${esc(layoutVariant(x.name))}</figcaption>
      <img class="mz-map mz-lay-map" loading="lazy" src="${plain}" data-plain="${plain}" data-measure="${measure}" alt="${esc(x.name)} objective layout map">
      <button type="button" class="mz-lay-toggle" data-mode="plan" aria-label="Switch to measured view" title="Show measured distances">
        <span class="mz-lay-toggle-icon" aria-hidden="true">&#8646;</span><span class="mz-lay-toggle-label">Plan</span>
      </button>
    </figure>`;
    }).join('');
    return `<div class="mz-lay-fam">
      <div class="mz-lay-fam-head">${esc(fam)}<span class="mz-lay-fam-count">${items.length} layouts</span></div>
      <div class="mz-fig-grid">${cards}</div>
    </div>`;
  }).join('');
  return `<section class="rl-section" id="sec-layouts">
    ${shead('04', 'Objective Layouts', 'Control range 3″')}
    <p class="rl-intro">Objective-marker layouts pair with the primary missions below. Marker placement follows the mission pack; the maps table sets out which layout each map uses.</p>
    ${body || '<p class="rl-intro">No objective layouts in this pack.</p>'}
  </section>`;
}

function sectionPresets(){
  const depById = Object.fromEntries(DATA.deployments.map(x => [x.id, x]));
  const layById = Object.fromEntries(DATA.layouts.map(x => [x.id, x]));
  const twById  = Object.fromEntries(DATA.twists.map(x => [x.id, x]));
  const rows = DATA.presets.map(m => {
    const dep = depById[m.deployment_id];
    const lay = layById[m.layout_id];
    const tw  = m.twist_id ? twById[m.twist_id] : null;
    return `<tr id="${m.id}">
      <td class="mz-map-name">${esc(m.name)}</td>
      <td>${dep ? `<a class="mz-link" href="#${dep.id}">${esc(dep.name)}</a>` : '<span class="mz-none">—</span>'}</td>
      <td>${lay ? `<a class="mz-link" href="#${lay.id}">${esc(lay.name)}</a>` : '<span class="mz-none">—</span>'}</td>
      <td>${tw ? `<a class="mz-link" href="#${tw.id}">${esc(tw.name)}</a>` : '<span class="mz-none">—</span>'}</td>
    </tr>`;
  }).join('');
  return `<section class="rl-section" id="sec-presets">
    ${shead('05', 'Mission Maps', 'Pre-set combinations')}
    <table class="mz-table">
      <thead><tr><th>Map</th><th>Deployment</th><th>Objective layout</th><th>Twist</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </section>`;
}

function sectionTwists(){
  const cards = DATA.twists.map(m => `<article id="${m.id}" class="mz-card">
    <div class="mz-card-head">
      <span class="mz-card-name">${esc(m.name)}</span>
      <span class="mz-badges"><span class="mz-badge mz-badge--twist">Twist</span></span>
    </div>
    ${m.lore ? `<p class="mz-lore">${esc(m.lore)}</p>` : ''}
    ${m.brief ? `<p class="mz-brief">${fmt(m.brief)}</p>` : ''}
  </article>`).join('');
  return `<section class="rl-section" id="sec-twists">
    ${shead('06', 'Twists', 'Optional · agree before the battle')}
    <div class="mz-card-grid">${cards}</div>
  </section>`;
}

/* ---------------------------------------------------------- jumps + flash */

function chromeOffset(){
  const chrome = document.querySelector('.rl-chrome');
  return (chrome ? chrome.offsetHeight : 122) + 8;
}
function jumpTo(id, push = true){
  const el = document.getElementById(id);
  if(!el) return;
  if(push && ('#' + id) !== location.hash) history.pushState(null, '', '#' + id);
  const y = el.getBoundingClientRect().top + window.scrollY - chromeOffset();
  window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
  el.classList.remove('rl-flash');
  requestAnimationFrame(() => el.classList.add('rl-flash'));
  setTimeout(() => el.classList.remove('rl-flash'), 1700);
}

/* Delegate every in-page #hash link (strip, sidebar, maps table) to jumpTo. */
function bindContentJumps(){
  [stripChipsEl, tocEl, view].forEach(root => {
    root.addEventListener('click', e => {
      const a = e.target.closest('a[href^="#"]');
      if(!a || !root.contains(a)) return;
      e.preventDefault();
      jumpTo(a.getAttribute('href').slice(1));
    });
  });
}

/* Per-card arrow that flips a layout figure between the plan image and the
   measured variant. Delegated on `view`; the measured PNG loads only on the
   first flip (src starts on the plan URL, the measured URL waits in data-). */
function bindLayoutToggles(){
  view.addEventListener('click', e => {
    const btn = e.target.closest('.mz-lay-toggle');
    if(!btn || !view.contains(btn)) return;
    const img = btn.closest('.mz-lay-fig')?.querySelector('.mz-lay-map');
    if(!img) return;
    const toMeasure = btn.getAttribute('data-mode') !== 'measure';
    btn.setAttribute('data-mode', toMeasure ? 'measure' : 'plan');
    img.src = toMeasure ? img.dataset.measure : img.dataset.plain;
    btn.querySelector('.mz-lay-toggle-label').textContent = toMeasure ? 'Measured' : 'Plan';
    btn.setAttribute('aria-label', toMeasure ? 'Switch to plan view' : 'Switch to measured view');
    btn.setAttribute('title', toMeasure ? 'Hide measured distances' : 'Show measured distances');
  });
}

/* Click any deployment / layout map to open it enlarged in the shared
   lightbox. Layout figures open whichever variant is currently shown, since
   we read the image's live src. */
function bindMapZoom(){
  view.addEventListener('click', e => {
    const img = e.target.closest('.mz-map');
    if(!img || !view.contains(img)) return;
    openLightbox(img.currentSrc || img.src, img.alt);
  });
}

window.addEventListener('hashchange', () => {
  const id = location.hash.slice(1);
  if(id) jumpTo(id, false);
});

/* ------------------------------------------------------------- scrollspy */

function bindScrollSpy(){
  const chips = new Map();
  stripChipsEl.querySelectorAll('.rl-chip').forEach(c => chips.set(c.dataset.sec, c));
  const groups = new Map();
  tocEl.querySelectorAll('.mz-toc-group').forEach(g => groups.set(g.dataset.sec, g));

  const obs = new IntersectionObserver(entries => {
    for(const en of entries){
      if(!en.isIntersecting) continue;
      const id = en.target.id;
      if(id === activeSec) continue;
      activeSec = id;
      chips.forEach((c, sid) => c.classList.toggle('is-active', sid === id));
      groups.forEach((g, sid) => g.classList.toggle('is-active', sid === id));
      const g = groups.get(id);
      if(g){
        const gr = g.getBoundingClientRect(), tr = tocEl.getBoundingClientRect();
        if(gr.top < tr.top || gr.bottom > tr.bottom){
          tocEl.scrollTop += (gr.top - tr.top) - tr.height / 2 + gr.height / 2;
        }
      }
    }
  }, { rootMargin: '-12% 0px -70% 0px' });
  view.querySelectorAll('.rl-section').forEach(sec => obs.observe(sec));
}

/* ------------------------------------------------ search / theme / chrome */

function bindStatic(){
  bindSearch();
  bindTheme();
  bindTopButton();
  bindKeyboard();
}

function bindSearch(){
  searchEl.addEventListener('input', () => {
    const q = searchEl.value.trim().toLowerCase();
    tocEl.querySelectorAll('.mz-toc-hits').forEach(el => el.remove());
    firstHit = null;
    if(!q){ tocEl.classList.remove('is-searching'); return; }
    tocEl.classList.add('is-searching');
    const hits = [];
    for(const c of CATS){
      for(const m of (DATA ? DATA[c.key] : []) || []){
        if((m.name || '').toLowerCase().includes(q)) hits.push({ id: m.id, name: m.name, cat: c.label });
      }
    }
    const capped = hits.slice(0, 40);
    firstHit = capped[0] || null;
    const wrap = document.createElement('div');
    wrap.className = 'mz-toc-hits';
    wrap.innerHTML = capped.length
      ? capped.map(h => `<a class="mz-toc-hit" href="#${h.id}">
          <span class="mz-toc-hit-title">${esc(h.name)}</span>
          <span class="mz-toc-hit-cat">${esc(h.cat)}</span></a>`).join('')
      : '<div class="rl-toc-none">No missions match.</div>';
    tocEl.prepend(wrap);
  });
  searchEl.addEventListener('keydown', e => {
    if(e.key === 'Enter' && firstHit){ jumpTo(firstHit.id); searchEl.blur(); }
    else if(e.key === 'Escape'){ searchEl.value = ''; searchEl.dispatchEvent(new Event('input')); searchEl.blur(); }
  });
}

function bindKeyboard(){
  document.addEventListener('keydown', e => {
    const typing = /INPUT|TEXTAREA/.test(document.activeElement?.tagName || '');
    if(e.key === 'Escape') return;   // per-input Escape handled on the input
    if(typing) return;
    if(e.key === '/'){ e.preventDefault(); searchEl.focus(); searchEl.select(); }
  });
}

function readTheme(){
  try{ return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'; }
  catch(e){ return 'light'; }
}
function applyTheme(t){
  if(t === 'dark') document.body.setAttribute('data-rl-theme', 'dark');
  else document.body.removeAttribute('data-rl-theme');
  if(themeLabel) themeLabel.textContent = t === 'dark' ? 'Light' : 'Dark';
}
function bindTheme(){
  themeBtn.addEventListener('click', () => {
    const t = document.body.getAttribute('data-rl-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(t);
    try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
  });
}

function bindTopButton(){
  document.addEventListener('scroll', () => {
    topBtn.classList.toggle('is-shown', window.scrollY > 900);
  }, { passive: true });
  topBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}
