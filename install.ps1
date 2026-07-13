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
    [string]$Project,
    [string]$OpenCodeConfigDir,
    [Alias('OpenCodeBuildModel')][string]$BuildModel,
    [Alias('OpenCodeReasonModel')][string]$ReasonModel,
    [Alias('OpenCodeReviewModel')][string]$ReviewModel
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$BeginMarker = '<!-- BEGIN agent-workflow-skills spine -->'
$EndMarker = '<!-- END agent-workflow-skills spine -->'
$AgentMarker = '<!-- Managed by agent-workflow-skills. -->'
$SkillMarker = '.agent-workflow-skills-owned'
$OpenCodeBase = if ($OpenCodeConfigDir) { $OpenCodeConfigDir } else { Join-Path $env:USERPROFILE '.config\opencode' }
if (-not $BuildModel) { $BuildModel = $env:AGENT_WORKFLOW_OPENCODE_BUILD_MODEL }
if (-not $ReasonModel) { $ReasonModel = $env:AGENT_WORKFLOW_OPENCODE_REASON_MODEL }
if (-not $ReviewModel) { $ReviewModel = $env:AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL }
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
        if ($command) {
            & $command.Source -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)'
            if ($LASTEXITCODE -eq 0) { return $command.Source }
        }
    }
    throw 'A runnable Python 3 interpreter is required to validate and stage model bindings.'
}

function New-InstallStage([string]$Binding) {
    $stage = Join-Path ([IO.Path]::GetTempPath()) "agent-workflow-$([guid]::NewGuid().ToString('N'))"
    $python = Resolve-Python
    $build = if ($BuildModel) { $BuildModel } else { '-' }
    $reason = if ($ReasonModel) { $ReasonModel } else { '-' }
    $review = if ($ReviewModel) { $ReviewModel } else { '-' }
    & $python (Join-Path $RepoRoot 'tools\prepare_install.py') $stage $Binding $build $reason $review | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
        throw "Model binding validation failed. Nothing was installed."
    }
    return $stage
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
        throw "Corrupted agent-workflow-skills spine markers in $File. Nothing was installed."
    }
}

function Test-OpenCodeConfig {
    $present = @('opencode.json', 'opencode.jsonc') | Where-Object { Test-Path -LiteralPath (Join-Path $OpenCodeBase $_) }
    $config = if ($present.Count) { ($present | ForEach-Object { Join-Path $OpenCodeBase $_ }) -join ', ' } else { $null }
    $state = Join-Path $OpenCodeBase 'agent-workflow-skills\install-state.json'
    $binding = Join-Path $OpenCodeBase 'agent-workflow-skills\model-routing.jsonc'
    if ((Test-Path $binding) -and -not (Test-Path $state)) { throw "Model binding exists without bundle ownership: $binding. Nothing was installed." }
    foreach ($name in @('build.md', 'reason.md', 'review.md')) {
        $agent = Join-Path $OpenCodeBase "agents\$name"
        if ((Test-Path -LiteralPath $agent) -and -not (Read-Utf8 $agent).Contains($AgentMarker)) {
            throw "OpenCode agent already exists and is not bundle-owned: $agent. Nothing was installed."
        }
    }
    Test-SkillOwnership (Join-Path $OpenCodeBase 'skills')
    return $config
}

function Test-SkillOwnership([string]$DestSkillsDir) {
    Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'skills') | ForEach-Object {
        $dest = Join-Path $DestSkillsDir $_.Name
        if ((Test-Path $dest) -and -not (Test-Path (Join-Path $dest $SkillMarker))) {
            throw "Skill already exists and is not bundle-owned: $dest. Nothing was installed."
        }
    }
}

function Copy-Skills([string]$DestSkillsDir, [string]$Source = (Join-Path $RepoRoot 'skills')) {
    if (-not (Test-Path $DestSkillsDir)) { New-Item -ItemType Directory -Path $DestSkillsDir -Force | Out-Null }
    Get-ChildItem -Directory -LiteralPath $Source | ForEach-Object {
        $dest = Join-Path $DestSkillsDir $_.Name
        if (Test-Path $dest) { Remove-Item -Recurse -Force -LiteralPath $dest }
        Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $dest
        Write-NoBom (Join-Path $dest $SkillMarker) "agent-workflow-skills`n"
    }
}

function Set-BundleState([string]$Dir, [string]$Stage) {
    if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
    Copy-Item -Force (Join-Path $Stage 'model-routing.jsonc') (Join-Path $Dir 'model-routing.jsonc')
    Copy-Item -Force (Join-Path $Stage 'install-state.json') (Join-Path $Dir 'install-state.json')
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
        Test-SpineMarkerIntegrity $File
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
    Copy-Skills $skillsDir (Join-Path $script:CursorStage 'skills')
    $summary.Add("cursor: skills -> $skillsDir")
    $rulesDir = Join-Path $Project '.cursor\rules'
    if (-not (Test-Path $rulesDir)) { New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null }
    $dest = Join-Path $rulesDir 'workflow-gate.mdc'
    Copy-Item -Force -LiteralPath (Join-Path $script:CursorStage 'workflow-gate.mdc') -Destination $dest
    Copy-Item -Force -LiteralPath (Join-Path $script:CursorStage 'model-routing.mdc') -Destination (Join-Path $rulesDir 'model-routing.mdc')
    Set-BundleState (Join-Path $Project '.cursor\agent-workflow-skills') $script:CursorStage
    $summary.Add("cursor: forced always-on spine -> $dest (alwaysApply)")
    $summary.Add("cursor: project model adapter -> $rulesDir\model-routing.mdc")
    $summary.Add("cursor: model binding -> $Project\.cursor\agent-workflow-skills\model-routing.jsonc")
}

function Install-OpenCode {
    $base = $OpenCodeBase
    $skillsDir = Join-Path $base 'skills'
    Copy-Skills $skillsDir (Join-Path $script:OpenCodeStage 'skills')
    $summary.Add("opencode: skills -> $skillsDir")
    $agents = Join-Path $base 'AGENTS.md'
    Set-SpineBlock $agents
    $summary.Add("opencode: spine injected -> $agents (marker block)")
    $agentDir = Join-Path $base 'agents'
    if (-not (Test-Path $agentDir)) { New-Item -ItemType Directory -Path $agentDir -Force | Out-Null }
    foreach ($name in @('build.md', 'reason.md', 'review.md')) {
        Copy-Item -Force (Join-Path $script:OpenCodeStage "agents\$name") (Join-Path $agentDir $name)
    }
    Set-BundleState (Join-Path $base 'agent-workflow-skills') $script:OpenCodeStage
    $summary.Add("opencode: native agents -> $agentDir\{build,reason,review}.md")
    $summary.Add("opencode: model binding -> $base\agent-workflow-skills\model-routing.jsonc")
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
    Test-SpineMarkerIntegrity (Join-Path $OpenCodeBase 'AGENTS.md')
    $script:OpenCodeStage = New-InstallStage (Join-Path $OpenCodeBase 'agent-workflow-skills\model-routing.jsonc')
}
if ($Tool -eq 'cursor' -or $Tool -eq 'all') {
    $cursorState = Join-Path $Project '.cursor\agent-workflow-skills\install-state.json'
    $cursorBinding = Join-Path $Project '.cursor\agent-workflow-skills\model-routing.jsonc'
    if ((Test-Path $cursorBinding) -and -not (Test-Path $cursorState)) { throw "Cursor model binding exists without bundle ownership. Nothing was installed." }
    Test-SkillOwnership (Join-Path $env:USERPROFILE '.cursor\skills')
    foreach ($name in @('workflow-gate.mdc', 'model-routing.mdc')) {
        $rule = Join-Path $Project ".cursor\rules\$name"
        if ((Test-Path $rule) -and -not (Read-Utf8 $rule).Contains('Managed by agent-workflow-skills')) {
            throw "Cursor rule already exists and is not bundle-owned: $rule. Nothing was installed."
        }
    }
    $script:CursorStage = New-InstallStage $cursorBinding
}
if ($Tool -eq 'claude' -or $Tool -eq 'all') {
    Test-SpineMarkerIntegrity (Join-Path $env:USERPROFILE '.claude\CLAUDE.md')
}

try {
    switch ($Tool) {
        'cursor' { Install-Cursor }
        'opencode' { Install-OpenCode }
        'claude' { Install-Claude }
        'all' { Install-Cursor; Install-OpenCode; Install-Claude }
    }
}
finally {
    foreach ($stage in @($script:CursorStage, $script:OpenCodeStage)) {
        if ($stage -and (Test-Path $stage)) { Remove-Item -Recurse -Force $stage }
    }
}

Write-Host ""
Write-Host "=== agent-workflow-skills install summary (tool=$Tool) ===" -ForegroundColor Cyan
foreach ($line in $summary) { Write-Host "  - $line" }
if ($Tool -eq 'opencode' -or $Tool -eq 'all') { Write-Host "Restart OpenCode to load the installed files." }
Write-Host "Done."
