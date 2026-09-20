[CmdletBinding()]
param(
    [string]$UpstreamRef = 'origin/v2',
    [string]$CandidateRoot = '',
    [switch]$CleanupCandidate
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location $repositoryRoot

function Invoke-Git([string[]]$Arguments) {
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Get-GitValue([string[]]$Arguments) {
    $value = (& git @Arguments).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw "git $($Arguments -join ' ') returned no value"
    }
    return $value
}

$status = @(git status --porcelain=v1)
$unexpected = @($status | Where-Object { $_ -notmatch '^\?\? outputs([\\/]|$)' })
if ($unexpected.Count -gt 0) {
    $details = $unexpected -join [Environment]::NewLine
    throw "Worktree has untracked or modified files outside outputs; clean it before updating:`n$details"
}

Invoke-Git @('fetch', 'origin', 'v2', '--prune')
$upstreamSha = Get-GitValue @('rev-parse', $UpstreamRef)
$shortSha = $upstreamSha.Substring(0, 12)
if ([string]::IsNullOrWhiteSpace($CandidateRoot)) {
    $CandidateRoot = Join-Path $repositoryRoot ".cache\fixed-delivery-update-$shortSha"
}
$CandidateRoot = [IO.Path]::GetFullPath($CandidateRoot)
if (Test-Path -LiteralPath $CandidateRoot) {
    throw "Candidate path already exists; refusing to overwrite: $CandidateRoot"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CandidateRoot) | Out-Null
Invoke-Git @('worktree', 'add', '--detach', $CandidateRoot, $upstreamSha)

try {
    $candidateFixedDir = Join-Path $CandidateRoot 'tools\fixed-delivery'
    New-Item -ItemType Directory -Force -Path $candidateFixedDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compatibility.json') -Destination (Join-Path $candidateFixedDir 'compatibility.json')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check_compatibility.py') -Destination (Join-Path $candidateFixedDir 'check_compatibility.py')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'apply_route_overlay.mjs') -Destination (Join-Path $candidateFixedDir 'apply_route_overlay.mjs')
    $fixedRoutesTarget = Join-Path $CandidateRoot 'assets\data\MapNavigator\fixed_zipline_routes.json'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $fixedRoutesTarget) | Out-Null
    Copy-Item -LiteralPath (Join-Path $repositoryRoot 'assets\data\MapNavigator\fixed_zipline_routes.json') -Destination $fixedRoutesTarget

    node (Join-Path $candidateFixedDir 'apply_route_overlay.mjs') `
        --source (Join-Path $repositoryRoot 'tools\pipeline-generate\AutoDelivery\routes.json') `
        --target (Join-Path $CandidateRoot 'tools\pipeline-generate\AutoDelivery\routes.json') `
        --fixed-routes $fixedRoutesTarget

    $python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $python = 'python'
    }
    & $python (Join-Path $repositoryRoot 'tools\fixed-delivery\check_compatibility.py') `
        --root $CandidateRoot `
        --manifest (Join-Path $candidateFixedDir 'compatibility.json')
    $checkExit = $LASTEXITCODE
    if ($checkExit -ne 0) {
        throw "Upstream candidate failed the fixed-delivery compatibility contract (exit $checkExit). Candidate retained for adaptation: $CandidateRoot"
    }

    Write-Host "Upstream candidate passed the fixed-delivery compatibility gate: $upstreamSha" -ForegroundColor Green
    Write-Host "Candidate path: $CandidateRoot"
    Write-Host "This script stages and gates a candidate; build, runtime regression, and activation remain separate steps."
}
catch {
    Write-Error $_
    Write-Host "Current checkout was not modified. Candidate path: $CandidateRoot" -ForegroundColor Yellow
    exit 1
}
finally {
    if ($CleanupCandidate -and $CandidateRoot -and (Test-Path -LiteralPath $CandidateRoot) -and $LASTEXITCODE -eq 0) {
        Invoke-Git @('worktree', 'remove', '--force', $CandidateRoot)
    }
}
