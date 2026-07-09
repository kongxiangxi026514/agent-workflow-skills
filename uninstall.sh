#!/usr/bin/env bash
# Uninstall the agent-workflow-skills bundle from a tool's config dir.
# Reverse of install.sh. Idempotent: no error if items are already absent.
#
# Usage:
#   ./uninstall.sh [--tool cursor|opencode|claude|all] [--project <path>]
# Default tool is cursor.
set -euo pipefail

TOOL="cursor"
PROJECT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --tool) TOOL="${2:-}"; shift 2 ;;
    --tool=*) TOOL="${1#*=}"; shift ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --project=*) PROJECT="${1#*=}"; shift ;;
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

remove_skills() {
  # Only remove the skill folders that this bundle ships (never a whole skills dir).
  dest="$1"
  [ -d "$dest" ] || return 0
  for d in "$REPO_ROOT"/skills/*/; do
    name="$(basename "$d")"
    rm -rf "$dest/$name"
  done
}

remove_spine_block() {
  file="$1"
  [ -f "$file" ] || return 0
  awk -v b="$BEGIN_MARKER" -v e="$END_MARKER" '
    $0==b { skip=1 }
    skip!=1 { print }
    $0==e { skip=0 }
  ' "$file" > "$file.tmp"
  mv "$file.tmp" "$file"
}

uninstall_cursor() {
  skills_dir="$HOME/.cursor/skills"
  remove_skills "$skills_dir"
  SUMMARY+=("cursor: removed bundle skills from $skills_dir")
  if [ -n "$PROJECT" ]; then
    dest="$PROJECT/.cursor/rules/workflow-gate.mdc"
    rm -f "$dest"
    SUMMARY+=("cursor: removed forced spine rule $dest")
  fi
}

uninstall_opencode() {
  base="$HOME/.config/opencode"
  remove_skills "$base/skills"
  SUMMARY+=("opencode: removed bundle skills from $base/skills")
  remove_spine_block "$base/AGENTS.md"
  SUMMARY+=("opencode: removed spine marker block from $base/AGENTS.md (opencode.json left intact)")
}

uninstall_claude() {
  base="$HOME/.claude"
  remove_skills "$base/skills"
  SUMMARY+=("claude: removed bundle skills from $base/skills")
  remove_spine_block "$base/CLAUDE.md"
  SUMMARY+=("claude: removed spine marker block from $base/CLAUDE.md")
}

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
echo "Done."
