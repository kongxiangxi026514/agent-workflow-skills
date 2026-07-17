# First-Principles Analysis

Use this policy only for a hard, novel, or ambiguous decision; skip it for routine implementation.

1. Separate mandatory outcomes, invariants, safety limits, and compatibility constraints from preferences.
2. Decompose the system into irreducible data, state, control, trust, and failure elements. Replace vague compound stages with explicit interfaces.
3. Derive candidate behavior from those elements instead of copying an analogy. Mark every uncertain premise as an assumption with a verification method.
4. Compare the smallest viable options by impact, certainty, cost, reversibility, and operational risk. Recommend the first measurable step and defer speculative extension points.

Before committing to the design, state the least certain assumption and the largest likely omission. Use evidence or a bounded probe to resolve them when they could change the decision.
