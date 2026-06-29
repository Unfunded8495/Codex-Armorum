import { showArmyList, deleteArmy, toggleCreateForm,
         loadDetachmentsFor, submitCreateArmy, onCafBattleSize } from './army-list.js';
import { showArmy, saveArmyMeta, updateSquadSize, updateAssigned,
         toggleEnhEditor, saveEnhancement, removeArmyUnit, toggleWarlord,
         attachLeader, detachLeader, onAbBattleSize, toggleDetRule,
         toggleWargear, setWargearStep, setWargearRadio, setWargearSlot } from './army-detail.js';
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

initLightbox(()=>{ document.getElementById('unitPickerModal').hidden = true; });
refreshLedger();

/* ---- exports for inline onclick handlers in dynamically-rendered HTML --- */
Object.assign(window, {
  deleteArmy, toggleCreateForm, loadDetachmentsFor, submitCreateArmy, onCafBattleSize,
  saveArmyMeta, updateSquadSize, updateAssigned,
  toggleEnhEditor, saveEnhancement, removeArmyUnit, toggleWarlord, attachLeader, detachLeader, onAbBattleSize, toggleDetRule,
  toggleWargear, setWargearStep, setWargearRadio, setWargearSlot,
  openUnitPicker, filterPicker, closeUnitPicker, addUnitToArmy,
});

router();
