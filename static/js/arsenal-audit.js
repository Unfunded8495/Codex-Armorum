import { esc } from './utils.js';

function collectRow(row){
  const payload = {};
  row.querySelectorAll('[data-field]').forEach(el => {
    payload[el.dataset.field] = el.value;
  });
  return payload;
}

async function saveRow(row){
  const id = row.dataset.weaponId;
  const out = row.querySelector('output');
  out.textContent = 'Saving...';
  out.className = '';
  try{
    const res = await fetch(`/arsenal/audit/weapon/${encodeURIComponent(id)}`, {
      method:'POST',
      headers:{'content-type':'application/json','accept':'application/json'},
      body:JSON.stringify(collectRow(row)),
    });
    const data = await res.json();
    if(!res.ok || !data.ok){
      const errors = data.errors || {};
      out.textContent = Object.values(errors).join(' ') || 'Save failed.';
      out.className = 'is-error';
      return;
    }
    out.textContent = 'Saved';
    out.className = 'is-saved';
  }catch(err){
    out.textContent = esc(err.message || 'Save failed.');
    out.className = 'is-error';
  }
}

document.addEventListener('click', event => {
  const btn = event.target.closest('[data-audit-save]');
  if(!btn) return;
  const row = btn.closest('[data-weapon-id]');
  if(row) saveRow(row);
});
