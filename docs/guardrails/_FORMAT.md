# _FORMAT.md - contracts for editing the kit itself

These rules apply to anyone (human or model) editing kit files. They exist because the kit's value degrades fast if rules multiply, drift, or duplicate.

- F1. Budgets. CLAUDE.md kit core: 60 lines hard cap. Each guardrail doc: 80 lines target, 120 hard cap. `## Project` section: 40 lines. Adding a rule over budget requires deleting or merging one.
- F2. Event-phrased triggers. Every doc opens with "Trigger:" phrased as something the model literally experiences ("a test failed", "about to type done"), never a topic label ("debugging", "quality").
- F3. Countable, not graded. Rules use numbers (2 attempts, 10 messages, 300 lines, 5 files), never judgment words (soon, large, carefully, appropriately) as the operative condition.
- F4. Prohibitions carry replacements. Every NEVER states the replacement action on the same line or the next.
- F5. Paste, not promise. Every rule that can produce a transcript artifact must name it (a marker like CAUSE:, a pasted grep, a status word). A rule whose compliance is invisible in the transcript is redesigned or cut.
- F6. Single source. Each rule lives in exactly one file; other files reference it by ID (e.g. "IR9 applies"). Exception: a CLAUDE.md iron rule may compress a doc rule it points to.
- F7. Sanctioned compressed pairs (keep semantically aligned when editing either side): IR2/V1, IR3/D1, IR4/D3-D4, IR5/D6, IR9/V12, IR10/C14, IR11/V rule zero.
- F8. Stable IDs. Rule IDs (IR, HS, P, C, T, D, V, E, S, RS) are never renumbered; retired rules leave a tombstone line ("C16. retired v1.1").
- F9. Vocabulary. Status words are only those defined in VERIFY.md. Markers are UPPERCASE followed by a colon. No synonyms.
- F10. No em dashes anywhere in kit files.
