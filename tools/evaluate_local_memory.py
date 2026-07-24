"""Deterministically evaluate local-memory retrieval and isolation contracts."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_memory import MemoryStore


CASES = (
    ("concise summaries", "I prefer concise summaries."),
    ("focused regression", "I prefer focused regression tests."),
    ("explicit errors", "I prefer explicit error messages."),
    ("small changes", "I prefer small focused changes."),
    ("independent review", "I prefer independent review before merge."),
    ("atomic rollback", "I prefer atomic rollback for failed migrations."),
    ("source provenance", "I prefer source provenance in generated artifacts."),
    ("local only", "I prefer local-only persistence."),
    ("bounded context", "I prefer bounded context injection."),
    ("clear diagnostics", "I prefer clear diagnostics for failures."),
)


def evaluate() -> dict:
    """Return synthetic Recall@5, Precision@5, and isolation results."""
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        store = MemoryStore(root)
        for query, text in CASES:
            outcome = store.capture(text, outcome="success")
            if outcome["promoted"] != 1:
                raise RuntimeError(f"synthetic memory did not promote: {query}")
        recall_hits = precision_total = precision_hits = 0
        for query, _ in CASES:
            results = store.search(query, limit=5)
            relevant = [row for row in results if query.split()[0] in row["summary"].lower()]
            recall_hits += bool(relevant)
            precision_total += len(results)
            precision_hits += len(relevant)

        project = root / "project"
        project.mkdir()
        project_store = MemoryStore(root, scope="project", project_root=project)
        project_store.capture(
            "Project convention: run focused tests before changing production code.",
            outcome="success",
        )
        other_project = root / "other"
        other_project.mkdir()
        return {
            "cases": len(CASES),
            "recall_at_5": recall_hits / len(CASES),
            "precision_at_5": precision_hits / precision_total,
            "cross_namespace_leaks": int(
                bool(store.search("production code", limit=5))
                or bool(
                    MemoryStore(root, scope="project", project_root=other_project).search(
                        "production code", limit=5
                    )
                )
            ),
        }


def main() -> int:
    report = evaluate()
    print(json.dumps(report, sort_keys=True))
    return int(
        report["recall_at_5"] < 0.85
        or report["precision_at_5"] < 0.90
        or report["cross_namespace_leaks"] != 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
