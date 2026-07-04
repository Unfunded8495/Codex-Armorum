/* Core Rules reference page — "PDF style" redesign (Variant A · Manual).
   Renders /api/rules (built by scripts/build_rules.py) with:
   searchable TOC, quick-reference strip (battle round + attack sequence),
   hover tooltips, click-to-pin rule cards, an A-Z index overlay (G),
   scrollspy, and a light/dark reading-mode toggle. */
import { esc } from './utils.js';

const main = document.getElementById('rlMain');
const tocEl = document.getElementById('rlToc');
const tocCountEl = document.getElementById('rlTocCount');
const searchEl = document.getElementById('rlSearch');
const tipEl = document.getElementById('rlTooltip');
const topBtn = document.getElementById('rlTopBtn');
const phaseChipsEl = document.getElementById('rlPhaseChips');
const attackChipsEl = document.getElementById('rlAttackChips');
const attackLabelEl = document.getElementById('rlAttackLabel');
const pinsEl = document.getElementById('rlPins');
const pinsStackEl = document.getElementById('rlPinsStack');
const pinsCountEl = document.getElementById('rlPinsCount');
const pinsClearEl = document.getElementById('rlPinsClear');
const glossEl = document.getElementById('rlGlossary');
const glossListEl = document.getElementById('rlGlossList');
const glossLettersEl = document.getElementById('rlGlossLetters');
const glossSearchEl = document.getElementById('rlGlossSearch');
const glossCountEl = document.getElementById('rlGlossCount');
const glossCloseEl = document.getElementById('rlGlossClose');
const indexBtn = document.getElementById('rlIndexBtn');
const themeBtn = document.getElementById('rlThemeBtn');
const themeLabel = document.getElementById('rlThemeLabel');

let DATA = null;
let GLOSSARY = [];      // [{aid, title, ref, tip}] sorted by title
let PINS = [];          // [{aid, title, ref, tip}] newest first, cap 5

const THEME_KEY = 'caRules.theme';
const PIN_CAP = 5;
const ROMANS = ['I', 'II', 'III', 'IV', 'V', 'VI'];

applyTheme(readTheme());   // before first paint — no flash
init();

async function init(){
  let data;
  try{
    const r = await fetch('/api/rules');
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
  }catch(err){
    main.innerHTML = `<div class="rl-error">Failed to load the Core Rules (${esc(String(err))}).
      Run <code>python scripts/build_rules.py</code> and reload.</div>`;
    return;
  }
  DATA = data;
  buildGlossary();
  renderMain(data);
  renderToc(data);
  renderStrip(data);
  bindContent();
  bindSearch();
  bindScrollSpy();
  bindPins();
  bindGlossary();
  bindTheme();
  bindTopButton();
  bindKeyboard();
  if(location.hash) jumpTo(location.hash.slice(1), false);
}

/* ---------------------------------------------------------------- render */

function renderMain(data){
  const secById = Object.fromEntries(data.sections.map(s=>[s.id, s]));
  const partOf = {};
  for(const p of data.parts) for(const sid of p.sections) partOf[sid] = p.title;
  const out = [];

  const epLines = (data.epigraph || '').split('/').map(t=>t.trim()).filter(Boolean);
  out.push(`<header class="rl-mast">
    <div>
      <div class="rl-mast-plate">Core Rules</div>
      <div class="rl-mast-meta">Warhammer 40,000 &middot; 11th Edition &middot; Combined app + PDF ruleset</div>
      ${data.meta?.commentary ? `<div class="rl-mast-note"><span class="rt-cmt-badge">Commentary</span>
        <span>${data.meta.commentary} community notes ride alongside the official text &mdash; clearly separated, never mixed.</span></div>` : ''}
    </div>
    ${epLines.length ? `<div class="rl-mast-ep">
      ${epLines.map(l=>`<div>${esc(l)}</div>`).join('')}
      <div class="rl-ep-credit">&mdash; the litany of war</div>
    </div>` : ''}
  </header>`);

  const intro = secById['intro'];
  if(intro) out.push(sectionHtml(intro, partOf));

  data.parts.forEach((part, i)=>{
    out.push(`<section class="rl-part" id="${part.id}">
      <p class="rl-part-kicker">Part ${ROMANS[i] || i + 1}</p>
      <h2 class="rl-part-title">${esc(part.title)}</h2>
    </section>`);
    for(const sid of part.sections){
      const sec = secById[sid];
      if(sec) out.push(sectionHtml(sec, partOf));
    }
  });

  out.push(`<div class="rl-colophon"><hr>
    <p>&#10016; &nbsp;Warhammer 40,000 Core Rules &middot; 11th Edition&nbsp; &#10016;</p></div>`);
  main.innerHTML = out.join('');
}

function sectionHtml(sec, partOf){
  const num = sec.num ? `<span class="rl-snum">${sec.num}</span>` : '';
  const tag = partOf[sec.id] ? `<span class="rl-stag">${esc(partOf[sec.id])}</span>` : '';
  return `<section class="rl-section" id="${sec.id}">
    <h2 class="rl-shead">${num}<span class="rl-stitle">${esc(sec.title)}</span>${tag}</h2>
    <div class="rl-secwrap"><div class="rl-body">${sec.html}</div></div>
  </section>`;
}

function renderToc(data){
  const secById = Object.fromEntries(data.sections.map(s=>[s.id, s]));
  const out = [];
  const intro = secById['intro'];
  if(intro) out.push(tocSection(intro, '§'));
  for(const part of data.parts){
    out.push(`<div class="rl-toc-part">${esc(part.title)}</div>`);
    for(const sid of part.sections){
      const sec = secById[sid];
      if(sec) out.push(tocSection(sec, sec.num || '§'));
    }
  }
  tocEl.innerHTML = out.join('');
  tocCountEl.textContent = `${data.sections.length} sections`;

  tocEl.addEventListener('click', e=>{
    if(e.target.classList.contains('rl-toc-caret')){
      e.preventDefault();
      e.stopPropagation();
      e.target.closest('.rl-toc-group').classList.toggle('is-open');
    }
  });
}

function tocSection(sec, num){
  const rules = (sec.toc || []).map(t=>
    `<a class="rl-toc-rule" href="#${t.id}" data-ref="${t.ref}">
       <span class="rl-toc-ref">${t.ref}</span>${esc(t.title)}</a>`).join('');
  return `<div class="rl-toc-group" data-sec="${sec.id}">
    <a class="rl-toc-sec" href="#${sec.id}">
      <span class="rl-toc-num">${num}</span><span class="rl-toc-title">${esc(sec.title)}</span>
      ${rules ? '<span class="rl-toc-caret" title="Expand">&#9656;</span>' : ''}
    </a>
    ${rules ? `<div class="rl-toc-rules">${rules}</div>` : ''}
  </div>`;
}

/* --------------------------------------------------- quick-reference strip */

function renderStrip(data){
  const secById = Object.fromEntries(data.sections.map(s=>[s.id, s]));
  const br = data.parts.find(p=>p.id === 'the-battle-round');
  const phases = (br ? br.sections : [])
    .map(id=>secById[id]).filter(Boolean)
    .filter(s=>/ Phase$/.test(s.title));
  phaseChipsEl.innerHTML = phases.map(s=>
    `<a class="rl-chip" data-sec="${s.id}" href="#${s.id}"><b>${s.num}</b>${esc(s.title.replace(' Phase',''))}</a>`).join('');

  const s05 = secById['s05'];
  const steps = (s05 && s05.toc ? s05.toc.slice(0, 4) : []);
  attackChipsEl.innerHTML = steps.map((t, i)=>{
    const label = t.title.replace(' Rolls','').replace('Inflict ','');
    const sep = i < steps.length - 1 ? '<span class="rl-chip-sep">&rsaquo;</span>' : '';
    return `<a class="rl-chip rl-chip--step" href="#${t.id}">${esc(label)}${sep}</a>`;
  }).join('');

  document.getElementById('rlStrip').addEventListener('click', e=>{
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

/* -------------------------------------------------- content: tips + pins */

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

  // click a dotted reference: pin it; ctrl/cmd-click: jump. Other #links jump.
  main.addEventListener('click', e=>{
    const pinA = e.target.closest('a[data-a]');
    if(pinA){
      e.preventDefault();
      if(e.ctrlKey || e.metaKey) jumpTo(pinA.dataset.a);
      else addPin(pinA.dataset.a);
      return;
    }
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

function showTip(a){
  const aid = a.dataset.a;
  const title = DATA.titles[aid] || '';
  const tip = DATA.tips[aid] || '';
  if(!title && !tip) return;
  const ref = refOf(aid);
  tipEl.innerHTML = `
    <div class="rl-tip-head">${esc(title)}${ref ? `<span>${ref}</span>` : ''}</div>
    ${tip ? `<div class="rl-tip-body">${esc(tip)}</div>` : ''}
    <div class="rl-tip-foot">Click to pin &middot; Ctrl-click to jump</div>`;
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

function bindPins(){
  pinsClearEl.addEventListener('click', ()=>{ PINS = []; renderPins(); });
  pinsStackEl.addEventListener('click', e=>{
    const card = e.target.closest('[data-aid]');
    if(!card) return;
    const aid = card.dataset.aid;
    if(e.target.closest('.rl-pin-x')){
      PINS = PINS.filter(p=>p.aid !== aid);
      renderPins();
    }else if(e.target.closest('.rl-pin-open')){
      jumpTo(aid);
    }
  });
}

function addPin(aid){
  const title = DATA.titles[aid] || aid;
  const tip = DATA.tips[aid] || '';
  PINS = [{aid, title, ref: refOf(aid), tip},
          ...PINS.filter(p=>p.aid !== aid)].slice(0, PIN_CAP);
  tipEl.hidden = true;
  renderPins();
}

function renderPins(){
  pinsEl.hidden = PINS.length === 0;
  pinsCountEl.textContent = `Pinned · ${PINS.length}`;
  pinsStackEl.innerHTML = PINS.map(p=>{
    const tip = p.tip.length > 220 ? p.tip.slice(0, 220) + '…' : p.tip;
    return `<div class="rl-pin" data-aid="${p.aid}">
      <div class="rl-pin-head">
        <span class="rl-pin-title">${esc(p.title)}</span>
        <span class="rl-pin-ref">${p.ref}</span>
        <button type="button" class="rl-pin-x" title="Unpin">&#10005;</button>
      </div>
      ${tip ? `<div class="rl-pin-tip">${esc(tip)}</div>` : ''}
      <button type="button" class="rl-pin-open">Open rule &rarr;</button>
    </div>`;
  }).join('');
}

/* ------------------------------------------------------- index / glossary */

function buildGlossary(){
  GLOSSARY = Object.entries(DATA.titles || {})
    .filter(([aid, title])=>title && !/^dg-/.test(aid))
    .map(([aid, title])=>({aid, title, ref: refOf(aid), tip: (DATA.tips || {})[aid] || ''}))
    .sort((a, b)=>a.title.localeCompare(b.title));
}

function bindGlossary(){
  indexBtn.addEventListener('click', openGlossary);
  glossCloseEl.addEventListener('click', closeGlossary);
  glossEl.addEventListener('click', e=>{ if(e.target === glossEl) closeGlossary(); });
  glossSearchEl.addEventListener('input', renderGlossary);
  glossLettersEl.addEventListener('click', e=>{
    const b = e.target.closest('button[data-letter]');
    if(!b) return;
    const el = document.getElementById(`gloss-${b.dataset.letter}`);
    if(el) glossListEl.scrollTop += el.getBoundingClientRect().top - glossListEl.getBoundingClientRect().top - 6;
  });
  glossListEl.addEventListener('click', e=>{
    const row = e.target.closest('a[data-aid]');
    if(!row) return;
    e.preventDefault();
    closeGlossary();
    setTimeout(()=>jumpTo(row.dataset.aid), 40);
  });
  glossCountEl.textContent = `${GLOSSARY.length} entries`;
}

function openGlossary(){
  renderGlossary();
  glossEl.hidden = false;
  document.body.style.overflow = 'hidden';
  glossSearchEl.focus();
}
function closeGlossary(){
  glossEl.hidden = true;
  document.body.style.overflow = '';
}

function renderGlossary(){
  const q = glossSearchEl.value.trim().toLowerCase();
  const entries = q ? GLOSSARY.filter(e=>e.title.toLowerCase().includes(q)) : GLOSSARY;
  const groups = new Map();
  for(const e of entries){
    const c = (e.title[0] || '#').toUpperCase();
    const key = /[A-Z]/.test(c) ? c : '#';
    if(!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  glossLettersEl.innerHTML = [...groups.keys()]
    .map(L=>`<button type="button" data-letter="${L}">${L}</button>`).join('');
  glossListEl.innerHTML = entries.length
    ? [...groups.entries()].map(([L, list])=>`<div id="gloss-${L}">
        <div class="rl-gloss-letter">${L}</div>
        ${list.map(e=>`<a class="rl-gloss-row" href="#${e.aid}" data-aid="${e.aid}">
          <span class="rl-gloss-term">${esc(e.title)}</span>
          <span class="rl-gloss-ref">${e.ref}</span>
          <span class="rl-gloss-snippet">${esc(e.tip.slice(0, 110))}</span>
        </a>`).join('')}
      </div>`).join('')
    : '<div class="rl-gloss-none">No terms match.</div>';
  glossListEl.scrollTop = 0;
}

function refOf(aid){
  let m = aid.match(/^r(\d\d)-(\d\d)$/); if(m) return `${m[1]}.${m[2]}`;
  m = aid.match(/^s(\d\d)$/); if(m) return `${m[1]}.00`;
  m = aid.match(/^s(\d\d)-/); if(m) return m[1];
  if(/^appendix/.test(aid)) return 'APX';
  if(/^intro/.test(aid)) return 'INTRO';
  return '§';
}

/* ---------------------------------------------------------------- search */

function bindSearch(){
  const index = [];
  for(const sec of DATA.sections){
    index.push({id: sec.id, ref: sec.num ? sec.num + '.00' : '§', title: sec.title, sec: sec.title});
    for(const t of (sec.toc || [])) index.push({id: t.id, ref: t.ref, title: t.title, sec: sec.title});
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
      e.title.toLowerCase().includes(q) || e.ref.startsWith(q)).slice(0, 40);
    const wrap = document.createElement('div');
    wrap.className = 'rl-toc-hit';
    wrap.innerHTML = results.length
      ? results.map(e=>
          `<a class="rl-toc-rule" href="#${e.id}">
             <span class="rl-toc-ref">${e.ref}</span><span class="rl-toc-title">${esc(e.title)}</span>
             <span class="rl-toc-sec-tag">${esc(e.sec)}</span></a>`).join('')
      : '<div class="rl-toc-none">No rules match.</div>';
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

  tocEl.addEventListener('click', e=>{
    const a = e.target.closest('a[href^="#"]');
    if(!a) return;
    e.preventDefault();
    jumpTo(a.getAttribute('href').slice(1));
  });
}

/* ------------------------------------------------------------- keyboard */

function bindKeyboard(){
  document.addEventListener('keydown', e=>{
    const typing = /INPUT|TEXTAREA/.test(document.activeElement?.tagName || '');
    if(e.key === 'Escape'){
      if(!glossEl.hidden) closeGlossary();
      return; // per-input Escape handled on the inputs themselves
    }
    if(typing) return;
    if(e.key === '/'){
      e.preventDefault();
      searchEl.focus();
      searchEl.select();
    }else if(e.key === 'g' || e.key === 'G'){
      e.preventDefault();
      glossEl.hidden ? openGlossary() : closeGlossary();
    }
  });
}

/* ----------------------------------------------------------- navigation */

function chromeOffset(){
  const chrome = document.querySelector('.rl-chrome');
  return (chrome ? chrome.offsetHeight : 104) + 8;
}

function jumpTo(id, push = true){
  const el = document.getElementById(id);
  if(!el) return;
  if(push && ('#' + id) !== location.hash) history.pushState(null, '', '#' + id);
  const y = el.getBoundingClientRect().top + window.scrollY - chromeOffset();
  window.scrollTo({top: Math.max(0, y), behavior: 'smooth'});
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
  phaseChipsEl.querySelectorAll('.rl-chip').forEach(c=>chips.set(c.dataset.sec, c));

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

      chips.forEach((c, sid)=>c.classList.toggle('is-active', sid === id));
      attackLabelEl.classList.toggle('is-active', id === 's05');
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
