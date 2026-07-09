<#
.SYNOPSIS
  Install the agent-workflow-skills bundle (5 on-demand skills + 1 forced always-on spine rule)
  into a tool's config dir. Idempotent: re-running does not duplicate content.

.PARAMETER Tool
  cursor | opencode | claude | all   (default: cursor)

.PARAMETER Project
  Optional project path. For Cursor it writes the forced always-on rule
  <Project>\.cursor\rules\workflow-gate.mdc (per-project alwaysApply).

.EXAMPLE
  .\install.ps1 -Tool cursor -Project D:\work\my-repo
  .\install.ps1 -Tool all
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
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Copy-Skills([string]$DestSkillsDir) {
    if (-not (Test-Path $DestSkillsDir)) { New-Item -ItemType Directory -Path $DestSkillsDir -Force | Out-Null }
    Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'skills') | ForEach-Object {
        $dest = Join-Path $DestSkillsDir $_.Name
        if (Test-Path $dest) { Remove-Item -Recurse -Force -LiteralPath $dest }
        Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $dest
    }
}

function Get-SpineBody {
    # Read rules/workflow-gate.mdc and strip the leading --- ... --- frontmatter.
    $raw = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot 'rules\workflow-gate.mdc')
    $body = [regex]::Replace($raw, '^---\r?\n.*?\r?\n---\r?\n', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    return $body.Trim()
}

function Set-SpineBlock([string]$File) {
    # Idempotently place the spine between markers: replace the block if markers exist, else append.
    $body = Get-SpineBody
    $block = "$BeginMarker`n$body`n$EndMarker"
    if (Test-Path $File) {
        $content = Get-Content -Raw -LiteralPath $File
        if ($null -eq $content) { $content = '' }
        $bi = $content.IndexOf($BeginMarker)
        $ei = $content.IndexOf($EndMarker)
        if ($bi -ge 0 -and $ei -ge $bi) {
            $before = $content.Substring(0, $bi)
            $after = $content.Substring($ei + $EndMarker.Length)
            $new = $before + $block + $after
        }
        else {
            $new = $content.TrimEnd() + "`n`n" + $block + "`n"
        }
    }
    else {
        $new = $block + "`n"
    }
    Write-NoBom $File $new
}

function Install-Cursor {
    $skillsDir = Join-Path $env:USERPROFILE '.cursor\skills'
    Copy-Skills $skillsDir
    $summary.Add("cursor: skills -> $skillsDir")
    if ($Project) {
        $rulesDir = Join-Path $Project '.cursor\rules'
        if (-not (Test-Path $rulesDir)) { New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null }
        $dest = Join-Path $rulesDir 'workflow-gate.mdc'
        Copy-Item -Force -LiteralPath (Join-Path $RepoRoot 'rules\workflow-gate.mdc') -Destination $dest
        $summary.Add("cursor: forced always-on spine -> $dest (alwaysApply)")
    }
    else {
        Write-Host "[note] Cursor's file-based forced always-on rule is PER-PROJECT. Re-run with -Project <path> to write rules/workflow-gate.mdc into <project>\.cursor\rules\." -ForegroundColor Yellow
        Write-Host "[note] Cursor has NO file-based cross-project global always-on rule. To apply the spine to ALL projects you must paste rules/workflow-gate.mdc once via Settings -> Rules (GUI). This is the single unavoidable manual step (a Cursor platform limit)." -ForegroundColor Yellow
        $summary.Add("cursor: no -Project given -> forced spine NOT written (see notes above)")
    }
}

function Install-OpenCode {
    $base = Join-Path $env:USERPROFILE '.config\opencode'
    $skillsDir = Join-Path $base 'skills'
    Copy-Skills $skillsDir
    $summary.Add("opencode: skills -> $skillsDir")
    $agents = Join-Path $base 'AGENTS.md'
    Set-SpineBlock $agents
    $summary.Add("opencode: spine injected -> $agents (marker block)")
    $cfgDest = Join-Path $base 'opencode.json'
    if (Test-Path $cfgDest) {
        Write-Host "[note] $cfgDest already exists; NOT overwritten. Merge the 'agent' block manually from opencode/opencode.json." -ForegroundColor Yellow
        $summary.Add("opencode: opencode.json exists -> left as-is (merge 'agent' block manually)")
    }
    else {
        Copy-Item -Force -LiteralPath (Join-Path $RepoRoot 'opencode\opencode.json') -Destination $cfgDest
        $summary.Add("opencode: opencode.json -> $cfgDest")
    }
}

function Install-Claude {
    $base = Join-Path $env:USERPROFILE '.claude'
    $skillsDir = Join-Path $base 'skills'
    Copy-Skills $skillsDir
    $summary.Add("claude: skills -> $skillsDir")
    $claudeMd = Join-Path $base 'CLAUDE.md'
    Set-SpineBlock $claudeMd
    $summary.Add("claude: spine injected -> $claudeMd (marker block)")
}

switch ($Tool) {
    'cursor' { Install-Cursor }
    'opencode' { Install-OpenCode }
    'claude' { Install-Claude }
    'all' { Install-Cursor; Install-OpenCode; Install-Claude }
}

Write-Host ""
Write-Host "=== agent-workflow-skills install summary (tool=$Tool) ===" -ForegroundColor Cyan
foreach ($line in $summary) { Write-Host "  - $line" }
Write-Host "Done."
