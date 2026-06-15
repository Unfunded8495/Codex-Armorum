const shutdownBtn = document.querySelector('[data-shutdown-btn]');
let confirmTimer = null;

function showSealedState(){
  if(!shutdownBtn) return;
  document.body.classList.add('app-sealed');
  shutdownBtn.textContent = 'Vault Sealed';

  const banner = document.createElement('div');
  banner.className = 'shutdown-banner';
  banner.setAttribute('role', 'status');
  banner.innerHTML = '<strong>Vault Sealed</strong><span>Codex Armorum has stopped.</span>';
  document.body.appendChild(banner);
}

async function sealVault(){
  if(!shutdownBtn || shutdownBtn.disabled) return;

  if(!shutdownBtn.classList.contains('is-confirming')){
    shutdownBtn.classList.add('is-confirming');
    shutdownBtn.textContent = 'Confirm?';
    confirmTimer = setTimeout(() => {
      shutdownBtn.classList.remove('is-confirming');
      shutdownBtn.textContent = 'Seal Vault';
    }, 3000);
    return;
  }

  clearTimeout(confirmTimer);
  shutdownBtn.classList.remove('is-confirming');
  shutdownBtn.disabled = true;
  shutdownBtn.textContent = 'Sealing...';

  try{
    const response = await fetch('/api/shutdown', {
      method: 'POST',
      headers: {'Accept': 'application/json'},
      cache: 'no-store',
    });
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    showSealedState();
  }catch(err){
    shutdownBtn.disabled = false;
    shutdownBtn.textContent = 'Seal Vault';
    window.alert('The shutdown rite failed. Check the terminal.');
  }
}

if(shutdownBtn){
  shutdownBtn.addEventListener('click', sealVault);
}
