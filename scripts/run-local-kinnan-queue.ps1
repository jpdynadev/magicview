[CmdletBinding()]
param(
  [ValidateRange(1, 100)]
  [int]$MaxShards = 1,
  [ValidateRange(60, 3600)]
  [int]$LeaseSeconds = 300,
  [string]$Python = "python",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$required = @(
  "NEON_DATA_API",
  "NEON_DATA_API_TOKEN",
  "MANABREW_REF",
  "MANABREW_HARNESS_JAR",
  "MANABREW_FORGE_HOME"
)
if (-not $DryRun) {
  $missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
  if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
  }
  if (-not (Test-Path -LiteralPath $env:MANABREW_HARNESS_JAR -PathType Leaf)) {
    throw "MANABREW_HARNESS_JAR does not exist: $env:MANABREW_HARNESS_JAR"
  }
  if (-not (Test-Path -LiteralPath $env:MANABREW_FORGE_HOME -PathType Container)) {
    throw "MANABREW_FORGE_HOME does not exist: $env:MANABREW_FORGE_HOME"
  }
}

$runnerArguments = @(
  (Join-Path $repoRoot "engine-tests\local_queue_runner.py"),
  "--max-shards", $MaxShards,
  "--lease-seconds", $LeaseSeconds
)
if ($DryRun) { $runnerArguments += "--dry-run" }
& $Python @runnerArguments
if ($LASTEXITCODE -ne 0) {
  throw "Local Kinnan queue runner failed with exit code $LASTEXITCODE"
}
