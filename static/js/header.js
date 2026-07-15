import { esc, api } from './utils.js';

const breadcrumb = document.getElementById('breadcrumb');
const ledger = document.getElementById('ledger');
let ledgerRequest = null;

export function updateLedger(s){
  if(!ledger) return;
  const bought = s.bought_minis || 0;
  const unbuilt = s.unbuilt_minis || 0;
  const wip = s.wip_minis || 0;
  const finished = s.finished_minis || 0;
  const pct = bought > 0 ? Math.round((finished / bought) * 100) : 0;
  const wipPct = bought > 0 ? Math.round((wip / bought) * 100) : 0;
  ledger.innerHTML = `
    <div class="stat"><b>${bought}</b><span>Bought</span></div>
    <div class="stat"><b>${unbuilt}</b><span>Unbuilt</span></div>
    <div class="stat"><b>${wip}</b><span>WIP ${wipPct}%</span></div>
    <div class="stat"><b>${finished}</b><span>Finished ${pct}%</span></div>`;
}

export async function refreshLedger(){
  if(ledgerRequest) return ledgerRequest;

  ledgerRequest = api('/api/collection/summary')
    .then(summary => {
      updateLedger(summary);
      return summary;
    })
    .finally(() => { ledgerRequest = null; });
  return ledgerRequest;
}

export function setBreadcrumb(items){
  if(!breadcrumb) return;
  breadcrumb.innerHTML = items.map((item, idx) => {
    const sep = idx === 0 ? '' : '<span class="sep">&gt;</span>';
    const label = esc(item.label || '');
    const title = item.title ? ` title="${esc(item.title)}"` : '';
    if(item.href){
      return `${sep}<a class="crumb" href="${esc(item.href)}"${title}>${label}</a>`;
    }
    return `${sep}<span class="cur"${title}>${label}</span>`;
  }).join('');
}

export function setActiveNav(page){
  document.querySelectorAll('[data-nav-page]').forEach(link => {
    link.classList.toggle('is-current', link.dataset.navPage === page);
  });
}

export function wireHomeButton(handler){
  const homeBtn = document.getElementById('homeBtn');
  if(!homeBtn) return;
  homeBtn.addEventListener('click', e => {
    if(handler){
      e.preventDefault();
      handler();
    }
  });
}
