import { showArmyList, deleteArmy, toggleCreateForm, importArmyList,
         submitCreateArmy, onCafBattleSize } from './army-list.js';
import { showArmy, saveArmyMeta, updateSquadSize,
         saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord,
         attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
         toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
         setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, setWargearPlace,
         toggleWgCard, wgNudge, exportArmy, exportDatasheetsPdf,
         openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill,
         openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit,
         openDatasheetCard, closeDatasheetCard, closeAllOverlays } from './army-detail.js';
import { openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy, togglePickerProfile } from './unit-picker.js';
import { initLightbox } from './lightbox.js';
import { refreshLedger } from './header.js';

/* ---- routing ------------------------------------------------------------ */
function router(){
  const h = location.hash.slice(1) || '/';
  const p = h.split('/').filter(Boolean);
  if(p[0]==='army' && p[1]) return showArmy(p[1]);
  showArmyList();
}

window.addEventListener('hashchange', router);

// Escape closes whichever drawer/overlay is open (unit picker, Command
// Bunker, Edit Roster, or the datasheet card); no-op when none is.
initLightbox(closeAllOverlays);
refreshLedger();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  deleteArmy, toggleCreateForm, submitCreateArmy, onCafBattleSize,
  saveArmyMeta, updateSquadSize,
  saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord, attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
  toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
  setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, setWargearPlace, toggleWgCard, wgNudge,
  openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy, togglePickerProfile,
  openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill,
  openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit,
  openDatasheetCard, closeDatasheetCard, closeAllOverlays,
  exportArmy, exportDatasheetsPdf, importArmyList,
});

router();
