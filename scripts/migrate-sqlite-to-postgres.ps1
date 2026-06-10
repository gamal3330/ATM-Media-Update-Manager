param(
  [Parameter(Mandatory = $true)]
  [string]$PostgresUrl,

  [string]$SqliteUrl = "",
  [int]$BatchSize = 1000,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Root "backend"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\migrate-sqlite-to-postgres.py"

if (-not (Test-Path $Python)) {
  throw "Backend virtual environment was not found at $Python"
}

if (-not (Test-Path $Script)) {
  throw "Migration script was not found at $Script"
}

$Arguments = @(
  $Script,
  "--postgres-url", $PostgresUrl,
  "--batch-size", $BatchSize
)

if ($SqliteUrl) {
  $Arguments += @("--sqlite-url", $SqliteUrl)
}

if ($Force) {
  $Arguments += "--force"
}

Set-Location -LiteralPath $Root
& $Python @Arguments
