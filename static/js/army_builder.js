import { showArmyList, deleteArmy, toggleCreateForm, importArmyList,
         submitCreateArmy, onCafBattleSize } from './army-list.js';
import { showArmy, saveArmyMeta, updateSquadSize, updateAssigned,
         toggleEnhEditor, saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord,
         attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
         toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
         toggleWargear, setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, toggleWgCard, wgNudge, exportArmy,
         openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill, toggleCbDatasheet,
         openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit } from './army-detail.js';
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

// Escape closes whichever full-screen overlay is open (unit picker, Command
// Bunker, or Edit Roster); harmless no-op on the ones already hidden.
initLightbox(()=>{
  ['unitPickerModal', 'commandBunker', 'editRosterModal'].forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.hidden = true;
  });
});
refreshLedger();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  deleteArmy, toggleCreateForm, submitCreateArmy, onCafBattleSize,
  saveArmyMeta, updateSquadSize, updateAssigned,
  toggleEnhEditor, saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord, attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
  toggleDetachmentCard, removeDetachment, toggleDpExpand, selectUnit, clearRight, toggleUnitProfiles,
  toggleWargear, setWargearStep, setWargearRadio, setWargearSlot, setWargearBundleCount, toggleWgCard, wgNudge,
  openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy, togglePickerProfile,
  openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill, toggleCbDatasheet,
  openEditRoster, closeEditRoster, editRosterShow, duplicateRoster, jumpToUnit,
  exportArmy, importArmyList,
});

router();
