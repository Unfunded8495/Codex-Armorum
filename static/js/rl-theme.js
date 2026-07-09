/* =====================================================================
   static/js/rl-theme.js - shared light/dark reading mode for SPA paper views
   ---------------------------------------------------------------------
   The My Armies home, Faction Roster and Unit Datasheet all share one
   reading-mode toggle persisted to localStorage["caRules.theme"] (the same
   key the server-rendered manual pages use, so the whole app switches
   together). The theme is applied as body[data-rl-theme="dark"]; the
   --rl-* token blocks scoped to body.rl-spa (spa-shell.css) do the rest.
   ===================================================================== */

export function rlThemeMode(){
  try{ return localStorage.getItem('caRules.theme') === 'dark' ? 'dark' : 'light'; }
  catch(e){ return 'light'; }
}

export function rlPersistTheme(t){
  try{ localStorage.setItem('caRules.theme', t); }catch(e){}
}

/* Set the body attribute so the scoped tokens swap. Persists by default. */
export function rlApplyTheme(t, persist=true){
  document.body.setAttribute('data-rl-theme', t);
  if(persist) rlPersistTheme(t);
}

/* Markup for the strip's light/dark toggle button. The label shows the mode
   you would switch TO (Dark while light, Light while dark). */
export function rlThemeToggleHtml(){
  const label = rlThemeMode() === 'dark' ? 'Light' : 'Dark';
  return `<button type="button" class="rl-toggle" id="rlThemeToggle"
      title="Toggle light / dark reading mode">
      <span class="rl-toggle-dot"></span><span class="rl-toggle-label">${label}</span>
    </button>`;
}

/* Wire the toggle inside a freshly-rendered strip. Flips the mode, applies it,
   and updates the button label in place (no re-render, so no image reload). */
export function rlWireThemeToggle(root=document){
  const tt = root.querySelector('#rlThemeToggle');
  if(!tt) return;
  tt.addEventListener('click', ()=>{
    const next = rlThemeMode() === 'dark' ? 'light' : 'dark';
    rlApplyTheme(next);
    const lbl = tt.querySelector('.rl-toggle-label');
    if(lbl) lbl.textContent = next === 'dark' ? 'Light' : 'Dark';
  });
}
