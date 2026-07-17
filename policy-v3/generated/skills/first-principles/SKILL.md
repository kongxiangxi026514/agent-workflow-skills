---
name: first-principles
description: "Derive hard or ambiguous designs from irreducible requirements and constraints."
---
<!-- GENERATED; policy_id=P06; source=policy-v3/fragments/first-principles.md; source_sha256=8a6b985970d5757ab23082e989f5b03676fac629de9a8762beead743bd1b5307; registry_sha256=774f226f2600847405f2d0c038583e051108693286dad5a72490d793332a10ec -->

# First-Principles Analysis

Use this policy only for a hard, novel, or ambiguous decision; skip it for routine implementation.

1. Separate mandatory outcomes, invariants, safety limits, and compatibility constraints from preferences.
2. Decompose the system into irreducible data, state, control, trust, and failure elements. Replace vague compound stages with explicit interfaces.
3. Derive candidate behavior from those elements instead of copying an analogy. Mark every uncertain premise as an assumption with a verification method.
4. Compare the smallest viable options by impact, certainty, cost, reversibility, and operational risk. Recommend the first measurable step and defer speculative extension points.

Before committing to the design, state the least certain assumption and the largest likely omission. Use evidence or a bounded probe to resolve them when they could change the decision.
