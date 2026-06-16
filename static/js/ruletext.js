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
