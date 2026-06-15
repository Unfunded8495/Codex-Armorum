const lightbox = document.getElementById('lightbox');

export function openLightbox(url, cap){
  document.getElementById('lightboxImg').src = url;
  document.getElementById('lightboxCap').textContent = cap || '';
  lightbox.hidden = false;
}

export function initLightbox(onEscExtra){
  if(!lightbox) return;
  document.getElementById('lightboxClose').onclick = () => lightbox.hidden = true;
  lightbox.onclick = e => { if(e.target === lightbox) lightbox.hidden = true; };
  window.addEventListener('keydown', e => {
    if(e.key === 'Escape'){
      lightbox.hidden = true;
      if(onEscExtra) onEscExtra();
    }
  });
}
