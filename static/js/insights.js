/* Rules Insights page - community articles (Rules Deep Dive, Ruleshammer,
   Hammer of Math) in the Core Rules reader skin. Renders /api/insights
   (built by scripts/build_insights.py): series dividers, one section per
   article, searchable TOC, scrollspy, shared light/dark reading mode.
   Rule links inside articles point at /rules#anchor; their hover tooltips
   are hydrated from /api/rules so terms read the same as on that page. */
import { esc } from './utils.js';

const main = document.getElementById('insMain');
const tocEl = document.getElementById('insToc');
const tocCountEl = document.getElementById('insTocCount');
const searchEl = document.getElementById('insSearch');
const tipEl = document.getElementById('insTooltip');
const topBtn = document.getElementById('insTopBtn');
const seriesChipsEl = document.getElementById('insSeriesChips');
const themeBtn = document.getElementById('insThemeBtn');
const themeLabel = document.getElementById('insThemeLabel');

let DATA = null;
let RULES = null;    // /api/rules payload, tooltips only; page works without

const THEME_KEY = 'caRules.theme';   // shared with /rules: one reading mode

applyTheme(readTheme());
init();

async function init(){
  try{
    const r = await fetch('/api/insights');
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    DATA = await r.json();
  }catch(err){
    main.innerHTML = `<div class="rl-error">Failed to load the Rules Insights (${esc(String(err))}).
      Run <code>python scripts/build_insights.py</code> and reload.</div>`;
    return;
  }
  renderMain(DATA);
  renderToc(DATA);
  renderChips(DATA);
  bindContent();
  bindSearch();
  bindScrollSpy();
  bindTheme();
  bindTopButton();
  bindKeyboard();
  if(location.hash) initialJump(location.hash.slice(1));
  fetch('/api/rules').then(r=>r.ok ? r.json() : null)
    .then(d=>{ RULES = d; })
    .catch(()=>{});
}

/* ---------------------------------------------------------------- render */

function readTime(words){
  return `${Math.max(1, Math.round(words / 220))} min`;
}

function renderMain(data){
  const out = [];
  out.push(`<header class="rl-mast">
    <div>
      <div class="rl-mast-plate">Rules Insights</div>
      <div class="rl-mast-meta">Warhammer 40,000 &middot; 11th Edition &middot; Community articles, kept locally</div>
      <div class="rl-mast-note"><span class="rt-cmt-badge">Commentary</span>
        <span>${data.articles.length} community deep dives feed the notes on the
        <a class="ins-xref" href="/rules">Core Rules</a> page. Insight and opinion, not official rules text.</span></div>
    </div>
  </header>`);

  for(const s of data.series){
    const arts = data.articles.filter(a=>a.seriesId === s.id);
    if(!arts.length) continue;
    out.push(`<section class="rl-part" id="${s.id}">
      <p class="rl-part-kicker">Article Series</p>
      <h2 class="rl-part-title">${esc(s.title)}</h2>
      ${s.blurb ? `<p class="ins-part-blurb">${esc(s.blurb)}</p>` : ''}
    </section>`);
    for(const a of arts) out.push(articleHtml(a));
  }
  const listed = new Set(data.series.map(s=>s.id));
  for(const a of data.articles) if(!listed.has(a.seriesId)) out.push(articleHtml(a));

  out.push(`<div class="rl-colophon"><hr>
    <p>&#10016; &nbsp;Rules Insights &middot; community articles &middot; 11th Edition&nbsp; &#10016;</p></div>`);
  main.innerHTML = out.join('');
}

function articleHtml(a){
  return `<section class="rl-section" id="${a.slug}">
    <h2 class="rl-shead"><span class="rl-stitle">${esc(a.title)}</span>
      <span class="rl-stag">${esc(a.series)} &middot; ${readTime(a.words)}</span></h2>
    <div class="rl-secwrap"><div class="rl-body">${a.html}</div></div>
  </section>`;
}

function renderToc(data){
  const out = [];
  const bySeries = new Map(data.series.map(s=>[s.id, []]));
  for(const a of data.articles){
    if(!bySeries.has(a.seriesId)) bySeries.set(a.seriesId, []);
    bySeries.get(a.seriesId).push(a);
  }
  const titles = new Map(data.series.map(s=>[s.id, s.title]));
  for(const [sid, arts] of bySeries){
    if(!arts.length) continue;
    out.push(`<div class="rl-toc-part">${esc(titles.get(sid) || arts[0].series)}</div>`);
    for(const a of arts){
      const rules = (a.toc || []).map(t=>
        `<a class="rl-toc-rule" href="#${t.id}">
           <span class="rl-toc-ref">${t.ref || '&middot;'}</span>${esc(t.title)}</a>`).join('');
      out.push(`<div class="rl-toc-group" data-sec="${a.slug}">
        <a class="rl-toc-sec" href="#${a.slug}">
          <span class="rl-toc-title">${esc(shortTitle(a))}</span>
          ${rules ? '<span class="rl-toc-caret" title="Expand">&#9656;</span>' : ''}
        </a>
        ${rules ? `<div class="rl-toc-rules">${rules}</div>` : ''}
      </div>`);
    }
  }
  tocEl.innerHTML = out.join('');
  tocCountEl.textContent = `${data.articles.length} articles`;

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

function shortTitle(a){
  return a.title.replace(`${a.series}: `, '');
}

function renderChips(data){
  seriesChipsEl.innerHTML = data.series
    .filter(s=>data.articles.some(a=>a.seriesId === s.id))
    .map(s=>`<a class="rl-chip" data-sec="${s.id}" href="#${s.id}">${esc(s.title)}</a>`).join('');
  document.getElementById('insStrip').addEventListener('click', e=>{
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

/* ------------------------------------------------- tooltips + navigation */

function bindContent(){
  let hideTimer = null;

  main.addEventListener('mouseover', e=>{
    const a = e.target.closest('[data-a]');
    if(!a || !main.contains(a)) return;
    clearTimeout(hideTimer);
    showTip(a);
  });
  main.addEventListener('mouseout', e=>{
    if(!e.target.closest('[data-a]')) return;
    hideTimer = setTimeout(()=>{ tipEl.hidden = true; }, 60);
  });
  document.addEventListener('scroll', ()=>{ tipEl.hidden = true; }, {passive:true});

  // same-page anchors jump smoothly; /rules#… links navigate normally
  main.addEventListener('click', e=>{
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

function showTip(a){
  if(!RULES) return;
  const aid = a.dataset.a;
  const title = RULES.titles?.[aid] || '';
  const tip = RULES.tips?.[aid] || '';
  if(!title && !tip) return;
  tipEl.innerHTML = `
    <div class="rl-tip-head">${esc(title)}</div>
    ${tip ? `<div class="rl-tip-body">${esc(tip)}</div>` : ''}
    <div class="rl-tip-foot">Click to open in the Core Rules</div>`;
  tipEl.hidden = false;

  const r = a.getBoundingClientRect();
  const tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
  let x = r.left + r.width / 2 - tw / 2;
  x = Math.max(10, Math.min(x, window.innerWidth - tw - 10));
  let y = r.top - th - 10;
  if(r.top < 250) y = r.bottom + 10;
  tipEl.style.left = `${x}px`;
  tipEl.style.top = `${y}px`;
}

/* ---------------------------------------------------------------- search */

function bindSearch(){
  const index = [];
  for(const a of DATA.articles){
    index.push({id: a.slug, ref: '&sect;', title: shortTitle(a), sec: a.series});
    for(const t of (a.toc || []))
      index.push({id: t.id, ref: t.ref || '&middot;', title: t.title, sec: shortTitle(a)});
  }

  let results = [];
  searchEl.addEventListener('input', ()=>{
    const q = searchEl.value.trim().toLowerCase();
    tocEl.querySelectorAll('.rl-toc-hit').forEach(el=>el.remove());
    if(!q){
      tocEl.classList.remove('is-searching');
      return;
    }
    tocEl.classList.add('is-searching');
    results = index.filter(e=>
      e.title.toLowerCase().includes(q) || (e.ref || '').startsWith(q)).slice(0, 40);
    const wrap = document.createElement('div');
    wrap.className = 'rl-toc-hit';
    wrap.innerHTML = results.length
      ? results.map(e=>
          `<a class="rl-toc-rule" href="#${e.id}">
             <span class="rl-toc-ref">${e.ref}</span><span class="rl-toc-title">${esc(e.title)}</span>
             <span class="rl-toc-sec-tag">${esc(e.sec)}</span></a>`).join('')
      : '<div class="rl-toc-none">No articles match.</div>';
    tocEl.prepend(wrap);
  });

  searchEl.addEventListener('keydown', e=>{
    if(e.key === 'Enter' && results.length){
      jumpTo(results[0].id);
      searchEl.blur();
    }else if(e.key === 'Escape'){
      searchEl.value = '';
      searchEl.dispatchEvent(new Event('input'));
      searchEl.blur();
    }
  });
}

/* ------------------------------------------------------------- keyboard */

function bindKeyboard(){
  document.addEventListener('keydown', e=>{
    const typing = /INPUT|TEXTAREA/.test(document.activeElement?.tagName || '');
    if(typing || e.key !== '/') return;
    e.preventDefault();
    searchEl.focus();
    searchEl.select();
  });
}

/* ----------------------------------------------------------- navigation */

function chromeOffset(){
  const chrome = document.querySelector('.rl-chrome');
  return (chrome ? chrome.offsetHeight : 104) + 8;
}

/* Initial-load deep link: the browser's own scroll restoration / late
   fragment scroll can fire after our async render and stomp the position,
   so jump instantly now and re-assert shortly after if it drifted. */
function initialJump(id){
  try{ history.scrollRestoration = 'manual'; }catch(e){}
  // no requestAnimationFrame here: it never fires while the tab is hidden,
  // and the content is already rendered synchronously by this point. Jump
  // now, then re-assert once in case the browser's own late fragment scroll
  // or scroll restoration stomps the position.
  jumpTo(id, false, false);
  // fonts and lazy images above the target keep reflowing 70k+ px of page
  // for a while after load, so keep settling briefly until the position
  // holds (bounded; a user scroll cancels it)
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
  const chips = new Map();
  seriesChipsEl.querySelectorAll('.rl-chip').forEach(c=>chips.set(c.dataset.sec, c));
  const seriesOf = new Map(DATA.articles.map(a=>[a.slug, a.seriesId]));

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
      const sid = seriesOf.get(id) || id;
      chips.forEach((c, cid)=>c.classList.toggle('is-active', cid === sid));
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
