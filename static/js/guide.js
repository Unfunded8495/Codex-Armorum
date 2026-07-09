/* /how-to-play - "How to Play" illustrated walkthrough.
   A static editorial page; this script only adds the interactive polish:
   the sticky quick-nav chips + sidebar scrollspy, a click-to-zoom lightbox
   for every diagram, the shared light/dark reading mode (localStorage
   "caRules.theme", same key as /rules and /missions), and the one dynamic
   piece: a few example objective layouts pulled from /api/missions so the
   UUID-keyed layout images never need hardcoding. */
import { esc } from './utils.js';
import { openLightbox, initLightbox } from './lightbox.js';

const THEME_KEY = 'caRules.theme';

/* Section id + short chip label, in reading order. Ids match the sections
   rendered server-side in guide.html. */
const CHAPTERS = [
  ['ch-need',    'Need'],
  ['ch-muster',  'Muster'],
  ['ch-setup',   'Setup'],
  ['ch-round',   'Battle Round'],
  ['ch-scoring', 'Scoring'],
  ['ch-cp',      'Command'],
  ['ch-first',   'First Game'],
  ['ch-ref',     'Reference'],
];

const stripChipsEl = document.getElementById('gdStripChips');
const tocEl        = document.getElementById('gdToc');
const mainEl       = document.getElementById('gdMain');
const topBtn       = document.getElementById('gdTopBtn');
const themeBtn     = document.getElementById('gdThemeBtn');
const themeLabel   = document.getElementById('gdThemeLabel');
const layoutsEl    = document.getElementById('gdLayouts');

let activeSec = null;

/* ------------------------------------------------------------- reading mode */
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
  if(!themeBtn) return;
  themeBtn.addEventListener('click', () => {
    const t = document.body.getAttribute('data-rl-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(t);
    try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
  });
}

/* ---------------------------------------------------------------- quick nav */
function buildStripChips(){
  stripChipsEl.innerHTML = CHAPTERS
    .map(([id, label]) => `<a class="rl-chip" data-sec="${id}" href="#${id}">${esc(label)}</a>`)
    .join('');
}

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
}

/* Delegate every in-page #hash link (strip chips, sidebar TOC, phase tiles,
   hero buttons) through jumpTo so the sticky chrome offset is respected. */
function bindContentJumps(){
  [stripChipsEl, tocEl, mainEl].forEach(root => {
    if(!root) return;
    root.addEventListener('click', e => {
      const a = e.target.closest('a[href^="#"]');
      if(!a || !root.contains(a)) return;
      e.preventDefault();
      jumpTo(a.getAttribute('href').slice(1));
    });
  });
}

function bindTopButton(){
  document.addEventListener('scroll', () => {
    topBtn.classList.toggle('is-shown', window.scrollY > 900);
  }, { passive: true });
  topBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

window.addEventListener('hashchange', () => {
  const id = location.hash.slice(1);
  if(id) jumpTo(id, false);
});

/* ------------------------------------------------------------- scrollspy */
function bindScrollSpy(){
  const chips = new Map();
  stripChipsEl.querySelectorAll('.rl-chip').forEach(c => chips.set(c.dataset.sec, c));
  const links = new Map();
  tocEl.querySelectorAll('.gd-toc-link').forEach(a => {
    links.set(a.getAttribute('href').slice(1), a);
  });

  const obs = new IntersectionObserver(entries => {
    for(const en of entries){
      if(!en.isIntersecting) continue;
      const id = en.target.id;
      if(id === activeSec) continue;
      activeSec = id;
      chips.forEach((c, sid) => c.classList.toggle('is-active', sid === id));
      links.forEach((a, sid) => a.classList.toggle('is-active', sid === id));
    }
  }, { rootMargin: '-14% 0px -70% 0px' });
  mainEl.querySelectorAll('.gd-section').forEach(sec => obs.observe(sec));
}

/* ------------------------------------------------------------- lightbox */
function bindFigZoom(){
  mainEl.addEventListener('click', e => {
    const img = e.target.closest('.gd-fig-img');
    if(!img || !mainEl.contains(img)) return;
    openLightbox(img.currentSrc || img.src, img.dataset.cap || img.alt || '');
  });
}

/* -------------------------------------------------- example layout maps */
/* Layout image files are keyed by the mission_layout UUID, so we cannot
   hardcode them (they change with each w40k.db update). Pull the layout list
   from /api/missions and render the first layout from each of a few distinct
   primary-mission families, reusing the same slug scheme as /missions. */
function layoutFamily(name){
  const slash = (name || '').indexOf(' / ');
  if(slash >= 0) return name.slice(0, slash).trim();
  return ((name || '').split(' - ')[0] || name || '').trim();
}
function layoutVariant(name){
  const slash = (name || '').indexOf(' / ');
  return slash >= 0 ? name.slice(slash + 3).trim() : (name || '').trim();
}

function renderLayouts(layouts){
  const seen = new Set();
  const picks = [];
  for(const x of layouts){
    const fam = layoutFamily(x.name) || 'Layout';
    if(seen.has(fam)) continue;
    seen.add(fam);
    picks.push(x);
    if(picks.length >= 3) break;
  }
  if(!picks.length){ layoutsEl.remove(); return; }

  layoutsEl.innerHTML = picks.map(x => {
    const slug    = String(x.id).replace(/-/g, '_');
    const plain   = `/static/images/layouts/ic_layout_${slug}.png`;
    const measure = `/static/images/layouts/ic_measurement_layout_${slug}.png`;
    // caption with the primary-mission family (one card per family), so the
    // three examples read as distinct maps rather than repeating a variant name
    const cap     = layoutFamily(x.name) || layoutVariant(x.name) || 'Objective layout';
    return `<figure class="gd-fig gd-lay-fig">
      <img class="gd-fig-img gd-map gd-lay-map" loading="lazy" src="${plain}"
           data-plain="${plain}" data-measure="${measure}" data-cap="${esc(cap)}"
           alt="${esc(x.name)} objective layout"
           onerror="this.closest('figure').remove()">
      <figcaption class="gd-fig-cap">${esc(cap)}</figcaption>
      <button type="button" class="gd-lay-toggle" data-mode="plan"
              aria-label="Switch to measured view" title="Show measured distances">
        <span aria-hidden="true">&#8646;</span><span class="gd-lay-toggle-label">Plan</span>
      </button>
    </figure>`;
  }).join('');
}

/* Flip a layout figure between the plan image and the measured variant.
   The measured PNG loads only on the first flip (src starts on plan). */
function bindLayoutToggles(){
  layoutsEl.addEventListener('click', e => {
    const btn = e.target.closest('.gd-lay-toggle');
    if(!btn) return;
    const img = btn.closest('.gd-lay-fig')?.querySelector('.gd-lay-map');
    if(!img) return;
    const toMeasure = btn.getAttribute('data-mode') !== 'measure';
    btn.setAttribute('data-mode', toMeasure ? 'measure' : 'plan');
    img.src = toMeasure ? img.dataset.measure : img.dataset.plain;
    btn.querySelector('.gd-lay-toggle-label').textContent = toMeasure ? 'Measured' : 'Plan';
    btn.setAttribute('aria-label', toMeasure ? 'Switch to plan view' : 'Switch to measured view');
    btn.setAttribute('title', toMeasure ? 'Hide measured distances' : 'Show measured distances');
  });
}

async function loadLayouts(){
  if(!layoutsEl) return;
  try{
    const res = await fetch('/api/missions');
    if(!res.ok) throw new Error('missions ' + res.status);
    const data = await res.json();
    renderLayouts(Array.isArray(data.layouts) ? data.layouts : []);
  }catch(e){
    layoutsEl.innerHTML = `<p class="gd-loading">Example layouts unavailable. See the <a href="/missions">Missions</a> page for all maps.</p>`;
  }
}

/* --------------------------------------------------------------- boot */
applyTheme(readTheme());  // before first paint (no flash)
buildStripChips();
bindTheme();
bindContentJumps();
bindTopButton();
bindScrollSpy();
bindFigZoom();
bindLayoutToggles();
initLightbox();
loadLayouts();

if(location.hash){ jumpTo(location.hash.slice(1), false); }
