# EFFICIENCY.md - token and context discipline

Trigger: about to read a file over 300 lines, or context feels heavy. Every "read less" rule below is paired with a "read enough" floor, because under-reading causes the bugs that cost far more tokens than reading ever saves.

- E1. Grep before read: locate the region with a search, then read a targeted range.
  E2. Floor: the range must cover the whole function/class plus 10 lines either side, and at least one caller. Never edit from a grep snippet alone.

- E3. Do not re-read files that have not changed.
  E4. Floor: re-read any file after it was edited, after a failed patch (CODE.md C2), or if your last read is more than 10 messages old.

- E5. Summarise long command output in your reply.
  E6. Floor: error lines, assertion messages, and the lines required by VERIFY/DEBUG markers are quoted verbatim, never paraphrased.

- E7. Run the targeted test while iterating, not the whole suite each loop.
  E8. Floor: the full baseline suite runs once at PLAN P4 and once at VERIFY V2.

- E9. Batch edits: group all changes to one file into one pass where safe.
  E10. Floor: batching never spans a verification boundary; each PLAN P5 step still verifies before the next starts.

- E11. Exploration cap: when hunting for something, after 5 files or 8 tool calls without progress, stop and restate against GOAL what you actually know and what you are looking for, then choose a narrower probe.
  E12. Floor: do not declare "not found" without pasting the searches that came up empty.

- E13. Do not paste large unchanged code back into the conversation to "show context". Reference file and line range instead.
  E14. Floor: when the project requires complete files as deliverables, deliver complete files; the ban is on redundant echoes, not on required output.

- E15. Prefer computing over reading: a `wc -l`, `sqlite3 .schema`, or `python -c` probe often replaces reading hundreds of lines.
  E16. Floor: probes tell you shape, not semantics. Logic you are about to modify still gets read (E2).

- E17. If context was compacted or feels degraded, stop optimising tokens and go to SESSION.md S1 immediately. Recovery beats thrift.
