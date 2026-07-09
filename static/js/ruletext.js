import { esc } from './utils.js';

let WARGEAR_GLOSSARY = [];
fetch('/static/weapon_keywords.json').then(r=>r.json()).then(entries=>{
  WARGEAR_GLOSSARY = entries.map(({pattern,tip})=>[new RegExp(pattern,'gi'),tip]);
}).catch(()=>{});

export function wrapKeywords(html){
  if(!html||!WARGEAR_GLOSSARY.length) return html;
  let out=html;
  for(const [re,tipTemplate] of WARGEAR_GLOSSARY){
    out=out.replace(re,(...args)=>{
      const full=args[0];
      const groups=args.slice(1,-2);
      const tip=tipTemplate.replace(/\$(\d+)/g,(_,i)=>groups[parseInt(i)-1]??'').replace(/"/g,'&quot;');
      return `<span class="kwt" data-tip="${tip}">${full}</span>`;
    });
  }
  return out;
}

/* ---- tooltip interaction for the .kwt spans wrapKeywords produces ----
   Mouse, outside the datasheet card: the CSS-only .kwt:hover::after bubble in
   style.css. Inside the card that bubble is clipped by the chamfered frame
   (.dsc-lower-inner overflow:hidden + clip-path), so hovering shows one
   floating fixed-position element on <body> instead, which no frame can clip.
   Touch has no hover: tapping any .kwt shows the floating element -- via the
   tap's emulated mouseover inside the card (the card overlay body stops click
   propagation, so click never reaches the document there), via click
   everywhere else. Tapping anything else or scrolling dismisses it. While the
   floating element is up, .kwt-active suppresses that keyword's CSS bubble so
   the two never double-show. */
let tipEl = null, tipFor = null;
function showTip(kw){
  const tip = kw.getAttribute('data-tip');
  if(!tip) return;
  if(!tipEl){
    tipEl = document.createElement('div');
    tipEl.className = 'kwtip';
    tipEl.hidden = true;
    document.body.appendChild(tipEl);
  }
  if(tipFor && tipFor !== kw) tipFor.classList.remove('kwt-active');
  kw.classList.add('kwt-active');
  tipFor = kw;
  tipEl.textContent = tip;
  tipEl.hidden = false;
  const r = kw.getBoundingClientRect();
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
  const top = r.top - h - 7 >= 8 ? r.top - h - 7 : r.bottom + 7;
  tipEl.style.left = `${left}px`;
  tipEl.style.top = `${top}px`;
}
function hideTip(){
  if(tipEl) tipEl.hidden = true;
  if(tipFor){ tipFor.classList.remove('kwt-active'); tipFor = null; }
}
document.addEventListener('mouseover', e=>{
  const kw = e.target.closest ? e.target.closest('.kwt') : null;
  if(kw && kw.closest('.dsc-card')) showTip(kw);
  else if(kw !== tipFor) hideTip();
});
document.addEventListener('click', e=>{
  const kw = e.target.closest ? e.target.closest('.kwt') : null;
  if(kw) showTip(kw); else hideTip();
});
document.addEventListener('scroll', hideTip, true);

/* Convert BSData's plain-text rules markup into safe HTML.
   `**bold**`  -> <strong>, `^^small caps^^` -> keyword span, blank-line/­newline
   bullet markers (* - • ■ ▪) -> a bullet list. Input is escaped first. */
export function bsdataMarkup(raw){
  if(raw==null) return '';
  let html = esc(String(raw).replace(/\r\n?/g,'\n'));
  html = html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
             .replace(/\^\^(.+?)\^\^/g,'<span class="kw-ref">$1</span>');
  const out = [];
  let inList = false;
  for(const line of html.split('\n').map(l=>l.trim()).filter(Boolean)){
    const bullet = line.match(/^[■▪•*\-]\s*(.+)$/);
    if(bullet){
      if(!inList){ out.push('<ul class="ability-bullets">'); inList = true; }
      out.push(`<li>${bullet[1]}</li>`);
    }else{
      if(inList){ out.push('</ul>'); inList = false; }
      out.push(`<p>${line}</p>`);
    }
  }
  if(inList) out.push('</ul>');
  return out.join('');
}

/* Wargear-option rules text from the app export is one group per string: a
   "■ This model's X can be replaced with ..." lead-in line followed by
   "◦ 1 item" lines. Render the lead-in as text and the ◦ lines as a nested
   list so the datasheet reads like the official app instead of one flattened
   run-on line. */
export function optionMarkup(raw){
  if(raw==null) return '';
  const lines = esc(String(raw).replace(/\r\n?/g,'\n')).split('\n')
    .map(l=>l.trim()).filter(Boolean);
  const out = [];
  let inSub = false;
  for(const line of lines){
    const sub = line.match(/^[◦○]\s*(.+)$/);
    if(sub){
      if(!inSub){ out.push('<ul class="opt-sublist">'); inSub = true; }
      out.push(`<li>${sub[1]}</li>`);
    }else{
      if(inSub){ out.push('</ul>'); inSub = false; }
      out.push(`<span class="opt-lead">${line.replace(/^[■▪•]\s*/,'')}</span>`);
    }
  }
  if(inSub) out.push('</ul>');
  return out.join('');
}

export function cleanRuleText(text){
  return (text??'').toString()
    .replace(/ /g,' ').replace(/\s+/g,' ')
    .replace(/\s+([,.;:!?])/g,'$1').replace(/([:;,.!?])(?=\S)/g,'$1 ')
    .replace(/(^|[^A-Za-z-])(\d+)\s*-\s*(\d+)\b/g,(_,a,b,c)=>`${a}${b}–${c}`)
    .replace(/\s+(['''])/g,'$1').trim();
}

export function ruleText(html){
  const root=document.createElement('div');
  root.innerHTML=html||'';
  const renderNodes=nodes=>[...nodes].map(node=>{
    if(node.nodeType===Node.TEXT_NODE) return esc(cleanRuleText(node.textContent));
    if(node.nodeType!==Node.ELEMENT_NODE) return '';
    const tag=node.tagName.toLowerCase();
    if(tag==='br') return '<br>';
    if(tag==='ul'||tag==='ol'){
      const items=[...node.children].filter(c=>c.tagName?.toLowerCase()==='li')
        .map(li=>`<li>${renderNodes(li.childNodes)}</li>`).join('');
      return `<ul class="rule-sublist">${items}</ul>`;
    }
    if(tag==='li') return `<li>${renderNodes(node.childNodes)}</li>`;
    if(tag==='b'||tag==='strong') return `<strong>${renderNodes(node.childNodes)}</strong>`;
    return renderNodes(node.childNodes);
  }).join('');
  return renderNodes(root.childNodes)||esc(cleanRuleText(root.textContent));
}
