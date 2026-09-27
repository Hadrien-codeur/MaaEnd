[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TargetSha,
    [string]$CandidateRoot = '',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'stage_update.py'), '--target', $TargetSha)
if ($CandidateRoot) {
    $arguments += @('--candidate', $CandidateRoot)
}
& $Python @arguments
if ($LASTEXITCODE -ne 0) {
    throw 'Upstream staging failed. Any created candidate is retained for diagnosis.'
}
Write-Host 'Candidate merged but not committed, built, validated or activated. See .cache/upstream-update.json.'
