import { esc } from './utils.js';
import { ruleText, wrapKeywords } from './ruletext.js';

export function renderDatasheetModels(models){
  if(!models||!models.length) return '';
  return `<div class="section"><h2>Datasheet</h2>`+models.map(m=>{
    const stats=[['M',m.M],['T',m.T],['SV',m.Sv],['W',m.W],['LD',m.Ld],['OC',m.OC]];
    if(m.inv_sv&&m.inv_sv!=='') stats.splice(3,0,['INV',m.inv_sv+'+']);
    return `<div class="model-row">
      ${models.length>1?`<p class="mname">${esc(m.name)}</p>`:''}
      <div class="statline">${stats.map(([l,v])=>`
        <div class="stat-box"><span class="lbl">${l}</span><span class="val">${esc(v||'–')}</span></div>`).join('')}
      </div>
      ${m.base_size?`<p class="wg-desc">Base: ${esc(m.base_size)}${m.base_size_descr?' · '+esc(m.base_size_descr):''}</p>`:''}
    </div>`;
  }).join('')+'</div>';
}

export function renderWargear(title,rows){
  if(!rows||!rows.length) return '';
  const isMe=title.includes('Melee');
  return `<div class="section"><h2>${title}</h2>
    <table class="wargear"><thead><tr><th>Weapon</th><th>Range</th><th>A</th>
    <th>${isMe?'WS':'BS'}</th><th>S</th><th>AP</th><th>D</th></tr></thead>
    <tbody>${rows.map(w=>`<tr>
      <td><button type="button" class="arsenal-trigger" data-arsenal-name="${esc(w.name)}">${esc(w.name)}</button>${w.description?`<div class="wg-desc">${wrapKeywords(ruleText(w.description))}</div>`:''}</td>
      <td>${esc(w.range||'–')}</td><td>${esc(w.A||'–')}</td><td>${esc(w.BS_WS||'–')}</td>
      <td>${esc(w.S||'–')}</td><td>${esc(w.AP||'–')}</td><td>${esc(w.D||'–')}</td></tr>`).join('')}
    </tbody></table></div>`;
}

export function renderList(title,rows,cls){
  if(!rows||!rows.length) return '';
  return `<div class="section"><h2>${title}</h2><ul class="${cls}">
    ${rows.map(r=>`<li>${ruleText(r.description)}</li>`).join('')}</ul></div>`;
}

export function renderUnitComposition(rows,loadout,ledBy){
  if((!rows||!rows.length)&&!loadout&&(!ledBy||!ledBy.length)) return '';
  return `<div class="section"><h2>Unit Composition</h2>
    ${rows&&rows.length?`<ul class="comp-list">
      ${rows.map(r=>`<li>${ruleText(r.description)}</li>`).join('')}</ul>`:''}
    ${loadout?`<div class="loadout-block">${renderLoadout(loadout)}</div>`:''}
    ${ledBy&&ledBy.length?renderLedBy(ledBy):''}
  </div>`;
}

function renderLoadout(loadout){
  return ruleText(loadout).replace(/<\/strong>(?=[A-Za-z0-9])/g,'</strong> ');
}

function renderLedBy(ledBy){
  return `<div class="led-by-block">
    <h3>Led By</h3>
    <p>This unit can be led by the following units:</p>
    <div class="led-by-links">
      ${ledBy.map(u=>`<a href="#/unit/${esc(u.id)}">${esc(u.name)}</a>`).join('')}
    </div>
  </div>`;
}

export function renderOptions(rows){
  if(!rows||!rows.length) return '';
  return `<div class="section"><h2>Wargear Options</h2><ul class="opt-list">
    ${rows.map(r=>`<li>${ruleText(r.description)}</li>`).join('')}</ul></div>`;
}

export function renderPoints(costs){
  if(!costs||!costs.length) return '';
  return `<div class="section"><h2>Points</h2><div class="points-row">
    ${costs.map(c=>`<div class="points-box"><b>${esc(c.cost)}</b><span>${esc(c.description)}</span></div>`).join('')}
  </div></div>`;
}

export function renderKeywords(d){
  if(!d.keywords.length&&!d.faction_keywords.length) return '';
  return `<div class="section"><h2>Keywords</h2><div class="pill-row">
    ${d.keywords.map(k=>`<span class="pill">${esc(k)}</span>`).join('')}
    ${d.faction_keywords.map(k=>`<span class="pill faction">${esc(k)}</span>`).join('')}
  </div></div>`;
}
