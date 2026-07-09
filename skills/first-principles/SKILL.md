---
name: first-principles
description: First-principles analysis for hard, novel, or ambiguous design problems. Use when the approach is non-obvious, requirements/constraints are tangled, or before committing to an architecture. Decompose to irreducible elements and derive a solution from zero. Not for routine changes.
---

# First-Principles Analysis

**When to use / when to skip**: use it for genuinely hard / novel / ambiguous problems (non-obvious approach, tangled requirements and constraints, before finalizing an architecture — usually path C); skip it for routine changes (path A/B), don't ritualize.

Decompose the problem down to its irreducible elements, then derive from zero — instead of copying analogies from existing code. Four steps:

1. **Core requirements and constraints** — list the core requirements + hard constraints (system architecture, compliance / security, performance budget, data / contract invariants), clearly separating MUST from nice-to-have.
2. **Decompose into irreducible elements** — break the problem down to an irreducible granularity (e.g. each stage of the request path, CPU / IO / locks / network, data flow, failure modes); no compound, vague blocks allowed.
3. **Derive a solution from zero + flag uncertain assumptions** — derive bottom-up from the irreducible elements rather than by analogy to existing implementations; explicitly mark each uncertain point as `assumption: … (to be verified)`.
4. **Prioritization recommendation** — rank by impact × certainty × cost, and call out what to do first and what can be deferred.

## Closing self-check

Answer two metacognition questions: (1) What are you least confident about? (2) What is the biggest omission / what am I not aware of?
