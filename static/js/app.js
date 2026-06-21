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
  const h = location.hash.slice(1) || '/';
  const p = h.split('/').filter(Boolean);
  if(p[0]==='purchases')          return routePurchases(p[1] ? decodeURIComponent(p[1]) : null);
  if(p[0]==='history')            return p[1] ? showHistoryFaction(decodeURIComponent(p[1])) : showHistory();
  // Chapter faction ids carry "::" and a space (e.g. "SM::Blood Angels"); the
  // browser percent-encodes the space in the hash, so decode each id segment
  // before handing it to the view (matches the history route above).
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
