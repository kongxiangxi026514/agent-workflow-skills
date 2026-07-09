#!/usr/bin/env bash
# Install the agent-workflow-skills bundle (4 on-demand skills + 1 forced always-on spine rule)
# into a tool's config dir. Idempotent: re-running does not duplicate content.
#
# Usage:
#   ./install.sh [--tool cursor|opencode|claude|all] [--project <path>]
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

set_spine_block() {
  # Idempotent: strip any existing block, then append a fresh one.
  file="$1"
  mkdir -p "$(dirname "$file")"
  remove_spine_block "$file"
  {
    if [ -s "$file" ]; then printf '\n'; fi
    printf '%s\n' "$BEGIN_MARKER"
    spine_body
    printf '%s\n' "$END_MARKER"
  } >> "$file"
}

install_cursor() {
  skills_dir="$HOME/.cursor/skills"
  copy_skills "$skills_dir"
  SUMMARY+=("cursor: skills -> $skills_dir")
  if [ -n "$PROJECT" ]; then
    rules_dir="$PROJECT/.cursor/rules"
    mkdir -p "$rules_dir"
    cp -f "$REPO_ROOT/rules/workflow-gate.mdc" "$rules_dir/workflow-gate.mdc"
    SUMMARY+=("cursor: forced always-on spine -> $rules_dir/workflow-gate.mdc (alwaysApply)")
  else
    echo "[note] Cursor's file-based forced always-on rule is PER-PROJECT. Re-run with --project <path> to write rules/workflow-gate.mdc into <project>/.cursor/rules/."
    echo "[note] Cursor has NO file-based cross-project global always-on rule. Applying the spine to ALL projects needs a one-time Settings -> Rules GUI paste of rules/workflow-gate.mdc (single unavoidable manual step, a Cursor platform limit)."
    SUMMARY+=("cursor: no --project given -> forced spine NOT written (see notes above)")
  fi
}

install_opencode() {
  base="$HOME/.config/opencode"
  copy_skills "$base/skills"
  SUMMARY+=("opencode: skills -> $base/skills")
  set_spine_block "$base/AGENTS.md"
  SUMMARY+=("opencode: spine injected -> $base/AGENTS.md (marker block)")
  if [ -f "$base/opencode.json" ]; then
    echo "[note] $base/opencode.json exists; NOT overwritten. Merge the 'agent' block manually from opencode/opencode.json."
    SUMMARY+=("opencode: opencode.json exists -> left as-is (merge 'agent' block manually)")
  else
    mkdir -p "$base"
    cp -f "$REPO_ROOT/opencode/opencode.json" "$base/opencode.json"
    SUMMARY+=("opencode: opencode.json -> $base/opencode.json")
  fi
}

install_claude() {
  base="$HOME/.claude"
  copy_skills "$base/skills"
  SUMMARY+=("claude: skills -> $base/skills")
  set_spine_block "$base/CLAUDE.md"
  SUMMARY+=("claude: spine injected -> $base/CLAUDE.md (marker block)")
}

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
echo "Done."
