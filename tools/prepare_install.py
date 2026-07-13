"""Stage validated, portable installer artifacts before target mutation."""
import json, re, shutil, sys
from pathlib import Path

from validate_jsonc import normalize_jsonc

ROOT = Path(__file__).resolve().parents[1]
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$")
RESERVED = {"provider", "model", "placeholder", "example", "change-me", "your-provider", "your-model"}
FORBIDDEN = ("gpt-5.6-", "glm-5.2-max", "huawei/")
OWNER = ".agent-workflow-skills-owned"


def _model(role, value, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not MODEL_RE.fullmatch(value):
        raise ValueError(f"{role} model binding must be an exact provider/model ID")
    if any(part.lower() in RESERVED for part in value.split("/")):
        raise ValueError(f"{role} model binding contains a placeholder")
    return value


def _binding(path, supplied):
    supplied = tuple("" if value == "-" else value for value in supplied)
    if path.exists():
        data = json.loads(normalize_jsonc(path.read_bytes().decode("utf-8-sig")))
    else:
        data = json.loads(normalize_jsonc((ROOT / "config/model-routing.jsonc").read_text(encoding="utf-8")))
        data.update({"build": supplied[0] or None, "reason": supplied[1] or None, "review": supplied[2] or None})
    if not isinstance(data, dict):
        raise ValueError("model binding root must be an object")
    build = _model("build", data.get("build"))
    reason = _model("reason", data.get("reason"), nullable=True)
    review = _model("review", data.get("review"))
    effective_reason = reason or build
    if review in (build, effective_reason):
        raise ValueError("review model binding must differ from build and effective reason")
    return data, (build, effective_reason, review)


def _render(source, target, replacements):
    text = source.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    if "__" in text:
        raise ValueError(f"unresolved placeholder in {source}")
    target.write_text(text, encoding="utf-8", newline="\n")


def _stage(stage, binding_path, supplied):
    data, models = _binding(binding_path, supplied)
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "skills", stage / "skills")
    for skill in (stage / "skills").iterdir():
        if skill.is_dir():
            (skill / OWNER).write_text("agent-workflow-skills\n", encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "rules/workflow-gate.mdc", stage / "workflow-gate.mdc")
    (stage / "agents").mkdir()
    for name, model in zip(("build", "reason", "review"), models):
        _render(ROOT / f"opencode/agents/{name}.md", stage / f"agents/{name}.md", {"__OPENCODE_MODEL__": model})
    _render(
        ROOT / "cursor/model-routing.mdc",
        stage / "model-routing.mdc",
        {"__BUILD_MODEL__": models[0], "__REASON_MODEL__": models[1], "__REVIEW_MODEL__": models[2]},
    )
    binding_text = "// Edit role IDs, then rerun the installer.\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    (stage / "model-routing.jsonc").write_text(binding_text, encoding="utf-8", newline="\n")
    state = {"bundle": "agent-workflow-skills", "version": 1}
    (stage / "install-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    portable = [stage / "workflow-gate.mdc", *(stage / "skills").glob("*/SKILL.md")]
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in portable)
    if any(token in text for token in FORBIDDEN):
        raise ValueError("portable runtime policy contains a concrete machine model identifier")
    if "edit: deny" not in (stage / "agents/review.md").read_text(encoding="utf-8"):
        raise ValueError("review agent must deny edits")
    return models


def main():
    try:
        if len(sys.argv) != 6:
            raise ValueError("usage: prepare_install.py STAGE BINDING BUILD REASON REVIEW")
        models = _stage(Path(sys.argv[1]), Path(sys.argv[2]), tuple(sys.argv[3:6]))
        print("\n".join(models))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(f"Invalid model binding or bundle artifact: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
