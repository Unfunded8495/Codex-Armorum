import { showHome, showFaction } from './home.js';
import { showPurchases, routePurchases, renderPurchasePreview, submitPurchase, deletePurchase,
         startBoxEditor, resetBoxEditor, renderBoxContentRows, searchBoxUnits,
         addUnitToBox, quickImportBoxText, saveBoxSet, deleteBoxSet,
         quickPurchase, switchToEditor, saveBoxRef, clearBoxRef,
         openPurchaseDetail, closePurchaseDetail } from './purchases.js';
import { showUnit } from './unit.js';
import { showMiniPage } from './mini-page.js';
import { showHistory, showHistoryFaction } from './history.js';
import { initLightbox } from './lightbox.js';
import { wireHomeButton } from './header.js';

/* ---- routing ------------------------------------------------------------ */
function router(){
  // Hash routes replace the whole SPA view, so each destination should start
  // at its own top instead of inheriting the previous screen's scroll offset.
  window.scrollTo(0, 0);
  const h = location.hash.slice(1) || '/';
  const p = h.split('/').filter(Boolean);
  // Paper views (home / faction / unit) each set their own body scope in their
  // show* fn. Clear every paper scope here before dispatching so a dark view
  // (purchases, history, mini) never inherits the light shell or its theme.
  document.body.classList.remove('rl-spa', 'home-armies', 'faction-roster', 'unit-sheet', 'mini-sheet');
  document.body.removeAttribute('data-rl-theme');
  if(p[0]==='purchases')          return routePurchases(p[1] ? decodeURIComponent(p[1]) : null);
  if(p[0]==='history')            return p[1] ? showHistoryFaction(decodeURIComponent(p[1])) : showHistory();
  if(p[0]==='faction' && p[1])    return showFaction(decodeURIComponent(p[1]), p[2] === 'browse');
  if(p[0]==='unit'    && p[1])    return showUnit(decodeURIComponent(p[1]));
  if(p[0]==='mini'    && p[1])    return showMiniPage(decodeURIComponent(p[1]));
  return showHome();
}

window.addEventListener('hashchange', router);
wireHomeButton(()=>{ location.hash = '/'; });

initLightbox();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  renderPurchasePreview, submitPurchase, deletePurchase,
  startBoxEditor, resetBoxEditor, renderBoxContentRows,
  searchBoxUnits, addUnitToBox, quickImportBoxText,
  saveBoxSet, deleteBoxSet,
  quickPurchase, switchToEditor,
  saveBoxRef, clearBoxRef,
  openPurchaseDetail, closePurchaseDetail,
});

router();
