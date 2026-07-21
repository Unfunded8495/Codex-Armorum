import { esc } from './utils.js';
import { ruleText, wrapKeywords, bsdataMarkup, optionMarkup } from './ruletext.js';

// BSData stat profiles use UPPER-CASE keys (M, T, SV, W, LD, OC) and store a
// single model's stats as a bare object rather than a one-item array. Read
// keys case-tolerantly and coerce to a list so single-model datasheets render.
function statVal(m, ...keys){
  for(const k of keys){ if(m[k]!=null && m[k]!=='') return m[k]; }
  return '';
}

export function renderDatasheetModels(models){
  if(!models) return '';
  const list = Array.isArray(models) ? models : [models];
  if(!list.length) return '';
  return `<div class="section"><h2>Datasheet</h2>`+list.map(m=>{
    const stats=[
      ['M',  statVal(m,'M','m')],
      ['T',  statVal(m,'T','t')],
      ['SV', statVal(m,'SV','Sv','sv')],
      ['W',  statVal(m,'W','w')],
      ['LD', statVal(m,'LD','Ld','ld')],
      ['OC', statVal(m,'OC','Oc','oc')],
    ];
    const inv = statVal(m,'inv_sv','INV');
    if(inv) stats.splice(3,0,['INV',inv+'+']);
    const mname = statVal(m,'profile_name','name');
    const base  = statVal(m,'base_size');
    return `<div class="model-row">
      ${list.length>1&&mname?`<p class="mname">${esc(mname)}</p>`:''}
      <div class="statline">${stats.map(([l,v])=>`
        <div class="stat-box"><span class="lbl">${l}</span><span class="val">${esc(v||'–')}</span></div>`).join('')}
      </div>
      ${base?`<p class="wg-desc">Base: ${esc(base)}</p>`:''}
    </div>`;
  }).join('')+'</div>';
}

function weaponKeywordTags(keywords){
  if(!keywords) return '';
  const tags = keywords.split(',').map(k=>k.trim()).filter(Boolean);
  if(!tags.length) return '';
  return `<span class="weapon-kws">${tags.map(k=>
    `<span class="wkw-tag">${wrapKeywords(esc(k))}</span>`).join('')}</span>`;
}

export function renderWargear(title,rows){
  if(!rows||!rows.length) return '';
  const isMe=title.includes('Melee');
  return `<div class="section"><h2>${title}</h2>
    <table class="wargear"><thead><tr><th>Weapon</th><th>Range</th><th>A</th>
    <th>${isMe?'WS':'BS'}</th><th>S</th><th>AP</th><th>D</th></tr></thead>
    <tbody>${rows.map(w=>`<tr>
      <td><button type="button" class="arsenal-trigger" data-arsenal-name="${esc(w.name)}">${esc(w.name)}</button>${weaponKeywordTags(w.keywords)}${w.description?`<div class="wg-desc">${wrapKeywords(ruleText(w.description))}</div>`:''}</td>
      <td>${esc(w.range||'–')}</td><td>${esc(w.A||'–')}</td><td>${esc(w.BS_WS||'–')}</td>
      <td>${esc(w.S||'–')}</td><td>${esc(w.AP||'–')}</td><td>${esc(w.D||'–')}</td></tr>`).join('')}
    </tbody></table></div>`;
}

/* Invulnerable save badge - shown under the stat line like the printed card. */
export function renderInvuln(abilities){
  const inv = abilities && abilities.invuln_save;
  if(!inv) return '';
  return `<div class="invuln-badge">
    <span class="invuln-val">${esc(inv)}+</span>
    <span class="invuln-lbl">Invulnerable Save</span>
  </div>`;
}

/* Damaged bracket - the "while this model has N wounds remaining…" penalty,
   shown under the stat line like the printed card's red banner. */
export function renderDamaged(d){
  if(!d.damaged_description) return '';
  const label = d.damaged_w
    ? `Damaged: ${esc(d.damaged_w)} Wounds Remaining`
    : 'Damaged';
  return `<div class="damaged-bracket">
    <span class="damaged-label">${label}</span>
    <span class="damaged-text">${bsdataMarkup(d.damaged_description)}</span>
  </div>`;
}

/* Transport capacity - its own section; BSData stores it as a full sentence. */
export function renderTransport(d){
  if(!d.transport) return '';
  return `<div class="section transport-section"><h2>Transport</h2>
    <div class="transport-text">${bsdataMarkup(d.transport)}</div>
  </div>`;
}

// Surfaced elsewhere: "Leader" as a Core tag + its own block, the invuln as a badge.
const HIDDEN_DATASHEET_ABILITIES = new Set(['leader','invulnerable save']);

export function renderAbilities(abilities){
  if(!abilities) return '';
  const core    = abilities.core    || [];
  const faction = abilities.faction || [];
  const special = abilities.special || [];
  const datasheet = (abilities.datasheet || [])
    .filter(a => !HIDDEN_DATASHEET_ABILITIES.has((a.name||'').toLowerCase()));

  if(!core.length && !faction.length && !special.length && !datasheet.length) return '';

  const tagLine = (label, items) => items.length
    ? `<p class="ability-tagline"><span class="ability-tag">${label}:</span> ${items.map(a=>esc(a.name)).join(', ')}</p>`
    : '';

  const item = a => `<div class="ability-item">
    <span class="ability-name">${esc(a.name)}:</span>
    <span class="ability-text">${bsdataMarkup(a.description)}</span>
  </div>`;

  // Special abilities grouped by their profile type (e.g. Warmaster).
  const groups = {};
  for(const s of special){ (groups[s.group] ||= []).push(s); }
  const specialBlocks = Object.entries(groups).map(([group, items]) =>
    `<div class="ability-group">
      <h3 class="ability-group-head">${esc(group)}</h3>
      ${items.map(item).join('')}
    </div>`).join('');

  return `<div class="section abilities-section">
    <h2>Abilities</h2>
    ${tagLine('Core', core)}
    ${tagLine('Faction', faction)}
    ${datasheet.map(item).join('')}
    ${specialBlocks}
  </div>`;
}

/* Wargear abilities (Chaos Icon and similar) - carried gear whose rule text
   lives on the wargear item, not the ability table. Own section like the card. */
export function renderWargearAbilities(abilities){
  const list = (abilities && abilities.wargear) || [];
  if(!list.length) return '';
  return `<div class="section abilities-section">
    <h2>Wargear Abilities</h2>
    ${list.map(a => `<div class="ability-item">
      <span class="ability-name">${esc(a.name)}:</span>
      <span class="ability-text">${bsdataMarkup(a.description)}</span>
    </div>`).join('')}
  </div>`;
}

/* "Leader" block - the units this model can be attached to. */
export function renderLeaderAttach(leads){
  if(!leads || !leads.length) return '';
  const links = leads.map(t => t.id
    ? `<a href="#/unit/${esc(t.id)}">${esc(t.name)}</a>`
    : `<span>${esc(t.name)}</span>`).join('');
  return `<div class="section leader-section">
    <h2>Leader</h2>
    <p class="leader-lead">This model can be attached to the following units:</p>
    <div class="led-by-links">${links}</div>
  </div>`;
}

export function renderList(title,rows,cls){
  if(!rows||!rows.length) return '';
  return `<div class="section"><h2>${title}</h2><ul class="${cls}">
    ${rows.map(r=>`<li>${ruleText(r.description)}</li>`).join('')}</ul></div>`;
}

// Composition rows are {name, min, max}; `name` sometimes already embeds the
// count range ("4-9 Dark Reapers"), otherwise prefix the model count.
function compositionLine(r){
  if(r.description) return ruleText(r.description);  // legacy/Wahapedia shape
  const name = (r.name||'').trim();
  if(!name) return '';
  if(/^\d/.test(name)) return esc(name);
  if(r.min!=null && r.max!=null){
    const count = r.min===r.max ? `${r.min}` : `${r.min}-${r.max}`;
    return `${count} ${esc(name)}`;
  }
  return esc(name);
}

// Base-size strings from w40k.db come in three shapes: a single value
// ("32mm"), a comma list ("32mm, 40mm"), or a per-model breakdown with one
// model per line ("Boss Nob: 40mm\nBreaka Boyz: 32mm"). Split the breakdown so
// each model's base can be rendered on its own line.
export function baseSizeLines(raw){
  return String(raw||'').split('\n').map(l=>l.trim()).filter(Boolean);
}

// Compact size-only summary for tight spots (the card header chip): the distinct
// sizes with the per-model labels dropped. Single-value and comma-list strings
// carry no ':' so they pass through unchanged; the full breakdown still shows in
// the composition block.
export function baseSizeSummary(raw){
  const seen = [];
  for(const line of baseSizeLines(raw)){
    const i = line.indexOf(':');
    const size = (i>=0 ? line.slice(i+1) : line).trim();
    if(size && !seen.includes(size)) seen.push(size);
  }
  return seen.join(', ');
}

export function renderUnitComposition(rows,loadout,ledBy,baseSize){
  if((!rows||!rows.length)&&!loadout&&(!ledBy||!ledBy.length)&&!baseSize) return '';
  return `<div class="section"><h2>Unit Composition</h2>
    ${rows&&rows.length?`<ul class="comp-list">
      ${rows.map(r=>`<li>${compositionLine(r)}</li>`).join('')}</ul>`:''}
    ${loadout?`<div class="loadout-block">${renderLoadout(loadout)}</div>`:''}
    ${baseSize?`<div class="base-size-block"><h3>Base Size</h3><p>${baseSizeLines(baseSize).map(esc).join('<br>')}</p></div>`:''}
    ${ledBy&&ledBy.length?renderLedBy(ledBy):''}
  </div>`;
}

// Duplicate-selection surcharge carried in points_steps:
// [{step_at, step_points}] -> "Your 3rd and subsequent selections of this
// unit each cost +10 pts." (clearer than the official app's "After the 2nd
// selection..." wording, which reads as if the 2nd costs more)
export function pointsStepNote(steps){
  const s = steps && steps[0];
  if(!s || !s.step_at || !s.step_points) return '';
  const n = s.step_at;
  const ord = n===1?'1st':n===2?'2nd':n===3?'3rd':`${n}th`;
  return `Your ${ord} and subsequent selections of this unit each cost +${s.step_points} pts.`;
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
    ${rows.map(r=>`<li>${optionMarkup(r.description)}</li>`).join('')}</ul></div>`;
}

export function renderPoints(costs,steps){
  const note = pointsStepNote(steps);
  if((!costs||!costs.length)&&!note) return '';
  return `<div class="section"><h2>Points</h2><div class="points-row">
    ${(costs||[]).map(c=>`<div class="points-box"><b>${esc(c.cost)}</b><span>${esc(c.description)}</span></div>`).join('')}
  </div>${note?`<p class="points-step-note">${esc(note)}</p>`:''}</div>`;
}

export function renderKeywords(d){
  if(!d.keywords.length&&!d.faction_keywords.length) return '';
  return `<div class="section"><h2>Keywords</h2><div class="pill-row">
    ${d.keywords.map(k=>`<span class="pill">${esc(k)}</span>`).join('')}
    ${d.faction_keywords.map(k=>`<span class="pill faction">${esc(k)}</span>`).join('')}
  </div></div>`;
}
