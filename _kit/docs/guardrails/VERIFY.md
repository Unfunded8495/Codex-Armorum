# VERIFY.md - before claiming done, fixed, works, or committing

Trigger: about to type "done", "fixed", "works", "should be good", or to run git commit.

Rule zero: every checkmark below requires output pasted from a real tool result in the SAME turn or a directly preceding one this session. A claim without a quoted line is not verified (IR11). If an item does not apply, write `V<n>: N/A - <reason>`, do not skip it silently.

## Echo protocol
- V1. The exact command(s) you ran, with exit status, pasted.
- V2. Test suite result pasted and compared against `BASELINE:` from PLAN.md P4. New failures block done. Pre-existing failures are listed, not fixed silently.
- V3. The `DONE-WHEN:` check from the TASK block executed and pasted, ending in `V3: PASS`.
- V4. If anything was renamed/removed/re-signed: `RS5: CLEAN` with the final zero-hit grep pasted (CODE.md C14).
- V5. Zero remaining `EDITED-UNVERIFIED` or `SIGNATURE UNVERIFIED` labels, or each one surfaced to the user explicitly.
- V6. Read your own full diff top to bottom. List files changed vs the FILES estimate; every extra file gets one line of justification.
- V7. No leftover debug prints, commented-out blocks, TODO-without-owner, or dead imports introduced by this task.
- V8. Every new file imports/loads cleanly (run the import or load it once; paste).
- V9. UI or template changes: rendered and checked, with what you looked at stated; otherwise the summary carries `NOT VISUALLY VERIFIED`.
- V10. Behaviour changes are reflected in their twins (CODE.md C3): tests, docs, README, STATE.md.
- V11. `HANDLED FAILURES:` list every known-not-working case and why it is acceptable, or write `HANDLED FAILURES: none`.
- V12. Environment left cold: servers/watchers/containers you started are stopped (CODE.md C15), scratch files cleaned, and destructive scripts handed over unrun (IR9).

## Commit gate
Commit message states what changed and why in imperative mood, references the task, and contains no banned characters per project rules. Never commit with V2 or V3 failing. Never `git add -A` blind: name the files.

## Status vocabulary (use exactly these words)
- `DONE` - V1-V12 pass.
- `DONE WITH NOTES` - done, but V11 is non-empty.
- `BLOCKED` - cannot proceed without the user; say what you need.
- `NOTED (not done)` - a request you acknowledged but have not executed. Never let this masquerade as done.
