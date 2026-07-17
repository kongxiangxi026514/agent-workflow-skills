# Persistent Memory Gate

Never let an updater directly overwrite the long-term memory file. Treat automatic memory hooks and explicit persistent-memory requests as an exclusive R2 path.

## Proposal rail

Process only new or changed transcripts. Keep durable recurring preferences and stable workspace facts; exclude secrets, transient experiment values, one-off corrections, and details invalidated by a normal commit. Write the complete proposed post-merge memory to a side proposal with an `ADD`, `MODIFY`, or `DELETE` summary, reason, and source transcript for each change. Do not compress dense existing contracts merely to satisfy a bullet limit.

## Verification rail

The parent records the memory file hash before dispatch and compares it afterward. If the hash changed, preserve the attempted content in a quarantined proposal, restore the exact baseline, verify the hash, and report the violation. Never auto-merge a proposal.

Only a human may approve specific entries for application. Refreshing an incremental transcript index is allowed when that state file is explicitly owned by the memory workflow. A no-update result must leave the memory file byte-identical.
