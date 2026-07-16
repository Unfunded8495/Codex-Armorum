import { esc } from './utils.js';
import { optionMarkup, wrapKeywords } from './ruletext.js';
import { pointsStepNote } from './datasheet.js';

/* The card's base colour comes straight from the API payload's `primary`, which
   the backend resolves from the official faction colours in factions_theme.py —
   the single source of truth shared with every other surface. Falls back to grey
   only when a datasheet has no themed faction. */
function factionColour(d){return d.primary || "#444";}

function statVal(m, ...keys){for(const k of keys){if(m && m[k]!=null && m[k]!=='') return m[k];} return '';}

/* Give keyword modifiers a consistent faction colour bold wherever they appear:
   Wahapedia bold keyword spans and bracketed all caps tokens such as [LETHAL HITS]. */
function markKw(t){
  if(!t) return t;
  t = t.replace(/<span class="kwb">([^<]+)<\/span>/gi, '<b class="dsc-kwref">$1</b>');
  t = t.replace(/\[[A-Z0-9][A-Z0-9 ,+\-\/]*\]/g, '<b class="dsc-kwref">$&</b>');
  return t;
}
/* Convert Wahapedia HTML into safe card markup. Keeps ul, li, br, b, strong, and the
   keyword bold tags markKw adds. Strips tooltip chrome, anchors, and other spans/divs. */
function clean(html){
  if(!html) return "";
  let t = markKw(html);
  t = t.replace(/<div class="redExample[\s\S]*?<\/div>/gi,"")
       .replace(/<div class="BreakInsideAvoid[\s\S]*?<\/div>/gi,"")
       .replace(/<div class="abWrap[\s\S]*?<\/div>\s*/gi,"");
  t = t.replace(/<a [^>]*>/gi,"").replace(/<\/a>/gi,"")
       .replace(/<span [^>]*>/gi,"").replace(/<\/span>/gi,"")
       .replace(/<div[^>]*>/gi,"").replace(/<\/div>/gi,"");
  t = t.replace(/<p[^>]*>/gi,"").replace(/<\/p>/gi,"<br>")
       .replace(/<(?!\/?(ul|li|br|b|strong)\b)[^>]*>/gi,"");
  t = t.replace(/(<br>\s*){2,}/gi,"<br>").replace(/^(<br>)+|(<br>)+$/g,"");
  /* Glossary tooltips must be added after the span-stripping above,
     or the .kwt spans wrapKeywords inserts would be stripped with the rest. */
  return wrapKeywords(t.trim());
}

function statBadges(model, invuln){
  const order = [
    ['M',  statVal(model,'M','m')],
    ['T',  statVal(model,'T','t')],
    ['SV', statVal(model,'SV','Sv','sv')],
    ['W',  statVal(model,'W','w')],
    ['LD', statVal(model,'LD','Ld','ld')],
    ['OC', statVal(model,'OC','Oc','oc')],
  ];
  let badges = order.map(([l,v]) =>
    `<div class="dsc-stat"><span class="dsc-stat-lbl">${l}</span>` +
    `<span class="dsc-stat-val"><span class="dsc-stat-in">${esc(v||'-')}</span></span></div>`).join('');
  if(invuln){
    badges += `<div class="dsc-invuln"><span class="dsc-invuln-lbl">Invulnerable Save</span>` +
      `<span class="dsc-invuln-val">${esc(invuln)}+</span></div>`;
  }
  return `<div class="dsc-statline">${badges}</div>`;
}

function profileName(n){return (n||"").replace(/\s[-–—]\s/," – ");}
export function weaponBase(n){
  return (n||"").replace(/^\s*\d+\s*×\s*/,"").split(/\s[-–—]\s/)[0].trim();
}
function rangeCell(v){if(!v) return "-"; if(String(v).toLowerCase()==="melee") return "Melee"; return esc(v)+'"';}
function kwTag(k){
  if(!k) return "";
  const t = k.split(",").map(x=>x.trim()).filter(Boolean);
  return t.length ? `<span class="dsc-wkw">[${t.map(x=>wrapKeywords(esc(x).toUpperCase())).join(", ")}]</span>` : "";
}

/* Each weapon profile is its own row with its full name and its own keywords.
   Zebra shading alternates per weapon group (base name), so multi profile weapons
   such as the two plasma pistol modes share one shaded block.
   `taken` (optional Set of lowercased base names) keeps only carried weapons;
   matching is by base name so every profile of a taken weapon stays visible.
   A table whose weapons are all filtered out is dropped entirely. */
function weaponTable(list, melee, taken){
  if(taken) list = (list || []).filter(w => taken.has(weaponBase(w.name).toLowerCase()));
  if(!list || !list.length) return "";
  const sk = melee ? "WS" : "BS";
  let rows = "", prevBase = null, gi = -1;
  list.forEach(w => {
    const base = weaponBase(w.name);
    if(base !== prevBase){ gi++; prevBase = base; }
    const alt = gi % 2 === 1 ? " dsc-wrow-alt" : "";
    const kw = kwTag(w.keywords);
    rows += `<tr class="dsc-wrow${alt}">` +
      `<td class="dsc-wname"><span class="dsc-w-base">${esc(profileName(w.name))}</span>${kw}</td>` +
      `<td>${rangeCell(w.range)}</td><td>${esc(w.A||'-')}</td><td>${esc(w.BS_WS||'-')}</td>` +
      `<td>${esc(w.S||'-')}</td><td>${esc(w.AP||'-')}</td><td>${esc(w.D||'-')}</td></tr>`;
  });
  const icon = melee ? 'ico-melee' : 'ico-range';
  const title = melee ? 'Melee Weapons' : 'Ranged Weapons';
  return `<table class="dsc-wpn"><thead><tr class="dsc-wpn-bar">` +
    `<th class="dsc-wname"><span class="dsc-wpn-titlewrap"><span class="dsc-ico ${icon}"></span>${title}</span></th>` +
    `<th>Range</th><th>A</th><th>${sk}</th><th>S</th><th>AP</th><th>D</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

function legendBlock(d){
  if(!d.legend) return "";
  return `<div class="dsc-legend">${clean(d.legend)}</div>`;
}

function abilitiesBlock(d){
  const a = d.abilities || {};
  const core    = (a.core    || []).map(x=>x.name).filter(Boolean);
  const faction = (a.faction || []).map(x=>x.name).filter(Boolean);
  const datasheet = (a.datasheet || []).filter(x => x && x.name &&
    (x.name||'').toLowerCase() !== 'leader' &&
    (x.name||'').toLowerCase() !== 'invulnerable save');
  if(!core.length && !faction.length && !datasheet.length) return "";
  let html = `<div class="dsc-head">Abilities</div><div class="dsc-block">`;
  if(core.length)    html += `<p class="dsc-coreline"><span class="dsc-k">Core:</span> ${esc(core.join(', '))}</p>`;
  if(faction.length) html += `<p class="dsc-coreline"><span class="dsc-k">Faction:</span> ${esc(faction.join(', '))}</p>`;
  for(const x of datasheet){
    html += `<div class="dsc-ability"><span class="dsc-an">${esc(x.name)}:</span> ${clean(x.description)}</div>`;
  }
  return html + `</div>`;
}

function wargearAbilitiesBlock(d){
  const list = (d.abilities && d.abilities.wargear) || [];
  if(!list.length) return "";
  let html = `<div class="dsc-head">Wargear Abilities</div><div class="dsc-block">`;
  for(const x of list){
    html += `<div class="dsc-ability"><span class="dsc-an">${esc(x.name)}:</span> ${clean(x.description)}</div>`;
  }
  return html + `</div>`;
}

function wargearBlock(d){
  if(!d.options || !d.options.length) return "";
  return `<div class="dsc-head">Wargear Options</div><div class="dsc-block">` +
    `<ul class="dsc-opt">` + d.options.map(o=>`<li>${optionMarkup(o.description)}</li>`).join('') + `</ul></div>`;
}

function leaderBlock(d){
  if(!d.leads || !d.leads.length) return "";
  const items = d.leads.map(t => t.id
    ? `<li><a href="#/unit/${esc(t.id)}">${esc(t.name)}</a></li>`
    : `<li>${esc(t.name)}</li>`).join('');
  return `<div class="dsc-head">Leader</div><div class="dsc-block">` +
    `<p class="dsc-lead">This model can be attached to the following units:</p>` +
    `<ul class="dsc-opt">${items}</ul></div>`;
}

// Mirror the official app's Unit Composition block: "1 Deff Dread" style
// count-prefixed model lines followed by the bolded "This model is equipped
// with: ..." sentence(s) served in d.loadout.
function compositionBlock(d){
  const items = (d.composition||[]).map(c=>{
    const name = (c.name||'').trim();
    if(!name) return '';
    if(/^\d/.test(name)) return `<li>${esc(name)}</li>`;
    if(c.min!=null && c.max!=null){
      const count = c.min===c.max ? `${c.min}` : `${c.min}-${c.max}`;
      return `<li>${count} ${esc(name)}</li>`;
    }
    return `<li>${esc(name)}</li>`;
  }).join('');
  const stepNote = pointsStepNote(d.points_steps);
  if(!items && !d.loadout && !stepNote && !d.base_size) return "";
  return `<div class="dsc-head">Unit Composition</div><div class="dsc-block">` +
    (items ? `<ul class="dsc-opt">${items}</ul>` : '') +
    (d.loadout ? `<p class="dsc-loadout">${clean(d.loadout)}</p>` : '') +
    (stepNote ? `<p class="dsc-step-note">${esc(stepNote)}</p>` : '') +
    (d.base_size ? `<p class="dsc-base-size"><span class="dsc-k">Base Size:</span> ${esc(d.base_size)}</p>` : '') +
    `</div>`;
}

function damagedBlock(d){
  if(!d.damaged_description) return "";
  const label = d.damaged_w ? `Damaged: ${esc(d.damaged_w)} Wounds Remaining` : 'Damaged';
  return `<div class="dsc-damaged"><div class="dsc-head"><span class="dsc-ico ico-skull"></span>${label}</div>` +
    `<div class="dsc-block"><div class="dsc-ability">${clean(d.damaged_description)}</div></div></div>`;
}

function keywordsFooter(d){
  const fac = (d.faction_keywords || []).map(k=>`<span class="dsc-kw">${esc(k)}</span>`).join(', ');
  const kw  = (d.keywords || []).map(k=>`<span class="dsc-kw">${esc(k)}</span>`).join(', ');
  if(!fac && !kw) return "";
  const iconUrl = `/api/factions/${esc(d.faction_id)}/icon`;
  const diamond = `<div class="dsc-fac-diamond"><span class="dsc-fac-ico" ` +
    `style="-webkit-mask-image:url('${iconUrl}');mask-image:url('${iconUrl}')"></span></div>`;
  return `<div class="dsc-footer">` +
    `<div class="dsc-kwbox dsc-kwbox-keywords"><span class="dsc-kwgroup"><span class="dsc-kwlbl">Keywords</span><span class="dsc-kwlist">${kw}</span></span></div>` +
    `<div class="dsc-kwbox dsc-kwbox-faction"><span class="dsc-kwgroup"><span class="dsc-kwlbl">Faction Keywords</span><span class="dsc-kwlist">${fac}</span></span></div>` +
    diamond +
    `</div>`;
}

/* True when at least one of the card's weapon rows matches the taken set.
   The wargear system and the weapon rows share no ids, so the join is by
   name; callers use this to fall back to the unfiltered card when the name
   match misses outright (never render empty weapon tables). */
export function cardWeaponMatches(d, taken){
  const hit = w => taken.has(weaponBase(w.name).toLowerCase());
  return (d.ranged || []).some(hit) || (d.melee || []).some(hit);
}

/* opts.takenWeapons: optional Set of lowercased weapon base names; when given,
   the weapon tables show only those weapons (army-builder loadout view).
   Callers without opts get the full card, unchanged. */
export function renderDatasheetCard(d, opts){
  const taken = (opts && opts.takenWeapons) || null;
  const primary = factionColour(d);
  const models  = Array.isArray(d.models) ? d.models : [d.models || {}];
  const invuln  = d.abilities && d.abilities.invuln_save;
  const baseSize = d.base_size || (models[0] || {}).base_size;

  const statBlocks = models.map((m,i)=>{
    const mname = statVal(m,'profile_name','name');
    const tag = (models.length>1 && mname) ? `<p class="dsc-model-tag">${esc(mname)}</p>` : '';
    return `<div class="dsc-model">${tag}${statBadges(m, i===0 ? invuln : null)}</div>`;
  }).join('');

  const left  = weaponTable(d.ranged,false,taken) + weaponTable(d.melee,true,taken) + wargearBlock(d) + leaderBlock(d);
  const right = abilitiesBlock(d) + wargearAbilitiesBlock(d) + compositionBlock(d) + damagedBlock(d);

  return `
    <div class="dsc-card" style="--dsc-primary:${primary}">
      <div class="dsc-hdr">
        <div class="dsc-hdr-logo" style="-webkit-mask-image:url('/api/factions/${esc(d.faction_id)}/icon');mask-image:url('/api/factions/${esc(d.faction_id)}/icon');"></div>
        <div class="dsc-hdr-rule"></div>
        <div class="dsc-hdr-main">
          <h2 class="dsc-name">${esc(d.name)}${baseSize ? ` <span class="dsc-base">(Ø${esc(baseSize)})</span>` : ''}</h2>
          <div class="dsc-models">${statBlocks}</div>
        </div>
        ${legendBlock(d)}
      </div>
      <div class="dsc-lower"><div class="dsc-lower-inner">
        <div class="dsc-body">
          <div class="dsc-col dsc-col-left">${left}</div>
          <div class="dsc-col dsc-col-right">${right}</div>
        </div>
      </div></div>
      ${keywordsFooter(d)}
    </div>`;
}
