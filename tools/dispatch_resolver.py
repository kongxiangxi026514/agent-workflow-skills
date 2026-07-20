"""Resolve platform-local roles into fail-loud native dispatch requests and receipts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from validate_jsonc import parse_jsonc


ROLES = ("build", "reason", "review")
PLATFORMS = ("cursor", "opencode")
CURSOR_SDK_MODEL_SOURCES = (
    "cursor-sdk.run.model",
    "cursor-sdk.result.model",
)
CURSOR_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OPENCODE_MODEL_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$"
)
FAMILY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class DispatchResolutionError(ValueError):
    """Raised before dispatch when a binding or evidence contract is invalid."""


def _validate_model(platform: str, role: str, value: object) -> str:
    pattern = CURSOR_MODEL_RE if platform == "cursor" else OPENCODE_MODEL_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        expected = "native model slug" if platform == "cursor" else "provider/model ID"
        raise DispatchResolutionError(f"{platform} {role} must be an exact {expected}")
    return value


def _load_binding(platform: str, binding_path: Path) -> dict:
    if platform not in PLATFORMS:
        raise DispatchResolutionError(f"unsupported dispatch platform: {platform}")
    try:
        data = parse_jsonc(binding_path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise DispatchResolutionError(f"invalid model binding: {error}") from error
    if not isinstance(data, dict):
        raise DispatchResolutionError("model binding root must be an object")
    models = {
        "build": _validate_model(platform, "build", data.get("build")),
        "review": _validate_model(platform, "review", data.get("review")),
    }
    reason = data.get("reason")
    models["reason"] = (
        models["build"]
        if reason is None
        else _validate_model(platform, "reason", reason)
    )
    if models["review"] in (models["build"], models["reason"]):
        raise DispatchResolutionError(
            "review model must differ from build and effective reason"
        )
    raw_families = data.get("families", {})
    if raw_families is None:
        raw_families = {}
    if not isinstance(raw_families, dict):
        raise DispatchResolutionError("families must be an object when present")
    families = {}
    for role in ROLES:
        family = raw_families.get(role)
        if role == "reason" and family is None and reason is None:
            family = raw_families.get("build")
        if family is not None:
            if not isinstance(family, str) or not FAMILY_RE.fullmatch(family):
                raise DispatchResolutionError(f"{role} family label is invalid")
            families[role] = family
    return {"models": models, "families": families}


def resolve_dispatch(
    platform: str,
    role: str,
    binding_path: Path,
    *,
    available_models=None,
    registry_exposed: bool = False,
) -> dict:
    """Return exact native dispatch arguments after binding and registry validation."""
    if role not in ROLES:
        raise DispatchResolutionError(f"unsupported dispatch role: {role}")
    binding = _load_binding(platform, Path(binding_path))
    requested = binding["models"][role]
    if registry_exposed and available_models is None:
        raise DispatchResolutionError(
            "platform model registry was exposed but no registry values were supplied"
        )
    if available_models is not None and requested not in set(available_models):
        raise DispatchResolutionError(
            f"requested model is unavailable; refusing fallback: {requested}"
        )
    if platform == "cursor":
        native_dispatch = {
            "subagent_type": "generalPurpose",
            "model": requested,
        }
        native_model_source = "dispatch-argument"
    else:
        native_dispatch = {"agent": role}
        native_model_source = "agent-json-config"
    return {
        "platform": platform,
        "role": role,
        "requested_model": requested,
        "requested_family": binding["families"].get(role),
        "comparison_families": [
            binding["families"][name]
            for name in ("build", "reason")
            if name in binding["families"]
        ],
        "native_dispatch": native_dispatch,
        "native_model_source": native_model_source,
        "review_write_contract": "read-only" if role == "review" else None,
        "registry_validation": (
            "verified" if available_models is not None else "not-exposed"
        ),
    }


def make_receipt(
    request: dict,
    *,
    actual_model: str | None = None,
    actual_model_source: str | None = None,
) -> dict:
    """Finalize a receipt only from permitted Cursor SDK model telemetry."""
    requested = request["requested_model"]
    role = request["role"]
    if actual_model is None:
        if actual_model_source is not None:
            raise DispatchResolutionError(
                "actual_model_source requires Cursor SDK model telemetry"
            )
    else:
        if request["platform"] != "cursor":
            raise DispatchResolutionError(
                "runtime model evidence is supported only for Cursor SDK telemetry"
            )
        if actual_model_source is None:
            raise DispatchResolutionError(
                "actual_model requires an explicit Cursor SDK telemetry source"
            )
        if actual_model_source not in CURSOR_SDK_MODEL_SOURCES:
            raise DispatchResolutionError(
                f"unsupported telemetry source: {actual_model_source}"
            )
    if actual_model is not None and actual_model != requested:
        raise DispatchResolutionError(
            f"native runtime fallback detected: requested {requested}, got {actual_model}"
        )
    if actual_model is None:
        cross_model = "unverified"
        review_kind = (
            "independent-review-unverified"
            if role == "review"
            else "not-a-review"
        )
    elif role != "review":
        cross_model = False
        review_kind = "not-a-review"
    else:
        observed_family = request.get("requested_family")
        comparison = request.get("comparison_families", [])
        if observed_family is None or len(comparison) < 2:
            cross_model = "unverified"
            review_kind = "independent-review-unverified"
        else:
            cross_model = all(observed_family != family for family in comparison)
            review_kind = (
                "cross-model-review"
                if cross_model
                else "independent-context-review"
            )
    return {
        "role": role,
        "requested_model": requested,
        "actual_model": actual_model,
        "actual_model_source": actual_model_source,
        "cross_model": cross_model,
        "review_kind": review_kind,
        "registry_validation": request["registry_validation"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--available-model", action="append")
    parser.add_argument("--registry-exposed", action="store_true")
    parser.add_argument("--actual-model")
    parser.add_argument(
        "--actual-model-source",
        choices=CURSOR_SDK_MODEL_SOURCES,
        help="Cursor SDK telemetry field that supplied --actual-model",
    )
    args = parser.parse_args()
    try:
        request = resolve_dispatch(
            args.platform,
            args.role,
            args.binding,
            available_models=args.available_model,
            registry_exposed=args.registry_exposed,
        )
        output = {
            "request": request,
            "receipt": make_receipt(
                request,
                actual_model=args.actual_model,
                actual_model_source=args.actual_model_source,
            ),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except DispatchResolutionError as error:
        print(f"Dispatch resolution failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
