import { esc } from './utils.js';

const cache = new Map();
let popover = null;
let timer = null;
let hideTimer = null;

function ensurePopover(){
  if(popover) return popover;
  popover = document.createElement('div');
  popover.className = 'arsenal-popover';
  popover.hidden = true;
  popover.addEventListener('mouseenter', () => {
    if(hideTimer) clearTimeout(hideTimer);
  });
  popover.addEventListener('mouseleave', scheduleHide);
  document.body.appendChild(popover);
  document.addEventListener('pointerdown', event => {
    if(popover.hidden) return;
    if(event.target.closest('.arsenal-popover') || event.target.closest('.arsenal-trigger')) return;
    hidePopover();
  });
  return popover;
}

async function fetchCard(name){
  if(cache.has(name)) return cache.get(name);
  const res = await fetch(`/arsenal/api/weapon-card?name=${encodeURIComponent(name)}`, {
    headers:{'accept':'application/json'},
  });
  const data = await res.json();
  cache.set(name, data);
  return data;
}

function renderCard(data){
  if(!data.found){
    return `<div class="arsenal-popover-empty">
      <strong>${esc(data.name || 'Unknown weapon')}</strong>
      <p>${esc(data.message || 'No Arsenal entry yet.')}</p>
      <a href="${esc(data.add_url || '/arsenal/weapon/new')}">Add to Arsenal</a>
    </div>`;
  }
  const image = data.photo_url
    ? `<img src="${esc(data.photo_url)}" alt="${esc(data.name)}">`
    : `<div class="arsenal-popover-noimg">No photo yet</div>`;
  return `<div class="arsenal-popover-card">
    ${image}
    <div>
      <strong>${esc(data.name)}</strong>
      <p>${esc(data.description || data.spotting_notes || 'No description yet.')}</p>
      <a href="${esc(data.entry_url)}">Open Arsenal entry</a>
    </div>
  </div>`;
}

function positionPopover(trigger){
  const box = ensurePopover();
  const rect = trigger.getBoundingClientRect();
  const top = window.scrollY + rect.bottom + 8;
  let left = window.scrollX + rect.left;
  box.style.top = `${top}px`;
  box.style.left = `${left}px`;
  const overflow = box.getBoundingClientRect().right - window.innerWidth + 14;
  if(overflow > 0) box.style.left = `${Math.max(12, left - overflow)}px`;
}

function hidePopover(){
  if(timer) clearTimeout(timer);
  if(hideTimer) clearTimeout(hideTimer);
  if(popover) popover.hidden = true;
}

function scheduleHide(){
  if(hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    const activeTrigger = document.activeElement?.classList?.contains('arsenal-trigger');
    if(popover?.matches(':hover') || activeTrigger) return;
    hidePopover();
  }, 180);
}

function showPopover(trigger){
  const name = trigger.dataset.arsenalName || trigger.textContent.trim();
  if(!name) return;
  if(timer) clearTimeout(timer);
  timer = setTimeout(async () => {
    const box = ensurePopover();
    box.hidden = false;
    box.innerHTML = '<div class="arsenal-popover-loading">Loading...</div>';
    positionPopover(trigger);
    try{
      box.innerHTML = renderCard(await fetchCard(name));
    }catch(err){
      box.innerHTML = `<div class="arsenal-popover-empty"><strong>${esc(name)}</strong><p>Preview unavailable.</p></div>`;
    }
    positionPopover(trigger);
  }, 120);
}

export function setupArsenalHover(root=document){
  root.querySelectorAll('.arsenal-trigger').forEach(trigger => {
    trigger.addEventListener('mouseenter', () => showPopover(trigger));
    trigger.addEventListener('focus', () => showPopover(trigger));
    trigger.addEventListener('mouseleave', scheduleHide);
    trigger.addEventListener('blur', scheduleHide);
    trigger.addEventListener('click', event => {
      event.preventDefault();
      if(popover && !popover.hidden) hidePopover();
      else showPopover(trigger);
    });
  });
}
