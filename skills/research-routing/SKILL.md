---
name: research-routing
description: Route literature / docs / source-code research to the right installed MCP or tool instead of relying on model memory. Use when investigating papers, official docs, third-party library/API/CLI/config/version behavior, or open-source repo implementations during design, planning, or debugging.
---

# External Research Routing

When a task needs literature, external web material, official docs, third-party library/API/CLI/config details, or open-source repo investigation, use the installed evidence tools first — do not answer from memory alone.

| Research target | Tool |
| --- | --- |
| Version-sensitive library / framework / SDK / CLI: API, config, version diff, error semantics | Context7 (`resolve-library-id` then `query-docs`) |
| Papers, surveys, blogs, official web pages, multi-source synthesis | Tavily (`search` for quick facts / `research` for deep multi-source / `extract` for a known URL / `crawl` for a docs tree) |
| Open-source repo implementation, issues, PRs, commits, file contents | GitHub (`search_repositories` / `search_code` / `get_file_contents`) or `gh` CLI |

## Discipline

- If a turn legitimately needs ≥3 different libraries, dispatch a docs-researcher subagent instead of querying inline (keep main context clean).
- Cite sources in research/spec/plan/retro outputs (URL / repo / commit) and note applicability boundaries.
- Privacy: never send secrets, credentials, private snippets, or unnecessary workspace paths into queries — only generic API/concept/method names and public errors.
- Workspace-trust fallback: if external evidence contradicts an established workspace fact/contract, preserve the workspace fact by default and ask the user before changing behavior.
- Add a one-line attribution in the reply when a lookup was actually performed (e.g. `已查 Context7 (/org/project): …`).
