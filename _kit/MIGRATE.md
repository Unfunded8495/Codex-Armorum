# MIGRATE.md - retrofitting a project that already has a CLAUDE.md

Execute phase by phase, in order, pasting the required artifacts. Do not merge phases. Written to be executed by the model itself ("Read MIGRATE.md and execute it exactly, phase by phase").

## M0. Detect prior installation (idempotency)
Grep the project CLAUDE.md for `BEGIN KIT CORE`.
- Found: this project is already migrated. Switch to UPGRADE mode (U0-U4 below). Do not run M1-M5.
- Not found: continue.

## M1. Snapshot
```
cp CLAUDE.md CLAUDE.md.pre-kit.bak
```
Confirm the backup exists (`ls -la` pasted). No backup, no migration. If docs/guardrails/ already exists with non-kit content, stop and ask.

## M2. Inventory with dispositions
Read the existing CLAUDE.md in full. Produce a numbered table where EVERY original line (or contiguous block) gets exactly one disposition:
- `KEEP-PROJECT` - project fact or rule; will move to the `## Project` section verbatim.
- `DUPLICATE-OF-KIT <rule id>` - already covered by a kit rule; will be dropped, coverage cited.
- `CONFLICT <rule id>` - contradicts a kit rule; will be surfaced, never silently resolved.
- `OBSOLETE?` - looks stale; will be listed for the user to confirm.
Paste the full table. A line with no disposition is a migration error.

## M3. User checkpoint (mandatory stop)
Present: the disposition table, all CONFLICT items with a recommendation each, all OBSOLETE? items. Wait for explicit approval. The user resolves conflicts; the kit does not auto-win (IR12 logic applies at file scale).

## M4. Install kit files
Copy (never retype, never paraphrase) the kit's `docs/guardrails/*.md` into the project. Verify with a checksum or line count comparison per file, pasted. Kit files that would overwrite existing same-named files: stop and ask (should have been caught at M1).

## M5. Compose the new CLAUDE.md
Structure, in order:
1. The kit core block, copied verbatim between its `BEGIN/END KIT CORE` markers.
2. `## Project` built ONLY from KEEP-PROJECT lines, carried verbatim, plus conflict resolutions from M3. Cap 40 lines; overflow goes to docs/guardrails/PROJECT.md with a pointer line.
Then verify and paste:
- every KEEP-PROJECT line from M2 appears in the new file or in PROJECT.md (paste the check),
- the kit core block is byte-identical to the source (diff pasted, empty),
- the backup from M1 still exists.
Report `MIGRATION: DONE` with a summary of dropped DUPLICATE lines and their covering rule IDs.

## UPGRADE mode
- U0. Confirm `CLAUDE.md.pre-kit.bak` or a git-clean state exists; snapshot current CLAUDE.md as `CLAUDE.md.pre-upgrade.bak`.
- U1. Replace the text between `BEGIN KIT CORE` and `END KIT CORE` markers wholesale with the new kit core. Touch nothing outside the markers.
- U2. Replace each `docs/guardrails/*.md` kit file wholesale, except PROJECT.md (project-owned, never touched).
- U3. Diff old vs new kit core and list rules added/removed/changed for the user.
- U4. Report `UPGRADE: DONE` with the version line changed.
