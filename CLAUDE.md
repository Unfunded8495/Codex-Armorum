# Model gate (read first)
The rules below assume an Opus-class model. Check the model name in your
system prompt before applying them:
- Opus, Sonnet, or Haiku: every rule applies in full.
- Fable or Mythos class: the scaffolding rules listed next are advisory;
  use judgement. Everything else, including all Hard stops and the whole
  Project section, still applies in full.

Scaffolding rules (advisory on Fable/Mythos, mandatory otherwise):
- The whole Routing table (mandatory guardrail-doc reads).
- IR4 (CAUSE line and revert ceremony), IR5 (two-strike escalation),
  IR10 (paste the grep), IR11 (quote, do not summarise).
- The "Plan first" line in the Project section (PLAN.md P7): on Fable,
  small low-risk tasks may proceed without a pre-approved plan; still
  present a plan and wait for approval on anything touching data files,
  IDs, migrations, or the catalogue.

<!-- BEGIN KIT CORE v1.0 - do not edit inside these markers, upgrades replace this block wholesale -->
# Operating Rules (always apply)

## Iron rules
- IR1. Read a file before editing it. If any edit has touched it since your last read, re-read before the next edit.
- IR2. Never claim code works, passes, or is fixed without running it this session and pasting the output. Unrun code is labelled `EDITED-UNVERIFIED`.
- IR3. Reproduce a bug before fixing it. No reproduction means no fix: label `CANNOT-REPRODUCE` and ask.
- IR4. One hypothesis per fix. Write a `CAUSE:` line before editing. If the edit does not confirm the cause, revert it before trying anything else.
- IR5. After 2 failed fix attempts on the same symptom, stop editing and open docs/guardrails/DEBUG.md (escalation ladder D6).
- IR6. Never add a dependency, framework, or build step without asking. Name the stdlib or vanilla alternative you rejected.
- IR7. Make the smallest change that fully solves the task. Do not refactor, rename, or reformat code you were not asked to touch.
- IR8. Ambiguous on scope, data, or external behaviour: ask. Ambiguous only on trivial internals: decide and record `ASSUMPTION:` in your reply.
- IR9. Never run destructive or irreversible operations inline. Write a separate deferred script and hand it to the user to run.
- IR10. Before finishing, grep every symbol you renamed, removed, or re-signed. Paste the grep. Non-zero unhandled hits means the task is not done.
- IR11. Quote, do not summarise: any claim about file contents, test results, or command output must include lines pasted from a tool result in the same turn.
- IR12. If a rule here conflicts with an explicit user instruction in this session, the user wins. Say which rule you are overriding.

## Routing table (when the left column literally happens, your NEXT tool call is reading the doc on the right, alone in its message)
| Event | Read |
|---|---|
| Starting a task that touches >1 file or >20 lines | docs/guardrails/PLAN.md |
| About to make the first edit of a task | docs/guardrails/CODE.md |
| About to write date/time, money, float, regex, async, sort, mutation, or SQL logic | docs/guardrails/TRAPS.md (relevant section) |
| A test failed, a command errored, or output surprised you | docs/guardrails/DEBUG.md |
| About to type "done", "fixed", "works", or to commit | docs/guardrails/VERIFY.md |
| About to read a file >300 lines, or context feels heavy | docs/guardrails/EFFICIENCY.md |
| Session passes 10 user messages, or context was compacted | docs/guardrails/SESSION.md |

## Hard stops (never do these; state the block and ask instead)
- HS1. `git push --force`, history rewrites, branch deletion.
- HS2. Dropping or altering DB tables, deleting user data files, emptying directories.
- HS3. Hand-editing generated files (exports, build output, lockfiles). Regenerate instead.
- HS4. Writing secrets, keys, or tokens into code, config, or commits, even as examples.
<!-- END KIT CORE -->

## Project
<!-- Project-specific facts and rules. Cap: 40 lines. Anything conditional or long goes in docs/guardrails/PROJECT.md with a one-line pointer here. -->
- READ docs/guardrails/PROJECT.md (PR1-PR6) before touching data files, IDs, the army builder, or the manual-style UI: it routes to the deep-dive docs and holds the traps (three ID systems, post-change gates, data ownership, CSS scoping).
- Stack: Flask + SQLite + vanilla JS. No build step. Deployed via Docker on QNAP NAS.
- Run: `python app.py` (dev). Stop the server after testing; leave nothing running.
- No em dashes anywhere: not in code, comments, UI strings, docs, or commit messages.
- Deliver complete files, not diffs or snippets, when handing code to the user.
- Plan first: present the plan and wait for approval before writing code (PLAN.md P7 is ON).
- Destructive operations (migrations, deletions, bulk updates) go in separate deferred scripts per IR9.
- No new dependencies without written justification per IR6.
