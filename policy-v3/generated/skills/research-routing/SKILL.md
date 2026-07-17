---
name: research-routing
description: "Select evidence tools for external documentation, web, papers, and repositories."
---
<!-- GENERATED; policy_id=P02; source=policy-v3/fragments/research-routing.md; source_sha256=3e480469324da98f602ef58b789928951f46fed70fd35ff4c8ee4b6965865eeb; registry_sha256=a0f339fcdd0ef7577e2f20f614ca1a2c3408ca5591f3bd3690710a9b3963e1a9 -->

# Research Routing

Load this policy when the answer or implementation depends on current external evidence.

- Use current official documentation for version-sensitive library, framework, SDK, API, configuration, CLI, migration, and error-semantics questions.
- Use web search or multi-source research for papers, reports, official pages, comparisons, and recent developments.
- Use repository evidence for source code, issues, pull requests, commits, and release history.

Resolve the source identity before querying, keep requests generic, and never transmit secrets, credentials, private code, or unnecessary workspace paths. Cite URLs, repositories, versions, or commits and state applicability boundaries.

If external evidence conflicts with a local contract, preserve the local behavior and ask before changing it. Do not trigger this policy for local symbol lookup, ordinary refactoring, or an API already used correctly in nearby code. Record a short source attribution only when a lookup actually occurred.
