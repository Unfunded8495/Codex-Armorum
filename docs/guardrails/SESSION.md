# SESSION.md - long-session survival

Trigger: the session passes 10 user messages, or the context window was compacted, or you notice you cannot recall an earlier decision precisely.

## S1. Post-compaction recovery (run immediately after any compaction)
1. Re-read CLAUDE.md.
2. Re-read docs/STATE.md.
3. Run `git status` and `git diff --stat`. Paste both.
4. Treat all remembered file contents as stale: re-read before any edit (IR1 hardens to "re-read everything").
5. Restate `ANCHOR:` (S4) before the next action.

## S2. docs/STATE.md template (create at task start for any multi-step task)
```
# STATE
GOAL: <one sentence>
BASELINE: <from PLAN P4>
PLAN:
  1. [x] <step> - verified by <what>
  2. [ ] <step>
DECISIONS:
  - DECISION: <choice> because <reason> (<date>)
OPEN QUESTIONS:
  - <thing awaiting the user>
ATTEMPT LEDGER: <mirrored from DEBUG D5 when debugging>
NEXT: <the single next action>
```

## S3. Same-turn update triggers (update STATE.md in the same turn as the event, not "later")
- a plan step completes or fails
- a DECISION is made
- a PLAN CHANGE occurs
- immediately BEFORE any risky or hard-to-reverse operation
- every 10 user messages regardless

## S4. ANCHOR
Every 10 user messages, and after every compaction, emit:
```
ANCHOR: goal=<GOAL> | step=<current plan step> | next=<NEXT>
```
If what you are currently doing does not serve the ANCHOR, you have drifted: stop and either log a DETOUR or return.

## S5. Detours
Leaving the plan to chase something (a distracting bug, a side improvement) requires:
```
DETOUR(<reason>): <what you are doing instead>
```
and on return:
```
RETURNING: <plan step resumed>
```
A detour with no RETURNING within 10 messages is abandonment: surface it to the user.

## S6. Decision ledger
Any choice that constrains later work (schema shape, endpoint contract, library selection, naming scheme) gets a `DECISION:` line in STATE.md the same turn. Re-deciding an already-logged decision requires quoting the original and saying why it changes.

## S7. Session end
Before the session closes or hands over: STATE.md updated, NEXT accurate, environment cold (CODE.md C15), and a 5-line handover summary the next session (or the user) can act on without archaeology.
