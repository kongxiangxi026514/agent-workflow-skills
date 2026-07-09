<#
.SYNOPSIS
  Uninstall the agent-workflow-skills bundle from a tool's config dir.
  Reverse of install.ps1. Idempotent: no error if items are already absent.

.PARAMETER Tool
  cursor | opencode | claude | all   (default: cursor)

.PARAMETER Project
  Optional project path. For Cursor it removes <Project>\.cursor\rules\workflow-gate.mdc.

.EXAMPLE
  .\uninstall.ps1 -Tool cursor -Project D:\work\my-repo
  .\uninstall.ps1 -Tool all
#>
[CmdletBinding()]
param(
    [ValidateSet('cursor', 'opencode', 'claude', 'all')]
    [string]$Tool = 'cursor',
    [string]$Project
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$BeginMarker = '<!-- BEGIN agent-workflow-skills spine -->'
$EndMarker = '<!-- END agent-workflow-skills spine -->'
$summary = New-Object System.Collections.Generic.List[string]

function Write-NoBom([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Remove-Skills([string]$DestSkillsDir) {
    # Only remove the skill folders that this bundle ships (never a whole skills dir).
    if (-not (Test-Path $DestSkillsDir)) { return }
    Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'skills') | ForEach-Object {
        $dest = Join-Path $DestSkillsDir $_.Name
        if (Test-Path $dest) { Remove-Item -Recurse -Force -LiteralPath $dest }
    }
}

function Remove-SpineBlock([string]$File) {
    # Strip the spine marker block, leaving the rest of the file intact.
    if (-not (Test-Path $File)) { return }
    $content = Get-Content -Raw -LiteralPath $File
    if ($null -eq $content) { return }
    $bi = $content.IndexOf($BeginMarker)
    $ei = $content.IndexOf($EndMarker)
    if ($bi -lt 0 -or $ei -lt $bi) { return }
    $before = $content.Substring(0, $bi)
    $after = $content.Substring($ei + $EndMarker.Length)
    $new = ($before.TrimEnd() + "`n" + $after.TrimStart()).Trim()
    if ($new.Length -gt 0) { $new = $new + "`n" }
    Write-NoBom $File $new
}

function Uninstall-Cursor {
    $skillsDir = Join-Path $env:USERPROFILE '.cursor\skills'
    Remove-Skills $skillsDir
    $summary.Add("cursor: removed bundle skills from $skillsDir")
    if ($Project) {
        $dest = Join-Path $Project '.cursor\rules\workflow-gate.mdc'
        if (Test-Path $dest) { Remove-Item -Force -LiteralPath $dest }
        $summary.Add("cursor: removed forced spine rule $dest")
    }
}

function Uninstall-OpenCode {
    $base = Join-Path $env:USERPROFILE '.config\opencode'
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("opencode: removed bundle skills from $base\skills")
    $agents = Join-Path $base 'AGENTS.md'
    Remove-SpineBlock $agents
    $summary.Add("opencode: removed spine marker block from $agents (opencode.json left intact)")
}

function Uninstall-Claude {
    $base = Join-Path $env:USERPROFILE '.claude'
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("claude: removed bundle skills from $base\skills")
    $claudeMd = Join-Path $base 'CLAUDE.md'
    Remove-SpineBlock $claudeMd
    $summary.Add("claude: removed spine marker block from $claudeMd")
}

switch ($Tool) {
    'cursor' { Uninstall-Cursor }
    'opencode' { Uninstall-OpenCode }
    'claude' { Uninstall-Claude }
    'all' { Uninstall-Cursor; Uninstall-OpenCode; Uninstall-Claude }
}

Write-Host ""
Write-Host "=== agent-workflow-skills uninstall summary (tool=$Tool) ===" -ForegroundColor Cyan
foreach ($line in $summary) { Write-Host "  - $line" }
Write-Host "Done."
