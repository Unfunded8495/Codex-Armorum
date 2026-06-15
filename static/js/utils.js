export const esc   = s => (s??'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
export const api   = (u,o) => fetch(u,o).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();});
export const jsStr = v => JSON.stringify((v??'').toString());
export const intOr = (v, fallback=0) => { const n=parseInt(v,10); return Number.isFinite(n)?n:fallback; };

export function withTimeout(promise, ms = 8000){
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('timeout')), ms)
  );
  return Promise.race([promise, timeout]);
}

/* ---- contrast-safe accent for text on the dark theme ---------------------
   Faction accents range from near-white to near-black. Using a near-black
   accent (e.g. Adeptus Custodes #1a1a1a, Necrons #101a12) as heading text on
   the dark background makes titles unreadable. readableInk keeps the faction
   hue where it is already legible, lightens dark hued accents toward the
   parchment tone, and falls back to bright gold for near-greyscale darks so
   every page title reads consistently. */
const _srgb = c => { c /= 255; return c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4); };
const _lum  = (r,g,b) => 0.2126*_srgb(r) + 0.7152*_srgb(g) + 0.0722*_srgb(b);

export function readableInk(hex, floor = 0.30){
  const m = /^#?([0-9a-fA-F]{6})$/.exec((hex ?? '').toString().trim());
  if(!m) return 'var(--parch)';
  const n = parseInt(m[1], 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  if(_lum(r,g,b) >= floor) return '#' + m[1];          // already legible, keep the hue
  if(Math.max(r,g,b) - Math.min(r,g,b) < 24) return 'var(--gold-bright)'; // greyscale dark
  const P = [230, 220, 196];                            // parchment target
  let lo = 0, hi = 1;
  for(let i = 0; i < 14; i++){
    const t = (lo + hi) / 2;
    const rr = r + (P[0]-r)*t, gg = g + (P[1]-g)*t, bb = b + (P[2]-b)*t;
    if(_lum(rr, gg, bb) < floor) lo = t; else hi = t;
  }
  r = Math.round(r + (P[0]-r)*hi);
  g = Math.round(g + (P[1]-g)*hi);
  b = Math.round(b + (P[2]-b)*hi);
  return `rgb(${r},${g},${b})`;
}
