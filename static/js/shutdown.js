const shutdownBtn = document.querySelector('[data-shutdown-btn]');
let confirmTimer = null;

function setShutdownLabel(label){
  if(!shutdownBtn) return;
  shutdownBtn.innerHTML = `<span class="seal-vault-mark" aria-hidden="true"></span><span>${label}</span>`;
}

function showSealedState(){
  if(!shutdownBtn) return;
  document.body.classList.add('app-sealed');
  setShutdownLabel('Vault Sealed');

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
    setShutdownLabel('Confirm?');
    confirmTimer = setTimeout(() => {
      shutdownBtn.classList.remove('is-confirming');
      setShutdownLabel('Seal Vault');
    }, 3000);
    return;
  }

  clearTimeout(confirmTimer);
  shutdownBtn.classList.remove('is-confirming');
  shutdownBtn.disabled = true;
  setShutdownLabel('Sealing...');

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
    setShutdownLabel('Seal Vault');
    window.alert('The shutdown rite failed. Check the terminal.');
  }
}

if(shutdownBtn){
  shutdownBtn.addEventListener('click', sealVault);
}
