"""Audit policy-v3 budgets, provenance drift, and routing quality gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Mapping


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from tools.policy_router import load_registry, route_task, token_proxy
from tools.render_policy import detect_drift, expected_outputs, resolve_policy_paths


REQUIRED_FIELDS = {
    "policy_id", "name", "tier", "description", "trigger", "path_selectors",
    "risk", "budget_tokens", "source", "artifact", "on_demand",
}
MODEL_ID_PATTERN = re.compile(
    r"\b(?:gpt|claude|gemini|glm|qwen|llama|mistral)[-/]?[a-z0-9_.-]*\d",
    flags=re.IGNORECASE,
)


def validate_registry(root: Path | str, registry: dict) -> list[str]:
    """Return schema, budget, and stale-reference errors."""
    root = Path(root)
    errors = []
    policies = registry.get("policies", [])
    ids = [policy.get("policy_id") for policy in policies]
    sources = [policy.get("source") for policy in policies]
    artifacts = [policy.get("artifact") for policy in policies]
    if len(ids) != len(set(ids)):
        errors.append("duplicate policy_id")
    if len(sources) != len(set(sources)):
        errors.append("duplicate source")
    if len(artifacts) != len(set(artifacts)):
        errors.append("duplicate artifact")
    for policy in policies:
        missing = REQUIRED_FIELDS - policy.keys()
        if missing:
            errors.append(f"{policy.get('policy_id', '?')}: missing fields {sorted(missing)}")
            continue
        try:
            source, artifact = resolve_policy_paths(root, policy)
        except ValueError as error:
            errors.append(f"{policy['policy_id']}: {error}")
            continue
        if not source.is_file():
            errors.append(f"{policy['policy_id']}: stale source {policy['source']}")
            continue
        if not artifact.is_file():
            errors.append(f"{policy['policy_id']}: stale artifact {policy['artifact']}")
        proxy = token_proxy(source.read_text(encoding="utf-8"))
        if proxy > policy["budget_tokens"]:
            errors.append(f"{policy['policy_id']}: budget {proxy}>{policy['budget_tokens']}")
    return errors


def find_duplicate_paragraphs(texts: Mapping[str, str]) -> list[dict]:
    """Find exact normalized prose paragraphs repeated across canonical files."""
    owners: dict[str, list[str]] = {}
    for name, text in texts.items():
        for paragraph in re.split(r"\n\s*\n", text):
            normalized = " ".join(paragraph.split())
            if len(normalized) >= 80:
                owners.setdefault(normalized, []).append(name)
    return [
        {"paragraph": paragraph, "files": sorted(set(files))}
        for paragraph, files in owners.items()
        if len(set(files)) > 1
    ]


def _load_cases(root: Path, name: str) -> list[dict]:
    return json.loads((root / "tests" / name).read_text(encoding="utf-8"))


def _routing_metrics(root: Path) -> dict:
    gold = _load_cases(root, "router_gold_cases.json")
    negative = _load_cases(root, "router_negative_cases.json")
    tp = fp = fn = risk_hits = 0
    critical_hits = critical_total = 0
    research_review_hits = research_review_total = 0
    for case in gold:
        result = route_task(case["text"], case["paths"], root=root)
        expected = set(case["expected_policies"])
        predicted = set(result["loaded_policy_ids"])
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        risk_hits += result["risk"] == case["expected_risk"]
        if case["expected_risk"] == "R2":
            critical_total += 1
            critical_hits += result["risk"] == "R2"
        for policy_id in expected & {"P03"}:
            critical_total += 1
            critical_hits += policy_id in predicted
        for policy_id in expected & {"P02", "P04"}:
            research_review_total += 1
            research_review_hits += policy_id in predicted
    heavy = {"P01", "P03", "P04", "P05", "P06"}
    false_heavy = sum(
        bool(set(route_task(case["text"], case["paths"], root=root)["loaded_policy_ids"]) & heavy)
        for case in negative
    )
    return {
        "policy_recall": tp / (tp + fn) if tp + fn else 1.0,
        "policy_precision": tp / (tp + fp) if tp + fp else 1.0,
        "risk_accuracy": risk_hits / len(gold),
        "risk_memory_recall": critical_hits / critical_total,
        "research_review_recall": research_review_hits / research_review_total,
        "heavy_false_trigger_rate": false_heavy / len(negative),
        "gold_cases": len(gold),
        "negative_cases": len(negative),
    }


def audit(root: Path | str = DEFAULT_ROOT) -> dict:
    """Return the complete policy-v3 acceptance report."""
    root = Path(root)
    registry = load_registry(root)
    registry_errors = validate_registry(root, registry)
    routing = _routing_metrics(root)
    if registry_errors:
        return {
            "passed": False,
            "budget": {},
            "routing": routing,
            "integrity": {
                "registry_errors": registry_errors,
                "duplicate_paragraphs": 0,
                "stale_references": sum("stale " in error for error in registry_errors),
                "generated_drift": 0,
                "concrete_model_id_hits": [],
            },
        }
    outputs = expected_outputs(root)
    sources = {
        policy["source"]: (root / policy["source"]).read_text(encoding="utf-8")
        for policy in registry["policies"]
        if (root / policy["source"]).is_file()
    }
    duplicates = find_duplicate_paragraphs(sources)
    model_hits = sorted({match.group(0) for text in sources.values() for match in MODEL_ID_PATTERN.finditer(text)})
    l0 = next(policy for policy in registry["policies"] if policy["policy_id"] == "P00")
    budget = {
        "l0_token_proxy": token_proxy(outputs[Path(l0["artifact"])]),
        "max_fragment_token_proxy": max(token_proxy(text) for text in sources.values()),
        "fragment_token_proxies": {name: token_proxy(text) for name, text in sorted(sources.items())},
    }
    integrity = {
        "registry_errors": registry_errors,
        "duplicate_paragraphs": len(duplicates),
        "stale_references": sum("stale " in error for error in registry_errors),
        "generated_drift": len(detect_drift(root, outputs)),
        "concrete_model_id_hits": model_hits,
    }
    limits = registry["token_proxy"]
    passed = (
        budget["l0_token_proxy"] <= limits["l0_max"]
        and budget["max_fragment_token_proxy"] <= limits["fragment_max"]
        and routing["policy_recall"] >= 0.98
        and routing["policy_precision"] >= 0.98
        and routing["risk_memory_recall"] >= 0.98
        and routing["research_review_recall"] >= 0.95
        and routing["heavy_false_trigger_rate"] < 0.10
        and not registry_errors
        and not duplicates
        and not model_hits
        and integrity["generated_drift"] == 0
    )
    return {"passed": passed, "budget": budget, "routing": routing, "integrity": integrity}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit(args.root)
    print(json.dumps(report, indent=None if args.json else 2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
