/* Data changelog page - one entry per rules-data update or source
   migration, newest first, in the Core Rules reader skin. Renders
   /api/changelog (built by scripts/build_changelog.py from the per-update
   records in docs/data_updates/). Shares the /rules reading mode. */
import { esc } from './utils.js';

const main = document.getElementById('clMain');
const tocEl = document.getElementById('clToc');
const tocCountEl = document.getElementById('clTocCount');
const versionChipEl = document.getElementById('clVersionChip');
const topBtn = document.getElementById('clTopBtn');
const themeBtn = document.getElementById('clThemeBtn');
const themeLabel = document.getElementById('clThemeLabel');

let DATA = null;

const THEME_KEY = 'caRules.theme';   // shared with /rules: one reading mode

applyTheme(readTheme());
init();

async function init(){
  try{
    const r = await fetch('/api/changelog');
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    DATA = await r.json();
  }catch(err){
    main.innerHTML = `<div class="rl-error">Failed to load the changelog (${esc(String(err))}).
      Run <code>python scripts/build_changelog.py</code> and reload.</div>`;
    return;
  }
  renderVersionChip(DATA);
  renderMain(DATA);
  renderToc(DATA);
  bindContent();
  bindScrollSpy();
  bindTheme();
  bindTopButton();
  if(location.hash) initialJump(location.hash.slice(1));
}

/* ---------------------------------------------------------------- render */

function currentVersion(data){
  for(const e of data.entries){
    const m = /->\s*(\d+)/.exec(e.versions || '');
    if(m) return m[1];
  }
  return null;
}

function renderVersionChip(data){
  const v = currentVersion(data);
  if(v) versionChipEl.innerHTML =
    `<span class="rl-chip cl-version-chip">data_version ${esc(v)}</span>`;
}

function renderMain(data){
  const out = [];
  const v = currentVersion(data);
  out.push(`<header class="rl-mast">
    <div>
      <div class="rl-mast-plate">Changelog</div>
      <div class="rl-mast-meta">Warhammer 40,000 &middot; 11th Edition &middot; Rules-data updates and source migrations</div>
      <div class="rl-mast-note"><span class="rt-cmt-badge">Records</span>
        <span>${data.entries.length} entries, newest first.
        ${v ? `The catalogue currently runs official app data_version <strong>${esc(v)}</strong>.` : ''}
        Every refresh of <code>data/w40k/w40k.db</code> gets a full field-level record here.</span></div>
    </div>
  </header>`);

  for(const e of data.entries) out.push(entryHtml(e));

  out.push(`<div class="rl-colophon"><hr>
    <p>&#10016; &nbsp;Changelog &middot; rules-data updates &middot; 11th Edition&nbsp; &#10016;</p></div>`);
  main.innerHTML = out.join('');
}

function entryHtml(e){
  const badge = `<span class="cl-kind cl-kind--${esc(e.kind.replace(' ', '-'))}">${esc(e.kind)}</span>`;
  const versions = e.versions
    ? `<span class="cl-versions">${esc(e.versions)}</span>` : '';
  return `<section class="rl-section" id="${e.slug}">
    <h2 class="rl-shead"><span class="rl-stitle">${esc(e.title)}</span>
      <span class="rl-stag">${esc(e.dateLabel)}</span></h2>
    <div class="rl-secwrap"><div class="rl-body">
      <p class="cl-plate">${badge}${versions}
        ${e.summary ? `<span class="cl-summary">${esc(e.summary)}</span>` : ''}</p>
      ${e.html}
    </div></div>
  </section>`;
}

function renderToc(data){
  const out = [];
  for(const e of data.entries){
    const rules = (e.toc || []).map(t=>
      `<a class="rl-toc-rule" href="#${t.id}">
         <span class="rl-toc-ref">&middot;</span>${esc(t.title)}</a>`).join('');
    out.push(`<div class="rl-toc-group" data-sec="${e.slug}">
      <a class="rl-toc-sec" href="#${e.slug}">
        <span class="rl-toc-title">${esc(e.dateLabel)} &middot; ${esc(shortTitle(e))}</span>
        ${rules ? '<span class="rl-toc-caret" title="Expand">&#9656;</span>' : ''}
      </a>
      ${rules ? `<div class="rl-toc-rules">${rules}</div>` : ''}
    </div>`);
  }
  tocEl.innerHTML = out.join('');
  tocCountEl.textContent = `${data.entries.length} entries`;

  tocEl.addEventListener('click', e=>{
    if(e.target.classList.contains('rl-toc-caret')){
      e.preventDefault();
      e.stopPropagation();
      e.target.closest('.rl-toc-group').classList.toggle('is-open');
      return;
    }
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

function shortTitle(e){
  const m = /->\s*(\d+)/.exec(e.versions || '');
  if(m && e.kind === 'data update') return `to ${m[1]}`;
  return e.title.split(':')[0];
}

/* ------------------------------------------------------------ navigation */

function bindContent(){
  main.addEventListener('click', e=>{
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

function chromeOffset(){
  const chrome = document.querySelector('.rl-chrome');
  return (chrome ? chrome.offsetHeight : 104) + 8;
}

function initialJump(id){
  try{ history.scrollRestoration = 'manual'; }catch(e){}
  jumpTo(id, false, false);
  let ticks = 8;
  const timer = setInterval(()=>{
    const el = document.getElementById(id);
    if(!el || --ticks < 0) return clearInterval(timer);
    if(Math.abs(el.getBoundingClientRect().top - chromeOffset()) > 60){
      jumpTo(id, false, false);
    }
  }, 500);
  window.addEventListener('wheel', ()=>clearInterval(timer), {once: true, passive: true});
  window.addEventListener('touchmove', ()=>clearInterval(timer), {once: true, passive: true});
}

function jumpTo(id, push = true, smooth = true){
  const el = document.getElementById(id);
  if(!el) return;
  if(push && ('#' + id) !== location.hash) history.pushState(null, '', '#' + id);
  const y = el.getBoundingClientRect().top + window.scrollY - chromeOffset();
  window.scrollTo({top: Math.max(0, y), behavior: smooth ? 'smooth' : 'auto'});
  el.classList.remove('rl-flash');
  requestAnimationFrame(()=>el.classList.add('rl-flash'));
  setTimeout(()=>el.classList.remove('rl-flash'), 1700);
}

window.addEventListener('hashchange', ()=>{
  const id = location.hash.slice(1);
  if(id) jumpTo(id, false);
});

/* ------------------------------------------------------------- scrollspy */

function bindScrollSpy(){
  const groups = new Map();
  tocEl.querySelectorAll('.rl-toc-group').forEach(g=>groups.set(g.dataset.sec, g));

  const obs = new IntersectionObserver(entries=>{
    for(const en of entries){
      if(!en.isIntersecting) continue;
      const id = en.target.id;
      tocEl.querySelectorAll('.rl-toc-group.is-active').forEach(x=>{
        if(x.dataset.sec !== id) x.classList.remove('is-active', 'is-open');
      });
      const g = groups.get(id);
      if(g){
        g.classList.add('is-active', 'is-open');
        const gr = g.getBoundingClientRect(), tr = tocEl.getBoundingClientRect();
        if(gr.top < tr.top || gr.bottom > tr.bottom){
          tocEl.scrollTop += (gr.top - tr.top) - tr.height / 2 + gr.height / 2;
        }
      }
    }
  }, {rootMargin: '-12% 0px -78% 0px'});
  main.querySelectorAll('.rl-section').forEach(sec=>obs.observe(sec));
}

/* ----------------------------------------------------- theme + top button */

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
  themeBtn.addEventListener('click', ()=>{
    const t = document.body.getAttribute('data-rl-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(t);
    try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
  });
}

function bindTopButton(){
  document.addEventListener('scroll', ()=>{
    topBtn.classList.toggle('is-shown', window.scrollY > 900);
  }, {passive:true});
  topBtn.addEventListener('click', ()=>window.scrollTo({top:0, behavior:'smooth'}));
}
