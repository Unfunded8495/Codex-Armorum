# DEBUG.md - when anything fails

Trigger: a test failed, a command errored, output surprised you, or the user reports a bug.

## D1. Reproduce first
Run the failing thing yourself and paste the failing output before touching any code. If you cannot reproduce it: label `CANNOT-REPRODUCE`, state what you tried, and ask for the exact steps/data. Do not fix a bug you have not seen (IR3).

## D2. Read the whole error
Quote the actual error line and the deepest frame of the stack trace in your reply. Not a paraphrase. Most wrong fixes come from acting on the error you expected instead of the error you got.

## D3. CAUSE line before any edit
```
CAUSE: <one sentence: mechanism, not symptom>
```
"The endpoint 500s" is a symptom. "unit_id is None because the join drops rows without wargear" is a cause. If you cannot write the cause, you are still investigating: add evidence (D5-style logging), do not edit logic.

## D4. One change at a time
One hypothesis, one edit, one re-run. If it did not confirm the cause, revert the edit (IR4) before the next attempt. Stacked failed edits create bugs you then debug on top of the original.

## D5. Failed-attempts ledger
Every attempt gets a line, kept in your replies (and mirrored to STATE.md in long sessions):
```
ATTEMPT 1: <change> | expected: <x> | observed: <y>
```

## D6. ESCALATION LADDER (mandatory after 2 failed attempts, IR5)
Stop editing. Climb in order, pasting evidence at each rung:
1. Re-read the full error output and the full failing function. Quote both.
2. Add targeted logging/prints at the boundary between "known good" and "suspect". Re-run. Paste.
3. Minimise the reproduction: smallest input, smallest code path that still fails.
4. Question the premise: is the bug even in the layer you are editing? Check data, config, environment, versions (D9).
5. Ask the user, pasting the ledger and the minimised repro. Asking at rung 5 with evidence is success, not failure.
Skipping rungs to "just try one more thing" is the failure mode this file exists to stop.

## D7. Red-flag phrases (if you catch yourself writing the left column, do the right column)
| Rationalisation | Mandated action |
|---|---|
| "That should fix it" / "This should work now" | You have not run it. Run it, paste output (IR2) |
| "Probably a caching / timing / environment issue" | That is a hypothesis. Test it explicitly at D6 rung 2 |
| "Let me just rewrite this function/module" | Rewrite destroys the evidence. Return to D3; rewrites need user approval |
| "The test must be wrong" | Maybe. Prove it: show the test asserts behaviour that contradicts the spec, then ask before changing the test |
| "I'll add a try/except around it" | Swallowing the error is not a fix. Find the cause |
| "It works on the happy path, edge case is unlikely" | Log it in HANDLED FAILURES (V11) and let the user decide |

## D8. Workarounds
A workaround (retry loop, sleep, special-case branch) is allowed only with user approval and a label at the site:
```
# WORKAROUND: <real cause still open> - <date>
```
and a line in your final summary.

## D9. Environment before blame
Before concluding library or interpreter misbehaviour: print the version, the resolved import path, and the config actually loaded. "Wrong venv / stale container / editing a different copy of the file" outranks "the library is broken" a hundred to one.

## D10. After the fix
Re-run the original reproduction (must now pass) AND the baseline suite from PLAN.md P4 (must match BASELINE). Paste both. A fix that breaks something else is not done.
