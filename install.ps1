<#
.SYNOPSIS
  Install the agent-workflow-skills bundle (5 on-demand skills + 1 forced always-on spine rule)
  into a tool's config dir. Idempotent: re-running does not duplicate content.

.PARAMETER Tool
  cursor | opencode | claude | all   (default: cursor)

.PARAMETER Project
  Required for cursor/all. Writes the forced always-on rule
  <Project>\.cursor\rules\workflow-gate.mdc (per-project alwaysApply).

.EXAMPLE
  .\install.ps1 -Tool cursor -Project D:\work\my-repo
  .\install.ps1 -Tool all -Project D:\work\my-repo
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
$AgentMarker = '<!-- Managed by agent-workflow-skills. -->'
$summary = New-Object System.Collections.Generic.List[string]
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

function Write-NoBom([string]$Path, [string]$Text) {
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
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

function Resolve-Python {
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'Python 3 is required to validate an existing OpenCode JSON/JSONC config safely.'
}

function Test-OpenCodeConfig {
    $base = Join-Path $env:USERPROFILE '.config\opencode'
    $json = Join-Path $base 'opencode.json'
    $jsonc = Join-Path $base 'opencode.jsonc'
    if ((Test-Path -LiteralPath $json) -and (Test-Path -LiteralPath $jsonc)) {
        throw "Both $json and $jsonc exist. OpenCode config is ambiguous; remove or rename one. Nothing was installed."
    }
    $config = if (Test-Path -LiteralPath $jsonc) { $jsonc } elseif (Test-Path -LiteralPath $json) { $json } else { $null }
    if ($config) {
        $python = Resolve-Python
        & $python (Join-Path $RepoRoot 'tools\validate_jsonc.py') $config
        if ($LASTEXITCODE -ne 0) { throw "Invalid OpenCode config: $config. Nothing was installed." }
    }
    foreach ($name in @('build.md', 'review.md')) {
        $agent = Join-Path $base "agents\$name"
        if ((Test-Path -LiteralPath $agent) -and -not (Read-Utf8 $agent).Contains($AgentMarker)) {
            throw "OpenCode agent already exists and is not bundle-owned: $agent. Nothing was installed."
        }
    }
    return $config
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
    $raw = Read-Utf8 (Join-Path $RepoRoot 'rules\workflow-gate.mdc')
    $body = [regex]::Replace($raw, '^---\r?\n.*?\r?\n---\r?\n', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    return $body.Trim()
}

function Set-SpineBlock([string]$File) {
    # Idempotently place the spine between markers: replace the block if markers exist, else append.
    $body = Get-SpineBody
    $block = "$BeginMarker`n$body`n$EndMarker"
    if (Test-Path $File) {
        $content = Read-Utf8 $File
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
    $rulesDir = Join-Path $Project '.cursor\rules'
    if (-not (Test-Path $rulesDir)) { New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null }
    $dest = Join-Path $rulesDir 'workflow-gate.mdc'
    Copy-Item -Force -LiteralPath (Join-Path $RepoRoot 'rules\workflow-gate.mdc') -Destination $dest
    $summary.Add("cursor: forced always-on spine -> $dest (alwaysApply)")
}

function Install-OpenCode {
    $base = Join-Path $env:USERPROFILE '.config\opencode'
    $skillsDir = Join-Path $base 'skills'
    Copy-Skills $skillsDir
    $summary.Add("opencode: skills -> $skillsDir")
    $agents = Join-Path $base 'AGENTS.md'
    Set-SpineBlock $agents
    $summary.Add("opencode: spine injected -> $agents (marker block)")
    $agentDir = Join-Path $base 'agents'
    if (-not (Test-Path $agentDir)) { New-Item -ItemType Directory -Path $agentDir -Force | Out-Null }
    foreach ($name in @('build.md', 'review.md')) {
        Copy-Item -Force -LiteralPath (Join-Path $RepoRoot "opencode\agents\$name") -Destination (Join-Path $agentDir $name)
    }
    $summary.Add("opencode: native agents -> $agentDir\{build,review}.md")
    $configLabel = if ($script:OpenCodeConfig) { $script:OpenCodeConfig } else { 'none present; none created' }
    $summary.Add("opencode: main config untouched -> $configLabel")
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

if (($Tool -eq 'cursor' -or $Tool -eq 'all') -and -not $Project) {
    throw '-Project is required for Cursor installation so the forced spine is installed automatically. Nothing was installed.'
}
if ($Tool -eq 'opencode' -or $Tool -eq 'all') {
    $script:OpenCodeConfig = Test-OpenCodeConfig
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
if ($Tool -eq 'opencode' -or $Tool -eq 'all') { Write-Host "Restart OpenCode to load the installed files." }
Write-Host "Done."
