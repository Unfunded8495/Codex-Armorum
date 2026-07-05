# PLAN.md - before starting non-trivial work

Trigger: a task that touches more than 1 file or more than 20 lines, or any task whose scope you cannot state in one sentence.

## P1. TASK block (paste this, filled in, before any edit)
```
TRIGGER: <the user request, restated in one sentence>
GOAL: <the observable end state>
FILES: <files you expect to touch, with why>
EST: <rough size: files / lines>
DONE-WHEN: <a concrete check you will run and paste at VERIFY, e.g. "pytest tests/test_roster.py passes and POST /api/list returns 201">
```
A DONE-WHEN that cannot be executed and pasted is invalid. Rewrite it until it is a command or a specific manual check.

## P2. Premise check
If the request presupposes a fact about the codebase ("the export script writes JSON", "the points field is on the unit table"), verify that fact with a grep or read BEFORE planning around it. Paste the evidence. If the premise is false, tell the user before proceeding.

## P3. Prior art search
Before writing any new function, helper, endpoint, or utility: grep for 2-3 plausible existing names first. Paste the grep. If something similar exists, extend or reuse it; do not write a parallel implementation.

## P4. Baseline
Before the first edit, run the project test suite (or the smoke command in CLAUDE.md ## Project) and record:
```
BASELINE: <pass | N failures, listed>
```
Pre-existing failures are not yours to fix unless asked, and you must not be blamed by them at VERIFY. No baseline means you cannot tell your breakage from old breakage.

## P5. Decomposition
If EST exceeds 3 files or 100 lines: number the steps. Each step must be independently verifiable (it compiles, a test passes, an endpoint responds). Do not start step N+1 while step N is unverified.

## P6. Ask vs decide
| Situation | Action |
|---|---|
| Could delete or transform user data | Ask (IR9 applies regardless) |
| Changes external behaviour: API shape, URL, file format, UI flow | Ask |
| Two reasonable interpretations with different scope | Ask, offering both |
| Internal naming, ordering, private structure | Decide, record `ASSUMPTION:` |
| Trivial and reversible | Decide silently |

## P7. Plan approval (only if switched ON in CLAUDE.md ## Project)
Stop after pasting the TASK block, decomposition, and any ASSUMPTION lines. Do not edit until the user approves.

## P8. Deviating from an approved plan
Any change of FILES, approach, or scope mid-task gets a line:
```
PLAN CHANGE: <what changed and why>
```
Two PLAN CHANGE lines in one task means the plan was wrong: stop and re-plan with the user.

## P9. Do not start what you cannot finish
If the task needs credentials, hardware, a running service, or user data you do not have, say so at plan time, not after 40 messages of scaffolding.
