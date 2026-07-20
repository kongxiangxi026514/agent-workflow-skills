"""Stage validated, portable installer artifacts before target mutation."""
import hashlib, json, re, shutil, sys
from pathlib import Path

from validate_jsonc import normalize_jsonc
from render_policy import detect_drift, expected_outputs, profile_names

ROOT = Path(__file__).resolve().parents[1]
CURSOR_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OPENCODE_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$")
RESERVED = {"provider", "model", "placeholder", "example", "change-me", "your-provider", "your-model"}
FORBIDDEN = ("model: ",)
OWNER = ".agent-workflow-skills-owned"


def _model(platform, role, value, nullable=False):
    if value is None and nullable:
        return None
    pattern = CURSOR_MODEL_RE if platform == "cursor" else OPENCODE_MODEL_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        expected = "native model slug" if platform == "cursor" else "provider/model ID"
        raise ValueError(f"{role} model binding must be an exact {expected}")
    if any(part.lower() in RESERVED for part in value.split("/")):
        raise ValueError(f"{role} model binding contains a placeholder")
    return value


def _binding(path, supplied, platform):
    supplied = tuple("" if value == "-" else value for value in supplied)
    if path.exists():
        data = json.loads(normalize_jsonc(path.read_bytes().decode("utf-8-sig")))
    else:
        data = json.loads(normalize_jsonc((ROOT / "config/model-routing.jsonc").read_text(encoding="utf-8")))
        data.update({"build": supplied[0] or None, "reason": supplied[1] or None, "review": supplied[2] or None})
    if not isinstance(data, dict):
        raise ValueError("model binding root must be an object")
    build = _model(platform, "build", data.get("build"))
    reason = _model(platform, "reason", data.get("reason"), nullable=True)
    review = _model(platform, "review", data.get("review"))
    effective_reason = reason or build
    if review in (build, effective_reason):
        raise ValueError("review model binding must differ from build and effective reason")
    return data, (build, effective_reason, review)


def _hash(path):
    """Return the content digest recorded in the owned-artifact manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adapter_source(platform, profile):
    if platform not in ("claude", "cursor", "opencode"):
        raise ValueError(f"unsupported install platform: {platform}")
    if profile not in profile_names(ROOT):
        raise ValueError(f"unsupported install profile: {profile}")
    name = {
        "claude": "CLAUDE.md",
        "cursor": "workflow-gate.mdc",
        "opencode": "AGENTS.md",
    }[platform]
    return ROOT / "policy-v3" / "generated" / "adapters" / platform / profile / name


def _stage(stage, binding_path, platform, profile, supplied):
    if platform == "claude":
        data, models = None, ()
    else:
        data, models = _binding(binding_path, supplied, platform)
    drift = detect_drift(ROOT, expected_outputs(ROOT))
    if drift:
        raise ValueError(f"generated policy artifacts drifted: {', '.join(drift)}")
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "policy-v3" / "generated" / "skills", stage / "skills")
    for skill in (stage / "skills").iterdir():
        if skill.is_dir():
            (skill / OWNER).write_text("agent-workflow-skills\n", encoding="utf-8", newline="\n")
    shutil.copy2(_adapter_source(platform, profile), stage / "workflow-gate.mdc")
    if platform != "claude":
        if platform == "cursor":
            shutil.copy2(ROOT / "cursor/model-routing.mdc", stage / "model-routing.mdc")
        binding_text = "// Edit role IDs, then rerun the installer.\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        (stage / "model-routing.jsonc").write_text(binding_text, encoding="utf-8", newline="\n")
        for name in ("dispatch_resolver.py", "validate_jsonc.py"):
            shutil.copy2(ROOT / "tools" / name, stage / name)
    policy_owned = [stage / "workflow-gate.mdc", *(stage / "skills").glob("*/SKILL.md")]
    owned = [*policy_owned]
    if platform != "claude":
        if platform == "cursor":
            owned.append(stage / "model-routing.mdc")
        owned.extend((
            stage / "model-routing.jsonc",
            stage / "dispatch_resolver.py",
            stage / "validate_jsonc.py",
        ))
    state = {
        "bundle": "agent-workflow-skills",
        "version": 3,
        "platform": platform,
        "profile": profile,
        "owned_sha256": {str(path.relative_to(stage)).replace("\\", "/"): _hash(path) for path in owned},
        "policy_owned_sha256": {
            str(path.relative_to(stage)).replace("\\", "/"): _hash(path) for path in policy_owned
        },
    }
    (stage / "install-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    portable = [stage / "workflow-gate.mdc", *(stage / "skills").glob("*/SKILL.md")]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in portable)
    if any(token in text for token in FORBIDDEN):
        raise ValueError("portable runtime policy contains a concrete machine model identifier")
    return models


def main():
    try:
        if len(sys.argv) != 8:
            raise ValueError("usage: prepare_install.py STAGE BINDING PLATFORM PROFILE BUILD REASON REVIEW")
        models = _stage(
            Path(sys.argv[1]),
            Path(sys.argv[2]),
            sys.argv[3],
            sys.argv[4],
            tuple(sys.argv[5:8]),
        )
        print("\n".join(models))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(f"Invalid model binding or bundle artifact: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
