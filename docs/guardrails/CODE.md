# CODE.md - while editing

Trigger: about to make the first edit of a task. Re-consult C14 whenever you rename, remove, or change the signature of anything.

## C1. Read before edit
Read the full function you are changing plus at least one caller. Editing from a snippet or from memory of the file is the number one source of introduced bugs. If your last read of the file predates any edit to it, re-read.

## C2. Re-read after a failed patch
If a str_replace or patch fails to apply, the file is not what you think it is. Re-read the region before retrying. Never "fix" a failed patch by loosening the match blindly.

## C3. Twin files
Before editing file X, name its twins and check each:
- its test file
- its template / static JS (Flask: route twin is usually a template and a JS file)
- schema or migration files if a model changed
- docs or README sections that describe the behaviour
List them in one line: `TWINS: <files or "none">`. An edit that changes behaviour without touching a stale twin ships a lie.

## C4. Generated files
If a file header, path, or CLAUDE.md marks it as generated (exports, build output, lockfiles, w40k exports and the like): do not hand-edit (HS3). Find the generator, change the source, regenerate.

## C5. Signature and contract changes
Changing a function signature, route path, JSON shape, DB column, or config key triggers the REFERENCE SWEEP (C14) before the task can end.

## C6. Copy-paste check
After duplicating any block (a second route, a parallel if-branch, a similar test): re-read the copy and diff every field that should differ (names, IDs, columns, messages). Copy-paste with one unchanged field is a classic silent bug.

## C7. Trap categories
The moment the code you are writing involves dates/times, epochs, money, floats, regex, async, sorting, mutation of shared structures, closures in loops, or raw SQL: open docs/guardrails/TRAPS.md at the matching section before writing the line, not after it fails.

## C8. Error handling
Match the file's existing convention (exceptions vs error returns, logging style, HTTP error shape). Do not introduce a second convention. Never swallow an exception with a bare `except: pass` you were not asked for.

## C9. Imports and definitions at edit time
When you use a new symbol, add its import in the same edit. When you delete the last use of a symbol, check whether its import is now dead and remove it.

## C10. Unverified APIs
If you are not certain of a library call's signature or return shape, check the installed package source or its docs in the repo environment. If you cannot check, write the call and label it on the same line:
```
# SIGNATURE UNVERIFIED: confirm arg order for X
```
That label must be resolved or surfaced to the user before VERIFY passes (V5).

## C11. Style
Match the surrounding file: quote style, naming, spacing, comment tone. Zero drive-by reformatting (IR7). Project bans (e.g. no em dashes) apply to every character you emit.

## C12. Boundaries
For every loop, slice, and comparison you write, answer in your head: first element, last element, empty input, off-by-one at each end. If the answer is not obvious, write the edge-case test now.

## C13. Deleting code
Before deleting a function, route, template block, or config key: grep its name. Paste the grep. Delete only at zero live references, or update the references in the same task.

## C14. REFERENCE SWEEP (RS1-RS5)
Run when anything was renamed, removed, moved, or re-signed:
- RS1. List every changed symbol: old name, new name/shape.
- RS2. Grep the repo for each old symbol AND each changed call pattern. Paste the output.
- RS3. Classify every hit: `updated` / `intentional` (e.g. changelog, migration) / `MISSED`.
- RS4. Fix every MISSED hit.
- RS5. Re-grep to show zero MISSED. Paste it. `RS5: CLEAN` goes in your VERIFY block.

## C15. Leave the environment cold
When testing is finished, stop everything you started (dev servers, watchers, containers) and say so. The user starts the app themselves.
