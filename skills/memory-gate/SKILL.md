---
name: memory-gate
description: Diff-review gate for persistent agent memory (AGENTS.md) updates. Use whenever an agent (or the continual-learning flow) proposes editing AGENTS.md / long-term project memory, so no agent silently overwrites or compresses it.
---

# Memory Update Gate

No agent may directly overwrite `AGENTS.md` (or the equivalent long-term memory file). Memory edits go through a two-rail diff-review gate.

## Rail 1 — the proposing subagent writes a proposal, not the file

The memory-updater subagent MUST:
1. Only consider new/changed transcripts (incremental; use the index/state file if present).
2. Compute proposed adds / in-place edits / deletes for durable, recurring user preferences and stable workspace facts only — exclude one-off corrections, transient numbers, secrets, and anything invalid after one commit.
3. Write the full post-merge view to a side proposal file (e.g. `.cursor/hooks/state/continual-learning-proposal.md`) with the same section layout plus a `## Proposed Diff Summary` enumerating each `ADD/MODIFY/DELETE [section] — reason — source-transcript`.
4. NOT aggressively dedupe/compress/merge existing bullets to hit any per-section cap; bullets here are intentionally long, dense, single-bullet contracts. If a section legitimately exceeds ~18 bullets, PROPOSE splitting into sub-sections (do not auto-apply).
5. Reply exactly one line: `Proposal written to <path> (N adds, M modifies, K deletes). Please review and approve before merge.` or `No high-signal memory updates.`

## Rail 2 — main agent verifies no direct write happened

1. Record the memory file's hash before dispatch.
2. After the subagent returns, recompute the hash. If it changed, the subagent violated the gate: quarantine its content into the proposal file with a QUARANTINED header, `git checkout -- <memory file>` to roll back, and tell the user.
3. Only a human ports approved bullets into the memory file (or explicitly instructs which entries to apply). Never auto-merge the proposal.

## Note

The auto-trigger hook is Cursor-plugin specific. Without it (e.g. OpenCode), memory updates become manual but this gate discipline still applies.
