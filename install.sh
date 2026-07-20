#!/usr/bin/env bash
# Install the agent-workflow-skills bundle (6 on-demand skills + 1 forced always-on spine rule)
# into a tool's config dir. Idempotent: re-running does not duplicate content.
#
# Usage:
#   ./install.sh [--tool cursor|opencode|claude|all] [--project <path>]
# Default tool is cursor.
set -euo pipefail

TOOL="cursor"
PROJECT=""
OPENCODE_CONFIG_DIR=""
OPENCODE_MODEL_CONFIG=""
MIGRATE_OPENCODE_MODEL_CONFIG=0
PROFILE=""
PROFILE_SET=0
GENERIC_BUILD_MODEL=""
GENERIC_REASON_MODEL=""
GENERIC_REVIEW_MODEL=""
CURSOR_BUILD_MODEL="${AGENT_WORKFLOW_CURSOR_BUILD_MODEL:-}"
CURSOR_REASON_MODEL="${AGENT_WORKFLOW_CURSOR_REASON_MODEL:-}"
CURSOR_REVIEW_MODEL="${AGENT_WORKFLOW_CURSOR_REVIEW_MODEL:-}"
OPENCODE_BUILD_MODEL="${AGENT_WORKFLOW_OPENCODE_BUILD_MODEL:-}"
OPENCODE_REASON_MODEL="${AGENT_WORKFLOW_OPENCODE_REASON_MODEL:-}"
OPENCODE_REVIEW_MODEL="${AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --tool) TOOL="${2:-}"; shift 2 ;;
    --tool=*) TOOL="${1#*=}"; shift ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --project=*) PROJECT="${1#*=}"; shift ;;
    --opencode-config-dir) OPENCODE_CONFIG_DIR="${2:-}"; shift 2 ;;
    --opencode-config-dir=*) OPENCODE_CONFIG_DIR="${1#*=}"; shift ;;
    --opencode-model-config) OPENCODE_MODEL_CONFIG="${2:-}"; shift 2 ;;
    --opencode-model-config=*) OPENCODE_MODEL_CONFIG="${1#*=}"; shift ;;
    --migrate-opencode-model-config) MIGRATE_OPENCODE_MODEL_CONFIG=1; shift ;;
    --profile) PROFILE="${2:-}"; PROFILE_SET=1; shift 2 ;;
    --profile=*) PROFILE="${1#*=}"; PROFILE_SET=1; shift ;;
    --build-model) GENERIC_BUILD_MODEL="${2:-}"; shift 2 ;;
    --build-model=*) GENERIC_BUILD_MODEL="${1#*=}"; shift ;;
    --reason-model) GENERIC_REASON_MODEL="${2:-}"; shift 2 ;;
    --reason-model=*) GENERIC_REASON_MODEL="${1#*=}"; shift ;;
    --review-model) GENERIC_REVIEW_MODEL="${2:-}"; shift 2 ;;
    --review-model=*) GENERIC_REVIEW_MODEL="${1#*=}"; shift ;;
    --cursor-build-model) CURSOR_BUILD_MODEL="${2:-}"; shift 2 ;;
    --cursor-build-model=*) CURSOR_BUILD_MODEL="${1#*=}"; shift ;;
    --cursor-reason-model) CURSOR_REASON_MODEL="${2:-}"; shift 2 ;;
    --cursor-reason-model=*) CURSOR_REASON_MODEL="${1#*=}"; shift ;;
    --cursor-review-model) CURSOR_REVIEW_MODEL="${2:-}"; shift 2 ;;
    --cursor-review-model=*) CURSOR_REVIEW_MODEL="${1#*=}"; shift ;;
    --opencode-build-model) OPENCODE_BUILD_MODEL="${2:-}"; shift 2 ;;
    --opencode-build-model=*) OPENCODE_BUILD_MODEL="${1#*=}"; shift ;;
    --opencode-reason-model) OPENCODE_REASON_MODEL="${2:-}"; shift 2 ;;
    --opencode-reason-model=*) OPENCODE_REASON_MODEL="${1#*=}"; shift ;;
    --opencode-review-model) OPENCODE_REVIEW_MODEL="${2:-}"; shift 2 ;;
    --opencode-review-model=*) OPENCODE_REVIEW_MODEL="${1#*=}"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ "$TOOL" = all ] && { [ -n "$GENERIC_BUILD_MODEL" ] || [ -n "$GENERIC_REASON_MODEL" ] || [ -n "$GENERIC_REVIEW_MODEL" ]; }; then
  echo "generic model options are ambiguous for --tool all; use platform-specific options" >&2
  exit 1
fi
if [ "$TOOL" = cursor ]; then
  CURSOR_BUILD_MODEL="${CURSOR_BUILD_MODEL:-$GENERIC_BUILD_MODEL}"
  CURSOR_REASON_MODEL="${CURSOR_REASON_MODEL:-$GENERIC_REASON_MODEL}"
  CURSOR_REVIEW_MODEL="${CURSOR_REVIEW_MODEL:-$GENERIC_REVIEW_MODEL}"
elif [ "$TOOL" = opencode ]; then
  OPENCODE_BUILD_MODEL="${OPENCODE_BUILD_MODEL:-$GENERIC_BUILD_MODEL}"
  OPENCODE_REASON_MODEL="${OPENCODE_REASON_MODEL:-$GENERIC_REASON_MODEL}"
  OPENCODE_REVIEW_MODEL="${OPENCODE_REVIEW_MODEL:-$GENERIC_REVIEW_MODEL}"
fi

if [ "$PROFILE_SET" = 1 ] && [ -z "$PROFILE" ]; then
  echo "--profile requires lean or balanced" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BEGIN_MARKER='<!-- BEGIN agent-workflow-skills spine -->'
END_MARKER='<!-- END agent-workflow-skills spine -->'
SUMMARY=()
SKILL_MARKER='.agent-workflow-skills-owned'
OPENCODE_BASE="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
OPENCODE_STAGE=""; CURSOR_STAGE=""; CLAUDE_STAGE=""
cleanup() {
  [ -z "$OPENCODE_STAGE" ] || rm -rf "$OPENCODE_STAGE"
  [ -z "$CURSOR_STAGE" ] || rm -rf "$CURSOR_STAGE"
  [ -z "$CLAUDE_STAGE" ] || rm -rf "$CLAUDE_STAGE"
}
trap cleanup EXIT

resolve_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info.major != 3)'; then
      printf '%s\n' "$candidate"; return 0
    fi
  done
  echo "A runnable Python 3 interpreter is required to validate an existing OpenCode JSON/JSONC config safely." >&2; return 1
}

new_install_stage() {
  binding="$1"; platform="$2"; profile="$3"; build="$4"; reason="$5"; review="$6"; stage="$(mktemp -d)"
  python_cmd="$(resolve_python)"
  if ! "$python_cmd" "$REPO_ROOT/tools/prepare_install.py" "$stage" "$binding" \
    "$platform" "$profile" "${build:--}" "${reason:--}" "${review:--}" >/dev/null; then
    rm -rf "$stage"; return 1
  fi
  printf '%s\n' "$stage"
}

profile_for() {
  if [ -n "$PROFILE" ]; then printf '%s\n' "$PROFILE"
  elif [ "$1" = cursor ]; then printf 'lean\n'
  else printf 'balanced\n'; fi
}

verify_policy_ownership() {
  state="$1"; adapter="$2"; skills="$3"; spine="$4"
  [ ! -f "$state" ] && return 0
  python_cmd="$(resolve_python)"
  args=(--state "$state" --adapter "$adapter" --skills "$skills")
  [ "$spine" = 1 ] && args+=(--spine)
  "$python_cmd" "$REPO_ROOT/tools/verify_install_state.py" "${args[@]}" ||
    { echo "Generated policy drift detected. Nothing was installed." >&2; return 1; }
}

assert_spine_markers() {
  file="$1"; [ -f "$file" ] || return 0
  begin_count="$(grep -Fxc "$BEGIN_MARKER" "$file" || true)"
  end_count="$(grep -Fxc "$END_MARKER" "$file" || true)"
  if [ "$begin_count" = 0 ] && [ "$end_count" = 0 ]; then return 0; fi
  begin_line="$(grep -Fnx "$BEGIN_MARKER" "$file" | cut -d: -f1)"
  end_line="$(grep -Fnx "$END_MARKER" "$file" | cut -d: -f1)"
  if [ "$begin_count" != 1 ] || [ "$end_count" != 1 ] || [ "$begin_line" -ge "$end_line" ]; then
    echo "Corrupted agent-workflow-skills spine markers in $file. Nothing was installed." >&2; return 1
  fi
}

preflight_opencode() {
  base="$OPENCODE_BASE"
  state="$base/agent-workflow-skills/install-state.json"
  binding="$base/agent-workflow-skills/model-routing.jsonc"
  if [ -f "$binding" ] && [ ! -f "$state" ]; then echo "Model binding exists without bundle ownership: $binding" >&2; return 1; fi
  preflight_skills "$base/skills"
}

preflight_skills() {
  dest="$1"
  for d in "$REPO_ROOT"/policy-v3/generated/skills/*/; do
    target="$dest/$(basename "$d")"
    if [ -d "$target" ] && [ ! -f "$target/$SKILL_MARKER" ]; then
      echo "Skill already exists and is not bundle-owned: $target. Nothing was installed." >&2; return 1
    fi
  done
}

copy_skills() {
  dest="$1"; source="${2:-$REPO_ROOT/skills}"
  mkdir -p "$dest"
  for d in "$source"/*/; do
    name="$(basename "$d")"
    rm -rf "$dest/$name"
    cp -R "$d" "$dest/$name"
    printf 'agent-workflow-skills\n' > "$dest/$name/$SKILL_MARKER"
  done
}

spine_body() {
  # Print an adapter with its optional Cursor frontmatter stripped.
  awk '
    NR==1 && $0=="---" { fm=1; next }
    NR==1 { fm=2 }
    fm==1 && $0=="---" { fm=2; next }
    fm==2 { print }
  ' "$1" | sed '/./,$!d'
}

set_spine_block() {
  file="$1"
  mkdir -p "$(dirname "$file")"
  tmp="$(mktemp "${file}.tmp.XXXXXX")"
  if [ -f "$file" ]; then
    assert_spine_markers "$file"
    if grep -Fqx "$BEGIN_MARKER" "$file"; then
      sed -e "\|^${BEGIN_MARKER}$|,\|^${END_MARKER}$|d" "$file" > "$tmp"
    else
      cat "$file" > "$tmp"
    fi
  fi
  {
    if [ -s "$tmp" ]; then printf '\n'; fi
    printf '%s\n' "$BEGIN_MARKER"
    spine_body "$2"
    printf '%s\n' "$END_MARKER"
  } >> "$tmp"
  mv -f "$tmp" "$file"
}

preflight_opencode_model_migration() {
  binding="$1"; python_cmd="$(resolve_python)"
  migration=(--config-dir "$OPENCODE_BASE" --binding "$binding" \
    --audit "$OPENCODE_BASE/agent-workflow-skills/opencode-model-migration.json" \
    --stage "$OPENCODE_STAGE" --check)
  [ -z "$OPENCODE_MODEL_CONFIG" ] || migration+=(--opencode-model-config "$OPENCODE_MODEL_CONFIG")
  "$python_cmd" "$REPO_ROOT/tools/migrate_opencode_models.py" "${migration[@]}" ||
    { echo "OpenCode model config migration preflight failed. Nothing was installed." >&2; return 1; }
}

install_cursor() {
  skills_dir="$HOME/.cursor/skills"
  copy_skills "$skills_dir" "$CURSOR_STAGE/skills"
  SUMMARY+=("cursor: skills -> $skills_dir")
  rules_dir="$PROJECT/.cursor/rules"
  mkdir -p "$rules_dir"
  cp -f "$CURSOR_STAGE/workflow-gate.mdc" "$rules_dir/workflow-gate.mdc"
  cp -f "$CURSOR_STAGE/model-routing.mdc" "$rules_dir/model-routing.mdc"
  mkdir -p "$PROJECT/.cursor/agent-workflow-skills"
  cp -f "$CURSOR_STAGE/model-routing.jsonc" "$CURSOR_STAGE/dispatch_resolver.py" \
    "$CURSOR_STAGE/validate_jsonc.py" "$CURSOR_STAGE/install-state.json" "$PROJECT/.cursor/agent-workflow-skills/"
  SUMMARY+=("cursor: forced always-on spine -> $rules_dir/workflow-gate.mdc (alwaysApply)")
  SUMMARY+=("cursor: project model adapter -> $rules_dir/model-routing.mdc")
  SUMMARY+=("cursor: model binding -> $PROJECT/.cursor/agent-workflow-skills/model-routing.jsonc")
}

install_opencode() {
  base="$OPENCODE_BASE"
  python_cmd="$(resolve_python)"
  migration=(--config-dir "$base" --binding "$OPENCODE_STAGE/model-routing.jsonc" \
    --audit "$base/agent-workflow-skills/opencode-model-migration.json" \
    --stage "$OPENCODE_STAGE")
  [ -z "$OPENCODE_MODEL_CONFIG" ] || migration+=(--opencode-model-config "$OPENCODE_MODEL_CONFIG")
  "$python_cmd" "$REPO_ROOT/tools/migrate_opencode_models.py" "${migration[@]}" ||
    { echo "OpenCode installation transaction failed; OpenCode config changes were rolled back." >&2; return 1; }
  SUMMARY+=("opencode: skills -> $base/skills")
  SUMMARY+=("opencode: spine injected -> $base/AGENTS.md (marker block)")
  SUMMARY+=("opencode: model binding -> $base/agent-workflow-skills/model-routing.jsonc")
  SUMMARY+=("opencode: role models -> selected JSON/JSONC config (audited migration)")
}

install_claude() {
  base="$HOME/.claude"
  copy_skills "$base/skills" "$CLAUDE_STAGE/skills"
  SUMMARY+=("claude: skills -> $base/skills")
  set_spine_block "$base/CLAUDE.md" "$CLAUDE_STAGE/workflow-gate.mdc"
  mkdir -p "$base/agent-workflow-skills"
  cp -f "$CLAUDE_STAGE/install-state.json" "$base/agent-workflow-skills/"
  SUMMARY+=("claude: generated v3 spine -> $base/CLAUDE.md (marker block)")
  SUMMARY+=("claude: ownership state -> $base/agent-workflow-skills/install-state.json")
}

if { [ "$TOOL" = cursor ] || [ "$TOOL" = all ]; } && [ -z "$PROJECT" ]; then
  echo "--project is required for Cursor installation so the forced spine is installed automatically. Nothing was installed." >&2
  exit 1
fi
if [ "$TOOL" = opencode ] || [ "$TOOL" = all ]; then
  if [ "$MIGRATE_OPENCODE_MODEL_CONFIG" != 1 ]; then
    echo "OpenCode JSON/JSONC model migration requires --migrate-opencode-model-config. Nothing was installed." >&2
    exit 1
  fi
  preflight_opencode
  assert_spine_markers "$OPENCODE_BASE/AGENTS.md"
  verify_policy_ownership "$OPENCODE_BASE/agent-workflow-skills/install-state.json" "$OPENCODE_BASE/AGENTS.md" "$OPENCODE_BASE/skills" 1
  OPENCODE_STAGE="$(new_install_stage "$OPENCODE_BASE/agent-workflow-skills/model-routing.jsonc" opencode "$(profile_for opencode)" "$OPENCODE_BUILD_MODEL" "$OPENCODE_REASON_MODEL" "$OPENCODE_REVIEW_MODEL")"
  preflight_opencode_model_migration "$OPENCODE_STAGE/model-routing.jsonc"
fi
if [ "$TOOL" = cursor ] || [ "$TOOL" = all ]; then
  state="$PROJECT/.cursor/agent-workflow-skills/install-state.json"
  binding="$PROJECT/.cursor/agent-workflow-skills/model-routing.jsonc"
  if [ -f "$binding" ] && [ ! -f "$state" ]; then echo "Cursor model binding exists without bundle ownership." >&2; exit 1; fi
    preflight_skills "$HOME/.cursor/skills"
  verify_policy_ownership "$state" "$PROJECT/.cursor/rules/workflow-gate.mdc" "$HOME/.cursor/skills" 0
  for rule in workflow-gate.mdc model-routing.mdc; do
    path="$PROJECT/.cursor/rules/$rule"
    if [ -f "$path" ] && ! grep -Fq 'Managed by agent-workflow-skills' "$path"; then
      echo "Cursor rule already exists and is not bundle-owned: $path" >&2; exit 1
    fi
  done
  CURSOR_STAGE="$(new_install_stage "$binding" cursor "$(profile_for cursor)" "$CURSOR_BUILD_MODEL" "$CURSOR_REASON_MODEL" "$CURSOR_REVIEW_MODEL")"
fi
if [ "$TOOL" = claude ] || [ "$TOOL" = all ]; then
  CLAUDE_BASE="$HOME/.claude"
  assert_spine_markers "$CLAUDE_BASE/CLAUDE.md"
  preflight_skills "$CLAUDE_BASE/skills"
  verify_policy_ownership "$CLAUDE_BASE/agent-workflow-skills/install-state.json" "$CLAUDE_BASE/CLAUDE.md" "$CLAUDE_BASE/skills" 1
  CLAUDE_STAGE="$(new_install_stage "$CLAUDE_BASE/agent-workflow-skills/model-routing.jsonc" claude "$(profile_for claude)" "" "" "")"
fi

case "$TOOL" in
  cursor)   install_cursor ;;
  opencode) install_opencode ;;
  claude)   install_claude ;;
  all)      install_cursor; install_opencode; install_claude ;;
  *) echo "invalid --tool: $TOOL (expected cursor|opencode|claude|all)" >&2; exit 1 ;;
esac

echo ""
echo "=== agent-workflow-skills install summary (tool=$TOOL) ==="
for line in "${SUMMARY[@]}"; do echo "  - $line"; done
if [ "$TOOL" = opencode ] || [ "$TOOL" = all ]; then echo "Restart OpenCode to load the installed files."; fi
echo "Done."
