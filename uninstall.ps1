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

function Resolve-Python {
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            & $command.Source -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)'
            if ($LASTEXITCODE -eq 0) { return $command.Source }
        }
    }
    throw 'A runnable Python 3 interpreter is required to verify managed OpenCode role fields.'
}

function Test-ManagedSpineOwnership([string]$State, [string]$Adapter, [string]$Skills) {
    if (-not (Test-Path -LiteralPath $Adapter)) { return }
    $content = Read-Utf8 $Adapter
    $hasBegin = $content.Contains($BeginMarker)
    $hasEnd = $content.Contains($EndMarker)
    if (-not $hasBegin -and -not $hasEnd) { return }
    if (-not $hasBegin -or -not $hasEnd -or -not (Test-Path -LiteralPath $State)) {
        throw "Managed spine marker lacks valid ownership state: $Adapter"
    }
    $python = Resolve-Python
    & $python (Join-Path $RepoRoot 'tools\verify_install_state.py') `
        '--state' $State '--adapter' $Adapter '--skills' $Skills '--spine' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Managed spine provenance validation failed: $Adapter"
    }
}

function Test-CursorOwnership {
    $skills = Join-Path $env:USERPROFILE '.cursor\skills'
    $rules = if ($Project) { Join-Path $Project '.cursor\rules' } else { $null }
    $bundle = if ($Project) { Join-Path $Project '.cursor\agent-workflow-skills' } else { $null }
    $state = if ($bundle) { Join-Path $bundle 'install-state.json' } else { $null }
    $candidate = $state -and (Test-Path -LiteralPath $state)
    if ($Project) {
        foreach ($name in @('workflow-gate.mdc', 'model-routing.mdc')) {
            $candidate = $candidate -or (Test-Path -LiteralPath (Join-Path $rules $name))
        }
    }
    foreach ($source in Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'policy-v3\generated\skills')) {
        $candidate = $candidate -or (Test-Path -LiteralPath (Join-Path $skills $source.Name))
    }
    if (-not $candidate) { return }
    if (-not $Project -or -not (Test-Path -LiteralPath $state)) {
        throw 'Cursor bundle artifacts require -Project and a valid install-state.json. Nothing was uninstalled.'
    }
    $python = Resolve-Python
    & $python (Join-Path $RepoRoot 'tools\verify_cursor_ownership.py') `
        '--state' $state '--rules' $rules '--skills' $skills '--bundle' $bundle | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Cursor ownership validation failed. Nothing was uninstalled.'
    }
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
    Test-CursorOwnership
    Remove-Skills $skillsDir
    $summary.Add("cursor: removed bundle skills from $skillsDir")
    if ($Project) {
        $dest = Join-Path $Project '.cursor\rules\workflow-gate.mdc'
        foreach ($name in @('workflow-gate.mdc', 'model-routing.mdc')) {
            $rule = Join-Path $Project ".cursor\rules\$name"
            if ((Test-Path $rule) -and (Read-Utf8 $rule).Contains('Managed by agent-workflow-skills')) { Remove-Item -Force $rule }
        }
        if ($owned) {
            foreach ($name in @('model-routing.jsonc', 'dispatch_resolver.py', 'validate_jsonc.py')) {
                Remove-Item -Force (Join-Path (Split-Path $state) $name) -ErrorAction SilentlyContinue
            }
            Remove-Item -Force $state
        }
        $summary.Add("cursor: processed spine rule $dest (removed only when bundle-owned)")
    }
}

function Uninstall-OpenCode {
    $base = $OpenCodeBase
    $state = Join-Path $base 'agent-workflow-skills\install-state.json'
    $owned = Test-Path $state
    $audit = Join-Path $base 'agent-workflow-skills\opencode-model-migration.json'
    $agents = Join-Path $base 'AGENTS.md'
    Test-ManagedSpineOwnership $state $agents (Join-Path $base 'skills')
    if ($owned -and ((-not (Test-Path -LiteralPath $audit)) -or (-not (Test-Path -LiteralPath $agents)) -or (-not (Read-Utf8 $agents).Contains($BeginMarker)))) {
        throw 'OpenCode bundle ownership state is incomplete; no files were changed.'
    }
    if ($owned -and (Test-Path $audit)) {
        $python = Resolve-Python
        & $python (Join-Path $RepoRoot 'tools\migrate_opencode_models.py') `
            '--config-dir' $base '--binding' (Join-Path $base 'agent-workflow-skills\model-routing.jsonc') `
            '--audit' $audit '--uninstall' '--check' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'OpenCode uninstall preflight failed; no files were changed.'
        }
        & $python (Join-Path $RepoRoot 'tools\migrate_opencode_models.py') `
            '--config-dir' $base '--binding' (Join-Path $base 'agent-workflow-skills\model-routing.jsonc') `
            '--audit' $audit '--uninstall' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'OpenCode model config uninstall failed; managed role fields were not changed.'
        }
    }
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("opencode: removed bundle skills from $base\skills")
    Remove-SpineBlock $agents
    $summary.Add("opencode: removed spine marker block from $agents")
    if ($owned) {
        foreach ($name in @('model-routing.jsonc', 'dispatch_resolver.py', 'validate_jsonc.py', 'opencode-model-migration.json')) {
            Remove-Item -Force (Join-Path $base "agent-workflow-skills\$name") -ErrorAction SilentlyContinue
        }
        Remove-Item -Force $state
    }
    $summary.Add("opencode: removed only verified managed JSON role fields; no Markdown role agents were restored")
}

function Uninstall-Claude {
    $base = Join-Path $env:USERPROFILE '.claude'
    $state = Join-Path $base 'agent-workflow-skills\install-state.json'
    $claudeMd = Join-Path $base 'CLAUDE.md'
    Test-ManagedSpineOwnership $state $claudeMd (Join-Path $base 'skills')
    Remove-Skills (Join-Path $base 'skills')
    $summary.Add("claude: removed bundle skills from $base\skills")
    Remove-SpineBlock $claudeMd
    $summary.Add("claude: removed spine marker block from $claudeMd")
    if (Test-Path $state) { Remove-Item -Force $state }
    $summary.Add("claude: removed bundle ownership state when present")
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
