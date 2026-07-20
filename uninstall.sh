#!/usr/bin/env bash
# Uninstall the agent-workflow-skills bundle from a tool's config dir.
# Reverse of install.sh. Idempotent: no error if items are already absent.
#
# Usage:
#   ./uninstall.sh [--tool cursor|opencode|claude|all] [--project <path>] [--remove-global-skills]
# Default tool is cursor.
set -euo pipefail

TOOL="cursor"
PROJECT=""
OPENCODE_CONFIG_DIR=""
REMOVE_GLOBAL_SKILLS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tool) TOOL="${2:-}"; shift 2 ;;
    --tool=*) TOOL="${1#*=}"; shift ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --project=*) PROJECT="${1#*=}"; shift ;;
    --opencode-config-dir) OPENCODE_CONFIG_DIR="${2:-}"; shift 2 ;;
    --opencode-config-dir=*) OPENCODE_CONFIG_DIR="${1#*=}"; shift ;;
    --remove-global-skills) REMOVE_GLOBAL_SKILLS=1; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BEGIN_MARKER='<!-- BEGIN agent-workflow-skills spine -->'
END_MARKER='<!-- END agent-workflow-skills spine -->'
SKILL_MARKER='.agent-workflow-skills-owned'
OPENCODE_BASE="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
SUMMARY=()

resolve_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info.major != 3)'; then
      printf '%s\n' "$candidate"; return 0
    fi
  done
  echo "A runnable Python 3 interpreter is required to verify managed OpenCode role fields." >&2; return 1
}

verify_managed_spine() {
  state="$1"; adapter="$2"; skills="$3"
  [ -f "$adapter" ] || return 0
  has_begin=0; has_end=0
  grep -Fqx "$BEGIN_MARKER" "$adapter" && has_begin=1
  grep -Fqx "$END_MARKER" "$adapter" && has_end=1
  [ "$has_begin" = 0 ] && [ "$has_end" = 0 ] && return 0
  if [ "$has_begin" != 1 ] || [ "$has_end" != 1 ] || [ ! -f "$state" ]; then
    echo "Managed spine marker lacks valid ownership state: $adapter" >&2; return 1
  fi
  python_cmd="$(resolve_python)"
  "$python_cmd" "$REPO_ROOT/tools/verify_install_state.py" \
    --state "$state" --adapter "$adapter" --skills "$skills" --spine ||
    { echo "Managed spine provenance validation failed: $adapter" >&2; return 1; }
}

verify_cursor_ownership() {
  skills="$HOME/.cursor/skills"
  global_candidate=0
  if [ -n "$PROJECT" ]; then
    rules="$PROJECT/.cursor/rules"
    bundle="$PROJECT/.cursor/agent-workflow-skills"
    state="$bundle/install-state.json"
    project_candidate=0
    [ ! -f "$state" ] || project_candidate=1
    [ ! -d "$bundle" ] || [ -z "$(ls -A "$bundle")" ] || project_candidate=1
    [ ! -e "$rules/workflow-gate.mdc" ] || project_candidate=1
    [ ! -e "$rules/model-routing.mdc" ] || project_candidate=1
  else
    project_candidate=0
  fi
  for source in "$REPO_ROOT"/policy-v3/generated/skills/*/; do
    [ ! -e "$skills/$(basename "$source")" ] || global_candidate=1
  done
  python_cmd="$(resolve_python)"
  if [ "$global_candidate" = 1 ]; then
    "$python_cmd" "$REPO_ROOT/tools/verify_cursor_ownership.py" \
      --skills "$skills" --source-skills "$REPO_ROOT/policy-v3/generated/skills" ||
      { echo "Cursor global skill ownership validation failed. Nothing was uninstalled." >&2; return 1; }
  fi
  if [ "$project_candidate" = 1 ]; then
    if [ -z "$PROJECT" ] || [ ! -f "$state" ]; then
      echo "Cursor project artifacts require a valid project install-state.json. Nothing was uninstalled." >&2
      return 1
    fi
    "$python_cmd" "$REPO_ROOT/tools/verify_cursor_ownership.py" \
      --state "$state" --rules "$rules" --skills "$skills" --bundle "$bundle" ||
      { echo "Cursor project ownership validation failed. Nothing was uninstalled." >&2; return 1; }
  fi
}

remove_skills() {
  # Only remove the skill folders that this bundle ships (never a whole skills dir).
  dest="$1"
  [ -d "$dest" ] || return 0
  for d in "$REPO_ROOT"/policy-v3/generated/skills/*/; do
    name="$(basename "$d")"
    if [ -f "$dest/$name/$SKILL_MARKER" ]; then rm -rf "$dest/$name"; fi
  done
}

assert_spine_markers() {
  file="$1"; [ -f "$file" ] || return 0
  begin_count="$(grep -Fxc "$BEGIN_MARKER" "$file" || true)"
  end_count="$(grep -Fxc "$END_MARKER" "$file" || true)"
  if [ "$begin_count" = 0 ] && [ "$end_count" = 0 ]; then return 0; fi
  begin_line="$(grep -Fnx "$BEGIN_MARKER" "$file" | cut -d: -f1)"
  end_line="$(grep -Fnx "$END_MARKER" "$file" | cut -d: -f1)"
  if [ "$begin_count" != 1 ] || [ "$end_count" != 1 ] || [ "$begin_line" -ge "$end_line" ]; then
    echo "Corrupted agent-workflow-skills spine markers in $file. Nothing was uninstalled." >&2; return 1
  fi
}

remove_spine_block() {
  file="$1"
  [ -f "$file" ] || return 0
  assert_spine_markers "$file"
  grep -Fqx "$BEGIN_MARKER" "$file" || return 0
  tmp="$(mktemp "${file}.tmp.XXXXXX")"
  sed -e "\|^${BEGIN_MARKER}$|,\|^${END_MARKER}$|d" "$file" > "$tmp"
  mv -f "$tmp" "$file"
}

uninstall_cursor() {
  skills_dir="$HOME/.cursor/skills"
  state="${PROJECT:+$PROJECT/.cursor/agent-workflow-skills/install-state.json}"
  owned=0; [ -z "$state" ] || [ ! -f "$state" ] || owned=1
  verify_cursor_ownership
  if [ "$REMOVE_GLOBAL_SKILLS" = 1 ]; then
    remove_skills "$skills_dir"
    SUMMARY+=("cursor: removed verified global bundle skills from $skills_dir")
  else
    SUMMARY+=("cursor: preserved shared global skills at $skills_dir")
  fi
  if [ -n "$PROJECT" ]; then
    dest="$PROJECT/.cursor/rules/workflow-gate.mdc"
    for rule in "$dest" "$PROJECT/.cursor/rules/model-routing.mdc"; do
      if [ -f "$rule" ] && grep -Fq 'Managed by agent-workflow-skills' "$rule"; then rm -f "$rule"; fi
    done
    if [ "$owned" = 1 ]; then
      rm -f "$PROJECT/.cursor/agent-workflow-skills/model-routing.jsonc" \
        "$PROJECT/.cursor/agent-workflow-skills/dispatch_resolver.py" \
        "$PROJECT/.cursor/agent-workflow-skills/validate_jsonc.py" "$state"
    fi
    SUMMARY+=("cursor: processed spine rule $dest (removed only when bundle-owned)")
  fi
}

uninstall_opencode() {
  base="$OPENCODE_BASE"; state="$base/agent-workflow-skills/install-state.json"
  owned=0; [ ! -f "$state" ] || owned=1
  audit="$base/agent-workflow-skills/opencode-model-migration.json"
  verify_managed_spine "$state" "$base/AGENTS.md" "$base/skills"
  if [ "$owned" = 1 ] && { [ ! -f "$audit" ] || [ ! -f "$base/AGENTS.md" ] || ! grep -Fqx "$BEGIN_MARKER" "$base/AGENTS.md"; }; then
    echo "OpenCode bundle ownership state is incomplete; no files were changed." >&2
    return 1
  fi
  if [ "$owned" = 1 ] && [ -f "$audit" ]; then
    python_cmd="$(resolve_python)"
    "$python_cmd" "$REPO_ROOT/tools/migrate_opencode_models.py" \
      --config-dir "$base" --binding "$base/agent-workflow-skills/model-routing.jsonc" \
      --audit "$audit" --uninstall --check ||
      { echo "OpenCode uninstall preflight failed; no files were changed." >&2; return 1; }
    "$python_cmd" "$REPO_ROOT/tools/migrate_opencode_models.py" \
      --config-dir "$base" --binding "$base/agent-workflow-skills/model-routing.jsonc" \
      --audit "$audit" --uninstall ||
      { echo "OpenCode model config uninstall failed; managed role fields were not changed." >&2; return 1; }
  fi
  remove_skills "$base/skills"
  SUMMARY+=("opencode: removed bundle skills from $base/skills")
  remove_spine_block "$base/AGENTS.md"
  SUMMARY+=("opencode: removed spine marker block from $base/AGENTS.md")
  if [ "$owned" = 1 ]; then
    rm -f "$base/agent-workflow-skills/model-routing.jsonc" \
      "$base/agent-workflow-skills/dispatch_resolver.py" \
      "$base/agent-workflow-skills/validate_jsonc.py" \
      "$base/agent-workflow-skills/opencode-model-migration.json" "$state"
  fi
  SUMMARY+=("opencode: removed only verified managed JSON role fields; no Markdown role agents were restored")
}

uninstall_claude() {
  base="$HOME/.claude"
  state="$base/agent-workflow-skills/install-state.json"
  verify_managed_spine "$state" "$base/CLAUDE.md" "$base/skills"
  remove_skills "$base/skills"
  SUMMARY+=("claude: removed bundle skills from $base/skills")
  remove_spine_block "$base/CLAUDE.md"
  SUMMARY+=("claude: removed spine marker block from $base/CLAUDE.md")
  [ ! -f "$state" ] || rm -f "$state"
  SUMMARY+=("claude: removed bundle ownership state when present")
}

if [ "$TOOL" = opencode ] || [ "$TOOL" = all ]; then assert_spine_markers "$OPENCODE_BASE/AGENTS.md"; fi
if [ "$TOOL" = claude ] || [ "$TOOL" = all ]; then assert_spine_markers "$HOME/.claude/CLAUDE.md"; fi

case "$TOOL" in
  cursor)   uninstall_cursor ;;
  opencode) uninstall_opencode ;;
  claude)   uninstall_claude ;;
  all)      uninstall_cursor; uninstall_opencode; uninstall_claude ;;
  *) echo "invalid --tool: $TOOL (expected cursor|opencode|claude|all)" >&2; exit 1 ;;
esac

echo ""
echo "=== agent-workflow-skills uninstall summary (tool=$TOOL) ==="
for line in "${SUMMARY[@]}"; do echo "  - $line"; done
if [ "$TOOL" = opencode ] || [ "$TOOL" = all ]; then echo "Restart OpenCode to unload the removed files."; fi
echo "Done."
