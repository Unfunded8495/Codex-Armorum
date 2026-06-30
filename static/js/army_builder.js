import { showArmyList, deleteArmy, toggleCreateForm, importArmyList,
         submitCreateArmy, onCafBattleSize } from './army-list.js';
import { showArmy, saveArmyMeta, updateSquadSize, updateAssigned,
         toggleEnhEditor, saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord,
         attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
         toggleDetachmentCard, removeDetachment, toggleDpExpand, selectConfig, selectUnit, clearRight, toggleUnitProfiles,
         toggleWargear, setWargearStep, setWargearRadio, setWargearSlot, toggleWgCard, exportArmy,
         openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill, toggleCbDatasheet } from './army-detail.js';
import { openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy } from './unit-picker.js';
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

// Escape closes whichever full-screen overlay is open (unit picker or
// Command Bunker); harmless no-op on the one that's already hidden.
initLightbox(()=>{
  const picker = document.getElementById('unitPickerModal');
  if(picker) picker.hidden = true;
  const bunker = document.getElementById('commandBunker');
  if(bunker) bunker.hidden = true;
});
refreshLedger();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  deleteArmy, toggleCreateForm, submitCreateArmy, onCafBattleSize,
  saveArmyMeta, updateSquadSize, updateAssigned,
  toggleEnhEditor, saveEnhancement, chooseEnhancement, removeArmyUnit, duplicateArmyUnit, toggleKebabMenu, toggleWarlord, attachLeader, detachLeader, onAbBattleSize, toggleAccordion, toggleOptBody,
  toggleDetachmentCard, removeDetachment, toggleDpExpand, selectConfig, selectUnit, clearRight, toggleUnitProfiles,
  toggleWargear, setWargearStep, setWargearRadio, setWargearSlot, toggleWgCard,
  openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy,
  openCommandBunker, closeCommandBunker, toggleCbSection, toggleStratPill, toggleCbDatasheet,
  exportArmy, importArmyList,
});

router();
