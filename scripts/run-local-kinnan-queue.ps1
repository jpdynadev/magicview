[CmdletBinding()]
param(
  [ValidateRange(1, 100)]
  [int]$MaxShards = 1,
  [ValidateRange(60, 3600)]
  [int]$LeaseSeconds = 300,
  [string]$Python = "python",
  [switch]$UseWsl,
  [string]$WslDistribution = "Ubuntu",
  [string]$WslHarnessJar = "/root/manabrew-kinnan/forge-harness/target/forge-harness-jar-with-dependencies.jar",
  [string]$WslForgeHome = "/root/manabrew-kinnan/forge/forge-gui",
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
if (-not $DryRun -and -not $UseWsl) {
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
  (Join-Path $repoRoot "engine-tests\local_queue_runner_safe.py"),
  "--max-shards", $MaxShards,
  "--lease-seconds", $LeaseSeconds
)
if ($DryRun) { $runnerArguments += "--dry-run" }

$env:KINNAN_RUNNER_KIND = "local"

if ($UseWsl) {
  if ($repoRoot -notmatch '^([A-Za-z]):\\(.*)$') {
    throw "WSL mode requires a repository on a Windows drive: $repoRoot"
  }
  $drive = $Matches[1].ToLowerInvariant()
  $relativeRoot = $Matches[2].Replace('\', '/')
  $repoRootWsl = "/mnt/$drive/$relativeRoot"
  $wslRunner = "$repoRootWsl/engine-tests/local_queue_runner_safe.py"
  $wslEnvironment = @(
    "NEON_DATA_API=$env:NEON_DATA_API",
    "NEON_DATA_API_TOKEN=$env:NEON_DATA_API_TOKEN",
    "MANABREW_REF=$env:MANABREW_REF",
    "MANABREW_HARNESS_JAR=$WslHarnessJar",
    "MANABREW_FORGE_HOME=$WslForgeHome",
    "KINNAN_RUNNER_KIND=local",
    "KINNAN_REPO_SHA=$env:KINNAN_REPO_SHA"
  )
  if (-not $DryRun) {
    $missing = @("NEON_DATA_API", "NEON_DATA_API_TOKEN", "MANABREW_REF" |
      Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
    if ($missing.Count -gt 0) {
      throw "Missing required environment variables: $($missing -join ', ')"
    }
    & wsl.exe -d $WslDistribution -- test -f $WslHarnessJar
    if ($LASTEXITCODE -ne 0) { throw "WSL harness JAR does not exist: $WslHarnessJar" }
    & wsl.exe -d $WslDistribution -- test -d $WslForgeHome
    if ($LASTEXITCODE -ne 0) { throw "WSL Forge home does not exist: $WslForgeHome" }
  }
  $wslArguments = @("-d", $WslDistribution, "--", "env") + $wslEnvironment +
    @("python3", $wslRunner, "--max-shards", $MaxShards, "--lease-seconds", $LeaseSeconds)
  if ($DryRun) { $wslArguments += "--dry-run" }
  & wsl.exe @wslArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Local Kinnan WSL queue runner failed with exit code $LASTEXITCODE"
  }
  return
}

& $Python @runnerArguments
if ($LASTEXITCODE -ne 0) {
  throw "Local Kinnan queue runner failed with exit code $LASTEXITCODE"
}