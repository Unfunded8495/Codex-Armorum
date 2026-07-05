# Guardrails Kit v1.0 (Dazz edition)

A portable CLAUDE.md plus documentation set that pushes Claude Opus / Sonnet inside Claude Code toward frontier-level behaviour: fewer logic errors, fewer introduced bugs, fewer wasted tokens. It converts the implicit judgment a stronger model applies automatically into explicit, checkable, event-triggered procedures a weaker model can execute mechanically.

Written from scratch by Claude Fable 5. Structure inspired by the public Guardrails Kit pattern; all rule text is original and tuned to your conventions (no em dashes, complete files not diffs, plan approval before code, deferred destructive scripts, environment left cold after testing, Flask/SQLite/vanilla JS stack).

## What's in the kit
| File | Role |
|---|---|
| `CLAUDE.md` | Always-loaded core: 12 iron rules (IR1-IR12), an event-phrased routing table, 4 hard stops (HS1-HS4), and a prefilled `## Project` section. |
| `docs/guardrails/PLAN.md` | Before non-trivial work: TASK block, premise check, prior-art search, baseline, decomposition, ask-vs-decide, plan approval. (P1-P9) |
| `docs/guardrails/CODE.md` | While editing: read-before-edit gates, twin files, copy-paste checks, and the REFERENCE SWEEP (RS1-RS5). (C1-C15) |
| `docs/guardrails/TRAPS.md` | Wrong-vs-right lookup tables for dates, epochs, mutation, async, floats/money, sort, division/modulo, regex, API lookalikes, closures, truthiness, SQL. (T1-T12) |
| `docs/guardrails/DEBUG.md` | When anything fails: reproduce-first, CAUSE line, attempt ledger, the ESCALATION LADDER, and the red-flag rationalisation table. (D1-D10) |
| `docs/guardrails/VERIFY.md` | Before claiming done: 12-item echo protocol; every claim needs output pasted from a real tool result. (V1-V12) |
| `docs/guardrails/EFFICIENCY.md` | Token discipline as paired rules: every "read less" rule has a "read enough" floor. (E1-E17) |
| `docs/guardrails/SESSION.md` | Long sessions: STATE.md template, same-turn update triggers, post-compaction recovery, ANCHOR/DETOUR/DECISION markers. (S1-S7) |
| `docs/guardrails/_FORMAT.md` | Contracts for editing the kit itself: budgets, event phrasing, countable thresholds, single-sourcing. (F1-F10) |
| `MIGRATE.md` | Retrofit procedure for a project with an existing CLAUDE.md: backup-first, per-line dispositions, user checkpoint, verbatim install, UPGRADE mode. |

## Install: fresh project
From the project root:
```
cp <kit>/CLAUDE.md CLAUDE.md
mkdir -p docs/guardrails
cp <kit>/docs/guardrails/*.md docs/guardrails/
```
Then edit the `## Project` section (it ships prefilled with your standing conventions; adjust the Run line per project). Never edit inside the BEGIN/END KIT CORE markers.

## Install: project with an existing CLAUDE.md (Codex Armorum, Codex Lucidus, Painting Cogitator)
Drop the kit folder somewhere reachable and tell the model:
> Read MIGRATE.md and execute it exactly, phase by phase.
Nothing is lost: snapshot first, every original line gets a logged disposition, conflicts are surfaced to you rather than silently resolved, and it stops for your approval before writing anything.

## Why it works
1. Lean core, on-demand playbooks. Only the small CLAUDE.md is always loaded; each doc is read at the moment its trigger fires, so depth and token thrift coexist.
2. Event-phrased routing. Weaker models route reliably on what they literally experience ("a test failed", "about to type done"), not on abstract topics.
3. Paste, don't promise. Every rule produces a greppable transcript artifact (CAUSE:, BASELINE:, RS5: CLEAN, V3: PASS). Compliance is visible; "I made sure" is not.
4. Numbers, not judgment. 2 failed attempts, 10 messages, 300 lines, 5 files. Models comply with countable thresholds and rationalise around graded ones.
5. Prohibitions carry replacements. Every NEVER names the alternative, because a banned action with no named substitute gets taken anyway under pressure.

## Auditing compliance
Grep any session transcript for the markers: `TRIGGER:`, `GOAL:`, `BASELINE:`, `ASSUMPTION:`, `PLAN CHANGE:`, `CAUSE:`, `ATTEMPT `, `WORKAROUND:`, `ANCHOR:`, `DETOUR(`, `RETURNING:`, `DECISION:`, `RS5: CLEAN`, `V3: PASS`, `HANDLED FAILURES:`, `EDITED-UNVERIFIED`, `CANNOT-REPRODUCE`, `SIGNATURE UNVERIFIED`, `NOTED (not done)`. Markers missing at the moments their triggers occurred are the non-compliance to tune.
