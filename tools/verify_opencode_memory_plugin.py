"""Verify the local OpenCode memory plugin's static and runtime contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    """Raised when the pinned OpenCode plugin contract cannot be verified."""


def _version(value: str) -> tuple[int, int, int]:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", value)
    if not match:
        raise ContractError("OpenCode version output has no semantic version")
    return tuple(int(part) for part in match.groups())


def _load_contract(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"invalid OpenCode memory contract: {error}") from error
    required = {"schema_version", "minimum_opencode_version", "required_hooks", "required_events", "forbidden_capture"}
    if not isinstance(value, dict) or required - value.keys():
        raise ContractError("OpenCode memory contract is incomplete")
    if value["schema_version"] != 1:
        raise ContractError("unsupported OpenCode memory contract schema")
    return value


def verify_source(plugin: Path, contract: dict) -> None:
    try:
        text = plugin.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ContractError(f"cannot read local memory plugin: {error}") from error
    for hook in contract["required_hooks"]:
        if f'"{hook}"' not in text:
            raise ContractError(f"local memory plugin is missing required hook: {hook}")
    for event in contract["required_events"]:
        if f'"{event}"' not in text:
            raise ContractError(f"local memory plugin is missing required event: {event}")
    if '"tool.execute.after"' in text:
        raise ContractError("local memory plugin must not capture tool output")
    for forbidden in contract["forbidden_capture"]:
        if forbidden in {"raw_prompt", "tool_output", "source_code"} and forbidden in text:
            raise ContractError(f"local memory plugin contains forbidden capture marker: {forbidden}")


def verify_runtime(binary: str, minimum: str) -> tuple[int, int, int]:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ContractError(f"cannot execute OpenCode compatibility probe: {error}") from error
    if result.returncode != 0:
        raise ContractError("OpenCode compatibility probe failed")
    actual, required = _version(result.stdout + result.stderr), _version(minimum)
    if actual < required:
        raise ContractError(
            f"OpenCode {minimum} or newer is required for local memory hooks"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin",
        type=Path,
        default=ROOT / "opencode" / "agent-workflow-memory.ts",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "opencode" / "local-memory-contract.json",
    )
    parser.add_argument("--opencode-bin")
    parser.add_argument("--require-runtime", action="store_true")
    args = parser.parse_args()
    try:
        contract = _load_contract(args.contract)
        verify_source(args.plugin, contract)
        output = {"static_contract": "verified"}
        if args.opencode_bin:
            output["opencode_version"] = ".".join(
                str(part)
                for part in verify_runtime(
                    args.opencode_bin, contract["minimum_opencode_version"]
                )
            )
        elif args.require_runtime:
            raise ContractError("--require-runtime needs --opencode-bin")
        print(json.dumps(output, sort_keys=True))
    except ContractError as error:
        print(f"OpenCode local-memory probe failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
