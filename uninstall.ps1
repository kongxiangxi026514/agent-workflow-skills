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
  .\uninstall.ps1 -Tool all -Project D:\work\my-repo
#>
[CmdletBinding()]
param(
    [ValidateSet('cursor', 'opencode', 'claude', 'all')]
    [string]$Tool = 'cursor',
    [string]$Project,
    [string]$OpenCodeConfigDir
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$BeginMarker = '<!-- BEGIN agent-workflow-skills spine -->'
$EndMarker = '<!-- END agent-workflow-skills spine -->'
$AgentMarker = '<!-- Managed by agent-workflow-skills. -->'
$SkillMarker = '.agent-workflow-skills-owned'
$OpenCodeBase = if ($OpenCodeConfigDir) { $OpenCodeConfigDir } else { Join-Path $env:USERPROFILE '.config\opencode' }
$summary = New-Object System.Collections.Generic.List[string]
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

function Write-NoBom([string]$Path, [string]$Text) {
    $temp = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [System.IO.File]::WriteAllText($temp, $Text, $Utf8NoBom)
        Move-Item -Force -LiteralPath $temp -Destination $Path
    }
    finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -Force -LiteralPath $temp }
    }
}

function Read-Utf8([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, $Utf8Strict)
}

function Test-SpineMarkerIntegrity([string]$File) {
    if (-not (Test-Path -LiteralPath $File)) { return }
    $content = Read-Utf8 $File
    $beginCount = [regex]::Matches($content, [regex]::Escape($BeginMarker)).Count
    $endCount = [regex]::Matches($content, [regex]::Escape($EndMarker)).Count
    if ($beginCount -eq 0 -and $endCount -eq 0) { return }
    $bi = $content.IndexOf($BeginMarker)
    $ei = $content.IndexOf($EndMarker)
    if ($beginCount -ne 1 -or $endCount -ne 1 -or $ei -lt $bi) {
        throw "Corrupted agent-workflow-skills spine markers in $File. Nothing was uninstalled."
    }
}

function Remove-Skills([string]$DestSkillsDir) {
    # Only remove the skill folders that this bundle ships (never a whole skills dir).
    if (-not (Test-Path $DestSkillsDir)) { return }
    Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'policy-v3\generated\skills') | ForEach-Object {
        $dest = Join-Path $DestSkillsDir $_.Name
        if ((Test-Path $dest) -and (Test-Path (Join-Path $dest $SkillMarker))) {
            Remove-Item -Recurse -Force -LiteralPath $dest
        }
    }
}

function Remove-SpineBlock([string]$File) {
    # Strip the spine marker block, leaving the rest of the file intact.
    if (-not (Test-Path $File)) { return }
    $content = Read-Utf8 $File
    if ($null -eq $content) { return }
    Test-SpineMarkerIntegrity $File
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
    $state = if ($Project) { Join-Path $Project '.cursor\agent-workflow-skills\install-state.json' } else { $null }
    $owned = $state -and (Test-Path $state)
    Remove-Skills $skillsDir
    $summary.Add("cursor: removed bundle skills from $skillsDir")
    if ($Project) {
        $dest = Join-Path $Project '.cursor\rules\workflow-gate.mdc'
        foreach ($name in @('workflow-gate.mdc', 'model-routing.mdc')) {
            $rule = Join-Path $Project ".cursor\rules\$name"
            if ((Test-Path $rule) -and (Read-Utf8 $rule).Contains('Managed by agent-workflow-skills')) { Remove-Item -Force $rule }
        }
        if ($owned) {
            Remove-Item -Force (Join-Path (Split-Path $state) 'model-routing.jsonc') -ErrorAction SilentlyContinue
            Remove-Item -Force $state
        }
        $summary.Add("cursor: processed spine rule $dest (removed only when bundle-owned)")
    }
}

function Uninstall-OpenCode {
    $base = $OpenCodeBase
    $state = Join-Path $base 'agent-workflow-skills\install-state.json'
    $owned = Test-Path $state
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("opencode: removed bundle skills from $base\skills")
    $agents = Join-Path $base 'AGENTS.md'
    Remove-SpineBlock $agents
    $summary.Add("opencode: removed spine marker block from $agents")
    foreach ($name in @('build.md', 'reason.md', 'review.md')) {
        $path = Join-Path $base "agents\$name"
        if ((Test-Path -LiteralPath $path) -and (Read-Utf8 $path).Contains($AgentMarker)) {
            Remove-Item -Force -LiteralPath $path
        }
    }
    $summary.Add("opencode: processed native agents in $base\agents (removed only when bundle-owned; main config untouched)")
    if ($owned) {
        Remove-Item -Force (Join-Path $base 'agent-workflow-skills\model-routing.jsonc') -ErrorAction SilentlyContinue
        Remove-Item -Force $state
    }
}

function Uninstall-Claude {
    $base = Join-Path $env:USERPROFILE '.claude'
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("claude: removed bundle skills from $base\skills")
    $claudeMd = Join-Path $base 'CLAUDE.md'
    Remove-SpineBlock $claudeMd
    $summary.Add("claude: removed spine marker block from $claudeMd")
}

if ($Tool -eq 'opencode' -or $Tool -eq 'all') {
    Test-SpineMarkerIntegrity (Join-Path $OpenCodeBase 'AGENTS.md')
}
if ($Tool -eq 'claude' -or $Tool -eq 'all') {
    Test-SpineMarkerIntegrity (Join-Path $env:USERPROFILE '.claude\CLAUDE.md')
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
if ($Tool -eq 'opencode' -or $Tool -eq 'all') { Write-Host "Restart OpenCode to unload the removed files." }
Write-Host "Done."
