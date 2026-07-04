/* /arsenal/loadouts pages — manual-page chrome behavior.
   Server-rendered content; this module only wires the shared reading-mode
   toggle, quick-strip jump chips and the back-to-top button. Same theme key
   and jump math as /rules — no scrollIntoView. */

const THEME_KEY = 'caRules.theme';
const themeBtn = document.getElementById('arsThemeBtn');
const themeLabel = document.getElementById('arsThemeLabel');
const topBtn = document.getElementById('arsTopBtn');
const strip = document.getElementById('arsStrip');

applyTheme(readTheme());

function readTheme(){
  try{ return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'; }
  catch(e){ return 'light'; }
}
function applyTheme(t){
  if(t === 'dark') document.body.setAttribute('data-rl-theme', 'dark');
  else document.body.removeAttribute('data-rl-theme');
  if(themeLabel) themeLabel.textContent = t === 'dark' ? 'Light' : 'Dark';
}
themeBtn?.addEventListener('click', () => {
  const t = document.body.getAttribute('data-rl-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(t);
  try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
});

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

strip?.addEventListener('click', e => {
  const a = e.target.closest('a[href^="#"]');
  if(!a) return;
  e.preventDefault();
  jumpTo(a.getAttribute('href').slice(1));
});

window.addEventListener('hashchange', () => {
  const id = location.hash.slice(1);
  if(id) jumpTo(id, false);
});
if(location.hash) jumpTo(location.hash.slice(1), false);

document.addEventListener('scroll', () => {
  topBtn?.classList.toggle('is-shown', window.scrollY > 900);
}, { passive: true });
topBtn?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
