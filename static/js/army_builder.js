import { showArmyList, deleteArmy, toggleCreateForm, importArmyList,
         submitCreateArmy, onCafBattleSize } from './army-list.js';
import { showArmy, saveArmyMeta, updateSquadSize,
         saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord,
         attachLeader, detachLeader, onAbBattleSize, onRailBattleSize, toggleAccordion, toggleOptBody,
         toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
         setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, setWargearPlace,
         toggleWgCard, wgNudge, exportArmy, exportDatasheetsPdf,
         openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill,
         openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit,
         jumpToValidation, jumpToFoc,
         openDatasheetCard, closeDatasheetCard, closeAllOverlays } from './army-detail.js';
import { openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy, togglePickerProfile } from './unit-picker.js';
import { initLightbox } from './lightbox.js';
import { refreshLedger } from './header.js';

/* ---- routing ------------------------------------------------------------ */
// body.ab-roster scopes the manual (paper) reskin to the roster detail view;
// the army list/create screen keeps the dark app chrome.
function router(){
  const h = location.hash.slice(1) || '/';
  const p = h.split('/').filter(Boolean);
  const isRoster = p[0]==='army' && !!p[1];
  document.body.classList.toggle('ab-roster', isRoster);
  if(isRoster) return showArmy(p[1]);
  showArmyList();
}

window.addEventListener('hashchange', router);

/* ---- manual-page chrome: shared reading-mode toggle (same key as /rules) - */
const THEME_KEY = 'caRules.theme';
const themeBtn = document.getElementById('abThemeBtn');
const themeLabel = document.getElementById('abThemeLabel');
function applyTheme(t){
  if(t === 'dark') document.body.setAttribute('data-rl-theme', 'dark');
  else document.body.removeAttribute('data-rl-theme');
  if(themeLabel) themeLabel.textContent = t === 'dark' ? 'Light' : 'Dark';
}
try{ applyTheme(localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'); }
catch(e){ applyTheme('light'); }
themeBtn?.addEventListener('click', ()=>{
  const t = document.body.getAttribute('data-rl-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(t);
  try{ localStorage.setItem(THEME_KEY, t); }catch(e){}
});

// Escape closes whichever drawer/overlay is open (unit picker, Command
// Bunker, Edit Roster, or the datasheet card); no-op when none is.
initLightbox(closeAllOverlays);
refreshLedger();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  deleteArmy, toggleCreateForm, submitCreateArmy, onCafBattleSize,
  saveArmyMeta, updateSquadSize,
  saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord, attachLeader, detachLeader, onAbBattleSize, onRailBattleSize, toggleAccordion, toggleOptBody,
  toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
  setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, setWargearPlace, toggleWgCard, wgNudge,
  openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy, togglePickerProfile,
  openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill,
  openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit,
  jumpToValidation, jumpToFoc,
  openDatasheetCard, closeDatasheetCard, closeAllOverlays,
  exportArmy, exportDatasheetsPdf, importArmyList,
});

router();
