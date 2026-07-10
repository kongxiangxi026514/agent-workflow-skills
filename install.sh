#!/usr/bin/env bash
# Install the agent-workflow-skills bundle (5 on-demand skills + 1 forced always-on spine rule)
# into a tool's config dir. Idempotent: re-running does not duplicate content.
#
# Usage:
#   ./install.sh [--tool cursor|opencode|claude|all] [--project <path>]
# Default tool is cursor.
set -euo pipefail

TOOL="cursor"
PROJECT=""
OPENCODE_BUILD_MODEL="${AGENT_WORKFLOW_OPENCODE_BUILD_MODEL:-}"
OPENCODE_REASON_MODEL="${AGENT_WORKFLOW_OPENCODE_REASON_MODEL:-}"
OPENCODE_REVIEW_MODEL="${AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --tool) TOOL="${2:-}"; shift 2 ;;
    --tool=*) TOOL="${1#*=}"; shift ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --project=*) PROJECT="${1#*=}"; shift ;;
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

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BEGIN_MARKER='<!-- BEGIN agent-workflow-skills spine -->'
END_MARKER='<!-- END agent-workflow-skills spine -->'
SUMMARY=()
OPENCODE_CONFIG=""
AGENT_MARKER='<!-- Managed by agent-workflow-skills. -->'

resolve_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info.major != 3)'; then
      printf '%s\n' "$candidate"; return 0
    fi
  done
  echo "A runnable Python 3 interpreter is required to validate an existing OpenCode JSON/JSONC config safely." >&2; return 1
}

validate_opencode_model() {
  role="$1"; value="$2"; env_name="$3"
  if [ -z "$value" ] || [[ "$value" =~ [[:cntrl:]] ]] ||
    ! [[ "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$ ]]; then
    echo "OpenCode $role model is required as a safe provider/model ID. Run 'opencode models' and pass an exact available ID with --opencode-${role}-model or $env_name." >&2
    return 1
  fi
  IFS=/ read -ra parts <<< "$value"
  for part in "${parts[@]}"; do
    case "$(printf '%s' "$part" | tr '[:upper:]' '[:lower:]')" in
      provider|model|placeholder|example|change-me|your-provider|your-model)
        echo "OpenCode $role model must not use a placeholder token. Run 'opencode models' for an exact available ID." >&2; return 1 ;;
    esac
  done
}

validate_opencode_models() {
  validate_opencode_model build "$OPENCODE_BUILD_MODEL" AGENT_WORKFLOW_OPENCODE_BUILD_MODEL || return 1
  validate_opencode_model reason "$OPENCODE_REASON_MODEL" AGENT_WORKFLOW_OPENCODE_REASON_MODEL || return 1
  validate_opencode_model review "$OPENCODE_REVIEW_MODEL" AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL || return 1
  if [ "$OPENCODE_REVIEW_MODEL" = "$OPENCODE_BUILD_MODEL" ] || [ "$OPENCODE_REVIEW_MODEL" = "$OPENCODE_REASON_MODEL" ]; then
    echo "OpenCode review model must differ from build and reason models. Select exact IDs from 'opencode models' before installation." >&2; return 1
  fi
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
  base="$HOME/.config/opencode"
  json="$base/opencode.json"
  jsonc="$base/opencode.jsonc"
  if [ -f "$json" ] && [ -f "$jsonc" ]; then
    echo "Both $json and $jsonc exist. OpenCode config is ambiguous; remove or rename one. Nothing was installed." >&2
    return 1
  fi
  if [ -f "$jsonc" ]; then OPENCODE_CONFIG="$jsonc"
  elif [ -f "$json" ]; then OPENCODE_CONFIG="$json"
  fi
  if [ -n "$OPENCODE_CONFIG" ]; then
    python_cmd="$(resolve_python)"
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$python_cmd" "$REPO_ROOT/tools/validate_jsonc.py" "$OPENCODE_CONFIG" ||
      { echo "Invalid OpenCode config: $OPENCODE_CONFIG. Nothing was installed." >&2; return 1; }
  fi
  for agent in "$base/agents/build.md" "$base/agents/reason.md" "$base/agents/review.md"; do
    if [ -f "$agent" ] && ! grep -Fq "$AGENT_MARKER" "$agent"; then
      echo "OpenCode agent already exists and is not bundle-owned: $agent. Nothing was installed." >&2
      return 1
    fi
  done
}

copy_skills() {
  dest="$1"
  mkdir -p "$dest"
  for d in "$REPO_ROOT"/skills/*/; do
    name="$(basename "$d")"
    rm -rf "$dest/$name"
    cp -R "$d" "$dest/$name"
  done
}

spine_body() {
  # Print rules/workflow-gate.mdc with the leading --- ... --- frontmatter stripped.
  awk '
    NR==1 && $0=="---" { fm=1; next }
    fm==1 && $0=="---" { fm=2; next }
    fm==2 { print }
  ' "$REPO_ROOT/rules/workflow-gate.mdc" | sed '/./,$!d'
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
    spine_body
    printf '%s\n' "$END_MARKER"
  } >> "$tmp"
  mv -f "$tmp" "$file"
}

render_opencode_agent() {
  name="$1"; model="$2"; dest="$3"; source="$REPO_ROOT/opencode/agents/$name.md"
  if ! grep -Fq '__OPENCODE_MODEL__' "$source"; then
    echo "OpenCode agent template is missing its model placeholder: $name.md" >&2; return 1
  fi
  sed "s|__OPENCODE_MODEL__|$model|g" "$source" > "$dest"
}

install_cursor() {
  skills_dir="$HOME/.cursor/skills"
  copy_skills "$skills_dir"
  SUMMARY+=("cursor: skills -> $skills_dir")
  rules_dir="$PROJECT/.cursor/rules"
  mkdir -p "$rules_dir"
  cp -f "$REPO_ROOT/rules/workflow-gate.mdc" "$rules_dir/workflow-gate.mdc"
  SUMMARY+=("cursor: forced always-on spine -> $rules_dir/workflow-gate.mdc (alwaysApply)")
}

install_opencode() {
  base="$HOME/.config/opencode"
  copy_skills "$base/skills"
  SUMMARY+=("opencode: skills -> $base/skills")
  set_spine_block "$base/AGENTS.md"
  SUMMARY+=("opencode: spine injected -> $base/AGENTS.md (marker block)")
  mkdir -p "$base/agents"
  render_opencode_agent build "$OPENCODE_BUILD_MODEL" "$base/agents/build.md"
  render_opencode_agent reason "$OPENCODE_REASON_MODEL" "$base/agents/reason.md"
  render_opencode_agent review "$OPENCODE_REVIEW_MODEL" "$base/agents/review.md"
  SUMMARY+=("opencode: native agents -> $base/agents/{build,reason,review}.md")
  config_label="${OPENCODE_CONFIG:-none present; none created}"
  SUMMARY+=("opencode: main config untouched -> $config_label")
}

install_claude() {
  base="$HOME/.claude"
  copy_skills "$base/skills"
  SUMMARY+=("claude: skills -> $base/skills")
  set_spine_block "$base/CLAUDE.md"
  SUMMARY+=("claude: spine injected -> $base/CLAUDE.md (marker block)")
}

if { [ "$TOOL" = cursor ] || [ "$TOOL" = all ]; } && [ -z "$PROJECT" ]; then
  echo "--project is required for Cursor installation so the forced spine is installed automatically. Nothing was installed." >&2
  exit 1
fi
if [ "$TOOL" = opencode ] || [ "$TOOL" = all ]; then
  validate_opencode_models
  preflight_opencode
  assert_spine_markers "$HOME/.config/opencode/AGENTS.md"
fi
if [ "$TOOL" = claude ] || [ "$TOOL" = all ]; then assert_spine_markers "$HOME/.claude/CLAUDE.md"; fi

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
