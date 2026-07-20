<#
.SYNOPSIS
  Install the agent-workflow-skills bundle (6 on-demand skills + 1 forced always-on spine rule)
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
    [string]$OpenCodeModelConfig,
    [switch]$MigrateOpenCodeModelConfig,
    [Alias('Profile')][ValidateSet('lean', 'balanced')][string]$InstallProfile,
    [string]$BuildModel,
    [string]$ReasonModel,
    [string]$ReviewModel,
    [string]$CursorBuildModel,
    [string]$CursorReasonModel,
    [string]$CursorReviewModel,
    [string]$OpenCodeBuildModel,
    [string]$OpenCodeReasonModel,
    [string]$OpenCodeReviewModel
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot
$BeginMarker = '<!-- BEGIN agent-workflow-skills spine -->'
$EndMarker = '<!-- END agent-workflow-skills spine -->'
$SkillMarker = '.agent-workflow-skills-owned'
$OpenCodeBase = if ($OpenCodeConfigDir) { $OpenCodeConfigDir } else { Join-Path $env:USERPROFILE '.config\opencode' }
if ($Tool -eq 'all' -and ($BuildModel -or $ReasonModel -or $ReviewModel)) {
    throw 'Generic model options are ambiguous for -Tool all. Use platform-specific Cursor* and OpenCode* options.'
}
if ($Tool -eq 'cursor') {
    if (-not $CursorBuildModel) { $CursorBuildModel = $BuildModel }
    if (-not $CursorReasonModel) { $CursorReasonModel = $ReasonModel }
    if (-not $CursorReviewModel) { $CursorReviewModel = $ReviewModel }
}
if ($Tool -eq 'opencode') {
    if (-not $OpenCodeBuildModel) { $OpenCodeBuildModel = $BuildModel }
    if (-not $OpenCodeReasonModel) { $OpenCodeReasonModel = $ReasonModel }
    if (-not $OpenCodeReviewModel) { $OpenCodeReviewModel = $ReviewModel }
}
if (-not $CursorBuildModel) { $CursorBuildModel = $env:AGENT_WORKFLOW_CURSOR_BUILD_MODEL }
if (-not $CursorReasonModel) { $CursorReasonModel = $env:AGENT_WORKFLOW_CURSOR_REASON_MODEL }
if (-not $CursorReviewModel) { $CursorReviewModel = $env:AGENT_WORKFLOW_CURSOR_REVIEW_MODEL }
if (-not $OpenCodeBuildModel) { $OpenCodeBuildModel = $env:AGENT_WORKFLOW_OPENCODE_BUILD_MODEL }
if (-not $OpenCodeReasonModel) { $OpenCodeReasonModel = $env:AGENT_WORKFLOW_OPENCODE_REASON_MODEL }
if (-not $OpenCodeReviewModel) { $OpenCodeReviewModel = $env:AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL }
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

function Get-Profile([string]$Platform) {
    if ($InstallProfile) { return $InstallProfile }
    if ($Platform -eq 'cursor') { return 'lean' }
    return 'balanced'
}

function New-InstallStage([string]$Binding, [string]$Platform, [string]$InstallProfile, [string[]]$Models) {
    $stage = Join-Path ([IO.Path]::GetTempPath()) "agent-workflow-$([guid]::NewGuid().ToString('N'))"
    $python = Resolve-Python
    $build = if ($Models[0]) { $Models[0] } else { '-' }
    $reason = if ($Models[1]) { $Models[1] } else { '-' }
    $review = if ($Models[2]) { $Models[2] } else { '-' }
    & $python (Join-Path $RepoRoot 'tools\prepare_install.py') $stage $Binding $Platform $InstallProfile $build $reason $review | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
        throw "Model binding validation failed. Nothing was installed."
    }
    return $stage
}

function Test-PolicyArtifactOwnership([string]$State, [string]$Adapter, [string]$Skills, [bool]$Spine) {
    if (-not (Test-Path -LiteralPath $State)) { return }
    $python = Resolve-Python
    $verifyArgs = @((Join-Path $RepoRoot 'tools\verify_install_state.py'), '--state', $State, '--adapter', $Adapter, '--skills', $Skills)
    if ($Spine) { $verifyArgs += '--spine' }
    & $python @verifyArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Generated policy drift detected. Nothing was installed." }
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

function Test-OpenCodeInstallOwnership {
    $state = Join-Path $OpenCodeBase 'agent-workflow-skills\install-state.json'
    $binding = Join-Path $OpenCodeBase 'agent-workflow-skills\model-routing.jsonc'
    if ((Test-Path $binding) -and -not (Test-Path $state)) { throw "Model binding exists without bundle ownership: $binding. Nothing was installed." }
    Test-SkillOwnership (Join-Path $OpenCodeBase 'skills')
}

function Test-SkillOwnership([string]$DestSkillsDir) {
    Get-ChildItem -Directory -LiteralPath (Join-Path $RepoRoot 'policy-v3\generated\skills') | ForEach-Object {
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
    $binding = Join-Path $Stage 'model-routing.jsonc'
    if (Test-Path $binding) {
        Copy-Item -Force $binding (Join-Path $Dir 'model-routing.jsonc')
    }
    foreach ($name in @('dispatch_resolver.py', 'validate_jsonc.py')) {
        $source = Join-Path $Stage $name
        if (Test-Path $source) { Copy-Item -Force $source (Join-Path $Dir $name) }
    }
    Copy-Item -Force (Join-Path $Stage 'install-state.json') (Join-Path $Dir 'install-state.json')
}

function Get-SpineBody([string]$Source) {
    # Strip optional Cursor frontmatter before inserting the OpenCode marker block.
    $raw = Read-Utf8 $Source
    $body = [regex]::Replace($raw, '^---\r?\n.*?\r?\n---\r?\n', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    return $body.Trim()
}

function Set-SpineBlock([string]$File, [string]$Source) {
    # Idempotently place the spine between markers: replace the block if markers exist, else append.
    $body = Get-SpineBody $Source
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

function Test-OpenCodeModelMigration([string]$Binding) {
    $python = Resolve-Python
    $migration = @(
        (Join-Path $RepoRoot 'tools\migrate_opencode_models.py'),
        '--config-dir', $OpenCodeBase,
        '--binding', $Binding,
        '--audit', (Join-Path $OpenCodeBase 'agent-workflow-skills\opencode-model-migration.json'),
        '--stage', $script:OpenCodeStage,
        '--check'
    )
    if ($OpenCodeModelConfig) { $migration += @('--opencode-model-config', $OpenCodeModelConfig) }
    & $python @migration | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'OpenCode model config migration preflight failed. Nothing was installed.'
    }
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
    $python = Resolve-Python
    $migration = @(
        (Join-Path $RepoRoot 'tools\migrate_opencode_models.py'),
        '--config-dir', $base,
        '--binding', (Join-Path $script:OpenCodeStage 'model-routing.jsonc'),
        '--audit', (Join-Path $base 'agent-workflow-skills\opencode-model-migration.json'),
        '--stage', $script:OpenCodeStage
    )
    if ($OpenCodeModelConfig) { $migration += @('--opencode-model-config', $OpenCodeModelConfig) }
    & $python @migration | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'OpenCode installation transaction failed; OpenCode config changes were rolled back.' }
    $summary.Add("opencode: skills -> $(Join-Path $base 'skills')")
    $summary.Add("opencode: spine injected -> $(Join-Path $base 'AGENTS.md') (marker block)")
    $summary.Add("opencode: model binding -> $base\agent-workflow-skills\model-routing.jsonc")
    $summary.Add("opencode: role models -> selected JSON/JSONC config (audited migration)")
}

function Install-Claude {
    $base = Join-Path $env:USERPROFILE '.claude'
    $skillsDir = Join-Path $base 'skills'
    Copy-Skills $skillsDir (Join-Path $script:ClaudeStage 'skills')
    $summary.Add("claude: skills -> $skillsDir")
    $claudeMd = Join-Path $base 'CLAUDE.md'
    Set-SpineBlock $claudeMd (Join-Path $script:ClaudeStage 'workflow-gate.mdc')
    Set-BundleState (Join-Path $base 'agent-workflow-skills') $script:ClaudeStage
    $summary.Add("claude: generated v3 spine -> $claudeMd (marker block)")
    $summary.Add("claude: ownership state -> $base\agent-workflow-skills\install-state.json")
}

function New-TargetSnapshot([string]$Root, [string]$Path) {
    $id = [guid]::NewGuid().ToString('N')
    $payload = Join-Path $Root $id
    $exists = Test-Path -LiteralPath $Path
    if ($exists) {
        Copy-Item -Recurse -Force -LiteralPath $Path -Destination $payload
    }
    return [pscustomobject]@{ Path = $Path; Payload = $payload; Exists = $exists }
}

function Restore-TargetSnapshot($Snapshot) {
    if (Test-Path -LiteralPath $Snapshot.Path) {
        Remove-Item -Recurse -Force -LiteralPath $Snapshot.Path
    }
    if ($Snapshot.Exists) {
        $parent = Split-Path -Parent $Snapshot.Path
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -Recurse -Force -LiteralPath $Snapshot.Payload -Destination $Snapshot.Path
    }
}

function Test-InjectedPlatformFailure([string]$Platform) {
    if ($env:AGENT_WORKFLOW_TEST_FAIL_PLATFORM -eq $Platform) {
        throw "Injected all-platform failure after $Platform installation."
    }
}

if (($Tool -eq 'cursor' -or $Tool -eq 'all') -and -not $Project) {
    throw '-Project is required for Cursor installation so the forced spine is installed automatically. Nothing was installed.'
}
if ($Tool -eq 'opencode' -or $Tool -eq 'all') {
    if (-not $MigrateOpenCodeModelConfig) {
        throw 'OpenCode JSON/JSONC model migration requires -MigrateOpenCodeModelConfig. Nothing was installed.'
    }
    Test-OpenCodeInstallOwnership
    $opencodeSpine = Join-Path $OpenCodeBase 'AGENTS.md'
    $opencodeState = Join-Path $OpenCodeBase 'agent-workflow-skills\install-state.json'
    Test-SpineMarkerIntegrity $opencodeSpine
    Test-PolicyArtifactOwnership $opencodeState $opencodeSpine (Join-Path $OpenCodeBase 'skills') $true
    $models = @($OpenCodeBuildModel, $OpenCodeReasonModel, $OpenCodeReviewModel)
    $script:OpenCodeStage = New-InstallStage (Join-Path $OpenCodeBase 'agent-workflow-skills\model-routing.jsonc') 'opencode' (Get-Profile 'opencode') $models
    Test-OpenCodeModelMigration (Join-Path $script:OpenCodeStage 'model-routing.jsonc')
}
if ($Tool -eq 'cursor' -or $Tool -eq 'all') {
    $cursorState = Join-Path $Project '.cursor\agent-workflow-skills\install-state.json'
    $cursorBinding = Join-Path $Project '.cursor\agent-workflow-skills\model-routing.jsonc'
    if ((Test-Path $cursorBinding) -and -not (Test-Path $cursorState)) { throw "Cursor model binding exists without bundle ownership. Nothing was installed." }
    Test-SkillOwnership (Join-Path $env:USERPROFILE '.cursor\skills')
    Test-PolicyArtifactOwnership $cursorState (Join-Path $Project '.cursor\rules\workflow-gate.mdc') (Join-Path $env:USERPROFILE '.cursor\skills') $false
    foreach ($name in @('workflow-gate.mdc', 'model-routing.mdc')) {
        $rule = Join-Path $Project ".cursor\rules\$name"
        if ((Test-Path $rule) -and -not (Read-Utf8 $rule).Contains('Managed by agent-workflow-skills')) {
            throw "Cursor rule already exists and is not bundle-owned: $rule. Nothing was installed."
        }
    }
    $models = @($CursorBuildModel, $CursorReasonModel, $CursorReviewModel)
    $script:CursorStage = New-InstallStage $cursorBinding 'cursor' (Get-Profile 'cursor') $models
}
if ($Tool -eq 'claude' -or $Tool -eq 'all') {
    $claudeBase = Join-Path $env:USERPROFILE '.claude'
    $claudeState = Join-Path $claudeBase 'agent-workflow-skills\install-state.json'
    Test-SpineMarkerIntegrity (Join-Path $claudeBase 'CLAUDE.md')
    Test-SkillOwnership (Join-Path $claudeBase 'skills')
    Test-PolicyArtifactOwnership $claudeState (Join-Path $claudeBase 'CLAUDE.md') (Join-Path $claudeBase 'skills') $true
    $script:ClaudeStage = New-InstallStage (Join-Path $claudeBase 'agent-workflow-skills\model-routing.jsonc') 'claude' (Get-Profile 'claude') @()
}

try {
    switch ($Tool) {
        'cursor' { Install-Cursor }
        'opencode' { Install-OpenCode }
        'claude' { Install-Claude }
        'all' {
            $snapshotRoot = Join-Path ([IO.Path]::GetTempPath()) "agent-workflow-all-$([guid]::NewGuid().ToString('N'))"
            New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
            $snapshots = @(
                (New-TargetSnapshot $snapshotRoot (Join-Path $env:USERPROFILE '.cursor')),
                (New-TargetSnapshot $snapshotRoot (Join-Path $Project '.cursor')),
                (New-TargetSnapshot $snapshotRoot $OpenCodeBase),
                (New-TargetSnapshot $snapshotRoot (Join-Path $env:USERPROFILE '.claude'))
            )
            try {
                Install-Cursor
                Test-InjectedPlatformFailure 'cursor'
                Install-OpenCode
                Test-InjectedPlatformFailure 'opencode'
                Install-Claude
                Test-InjectedPlatformFailure 'claude'
            }
            catch {
                $restore = [object[]]$snapshots
                [array]::Reverse($restore)
                foreach ($snapshot in $restore) {
                    Restore-TargetSnapshot $snapshot
                }
                throw
            }
            finally {
                Remove-Item -Recurse -Force -LiteralPath $snapshotRoot -ErrorAction SilentlyContinue
            }
        }
    }
}
finally {
    foreach ($stage in @($script:CursorStage, $script:OpenCodeStage, $script:ClaudeStage)) {
        if ($stage -and (Test-Path $stage)) { Remove-Item -Recurse -Force $stage }
    }
}

Write-Host ""
Write-Host "=== agent-workflow-skills install summary (tool=$Tool) ===" -ForegroundColor Cyan
foreach ($line in $summary) { Write-Host "  - $line" }
if ($Tool -eq 'opencode' -or $Tool -eq 'all') { Write-Host "Restart OpenCode to load the installed files." }
Write-Host "Done."
