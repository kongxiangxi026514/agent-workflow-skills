"""Deterministic policy-v3 routing and bounded task-capsule rendering."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CAPSULE_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")


def token_proxy(text: str) -> int:
    """Return the repository's deterministic character-based token proxy."""
    return math.ceil(len(text) / 4)


def load_registry(root: Path | str = DEFAULT_ROOT) -> dict:
    """Load the canonical policy registry."""
    path = Path(root) / "policy-v3" / "registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_settings(registry: dict, profile: str) -> dict:
    """Validate and return thresholds for one named installation profile."""
    try:
        settings = registry["profiles"][profile]
        escalation = settings["escalation"]
        budget = settings["budget"]
    except KeyError as error:
        raise ValueError(f"unknown or incomplete installer profile: {profile}") from error
    required_escalation = {"ordinary_change_min_paths", "ordinary_path_count"}
    if set(escalation) != required_escalation or set(budget) != {"l0_max", "capsule_max"}:
        raise ValueError(f"invalid installer profile: {profile}")
    return settings


def _matches(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _policy_matches(policy: dict, text: str) -> bool:
    trigger = policy["trigger"]
    positives = trigger.get("any", [])
    if not positives or not _matches(positives, text):
        return False
    return not _matches(trigger.get("none", []), text)


def _path_matches(patterns: Iterable[str], paths: Sequence[str]) -> bool:
    normalized = [path.replace("\\", "/").lower() for path in paths]
    return any(re.search(pattern, path, flags=re.IGNORECASE) for path in normalized for pattern in patterns)


def _risk_max(risks: Iterable[str], order: Sequence[str]) -> str:
    ranks = {risk: index for index, risk in enumerate(order)}
    return max(risks, key=ranks.__getitem__, default=order[0])


def _dependency_closure(selected: set[str], policies_by_id: dict[str, dict]) -> set[str]:
    pending = list(selected)
    while pending:
        policy_id = pending.pop()
        for required in policies_by_id[policy_id]["trigger"].get("requires", []):
            if required not in selected:
                selected.add(required)
                pending.append(required)
    return selected


def _base_risk(text: str, paths: Sequence[str], router: dict, escalation: dict) -> str:
    if _matches(router["strict_override_patterns"], text):
        return "R2"
    high_risk = _matches(router["high_risk_patterns"], text)
    high_risk = high_risk or _path_matches(router["high_risk_path_patterns"], paths)
    if high_risk:
        return "R2"
    lean = len(paths) <= 1 and _matches(router["lean_change_patterns"], text)
    ordinary = len(paths) >= escalation["ordinary_path_count"]
    ordinary = ordinary or (
        len(paths) >= escalation["ordinary_change_min_paths"]
        and _matches(router["change_patterns"], text)
    )
    risk = "R0" if lean or not ordinary else "R1"
    if risk == "R1" and _matches(router["quick_override_patterns"], text):
        return "R0"
    return risk


def route_task(
    text: str,
    paths: Sequence[str] = (),
    *,
    profile: str = "balanced",
    root: Path | str = DEFAULT_ROOT,
) -> dict:
    """Classify a task and return the exact ordered on-demand policy set."""
    registry = load_registry(root)
    settings = _profile_settings(registry, profile)
    policies = registry["policies"]
    policies_by_id = {policy["policy_id"]: policy for policy in policies}
    triggered = {policy["policy_id"] for policy in policies if _policy_matches(policy, text)}
    exclusive = {
        policy_id
        for policy_id in triggered
        if policies_by_id[policy_id]["trigger"].get("exclusive", False)
    }
    if exclusive:
        selected = _dependency_closure(exclusive, policies_by_id)
        risk = _risk_max((policies_by_id[item]["risk"] for item in selected), registry["router"]["risk_order"])
        return {"risk": risk, "loaded_policy_ids": sorted(selected)}

    base_risk = _base_risk(text, paths, registry["router"], settings["escalation"])
    policy_risks = [policies_by_id[item]["risk"] for item in triggered]
    risk = _risk_max([base_risk, *policy_risks], registry["router"]["risk_order"])
    selected = triggered | set(registry["router"]["risk_auto_load"][risk])
    selected = _dependency_closure(selected, policies_by_id)
    selected.discard("P00")
    return {"risk": risk, "loaded_policy_ids": sorted(selected)}


def _format_items(items: Sequence[str]) -> str:
    if not items:
        return "- None."
    return "\n".join(f"- {item}" for item in items)


def build_task_capsule(
    *,
    goal: str,
    non_goals: Sequence[str],
    risk: str,
    allowed_scope: Sequence[str],
    forbidden_scope: Sequence[str],
    acceptance: Sequence[str],
    loaded_policy_ids: Sequence[str],
    artifact_pointers: Sequence[str],
    profile: str = "balanced",
    root: Path | str = DEFAULT_ROOT,
) -> str:
    """Fill the canonical capsule template and enforce its proxy budget."""
    registry = load_registry(root)
    settings = _profile_settings(registry, profile)
    policy = next(item for item in registry["policies"] if item["policy_id"] == "P07")
    template = (Path(root) / policy["source"]).read_text(encoding="utf-8")
    values = {
        "GOAL": goal.strip(),
        "NON_GOALS": _format_items(non_goals),
        "RISK": risk,
        "ALLOWED_SCOPE": _format_items(allowed_scope),
        "FORBIDDEN_SCOPE": _format_items(forbidden_scope),
        "ACCEPTANCE": _format_items(acceptance),
        "LOADED_POLICIES": _format_items(loaded_policy_ids),
        "ARTIFACT_POINTERS": _format_items(artifact_pointers),
    }
    capsule = CAPSULE_PLACEHOLDER.sub(
        lambda match: values.get(match.group(1), match.group(0)),
        template,
    )
    budget = registry["token_proxy"]
    proxy = token_proxy(capsule)
    capsule_max = min(budget["capsule_max"], settings["budget"]["capsule_max"])
    if not budget["capsule_min"] <= proxy <= capsule_max:
        raise ValueError(f"task capsule proxy {proxy} outside {budget['capsule_min']}..{capsule_max}")
    return capsule
