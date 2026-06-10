param(
  [Parameter(Mandatory = $true)]
  [string]$SuperPassword,

  [string]$AppPassword = "",
  [string]$DbName = "qib_atm_manager",
  [string]$DbUser = "qib_atm_user",
  [int]$Port = 5432,
  [string]$InstallerPath = "",
  [switch]$UpdateEnv
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window: Run as Administrator."
  }
}

function Escape-SqlLiteral([string]$Value) {
  return $Value -replace "'", "''"
}

function Set-EnvDatabaseUrl([string]$EnvPath, [string]$DatabaseUrl) {
  $content = Get-Content -LiteralPath $EnvPath -Raw
  $backupPath = "$EnvPath.sqlite-backup-$(Get-Date -Format yyyyMMddHHmmss)"
  Copy-Item -LiteralPath $EnvPath -Destination $backupPath -Force
  if ($content -match "(?m)^DATABASE_URL=") {
    $content = $content -replace "(?m)^DATABASE_URL=.*$", "DATABASE_URL=$DatabaseUrl"
  } else {
    $content = "DATABASE_URL=$DatabaseUrl`r`n$content"
  }
  Set-Content -LiteralPath $EnvPath -Value $content -Encoding UTF8
  Write-Host "Updated $EnvPath and saved backup at $backupPath" -ForegroundColor Green
}

Assert-Administrator

if (-not $AppPassword) {
  $AppPassword = $SuperPassword
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Root "backend"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$EnvPath = Join-Path $Root ".env"
$DefaultInstaller = Join-Path $Root "postgresql-17.10-windows-x64.exe"
$DownloadUrl = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260200"

if (-not $InstallerPath) {
  $InstallerPath = $DefaultInstaller
}

if (-not (Test-Path $InstallerPath)) {
  Write-Host "Downloading PostgreSQL installer..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath
}

$PostgresRoot = "C:\Program Files\PostgreSQL\17"
$Psql = Join-Path $PostgresRoot "bin\psql.exe"
$Createdb = Join-Path $PostgresRoot "bin\createdb.exe"

if (-not (Test-Path $Psql)) {
  Write-Host "Installing PostgreSQL 17..." -ForegroundColor Cyan
  $arguments = @(
    "--mode", "unattended",
    "--unattendedmodeui", "none",
    "--superpassword", $SuperPassword,
    "--serverport", $Port,
    "--servicename", "postgresql-x64-17"
  )
  $process = Start-Process -FilePath $InstallerPath -ArgumentList $arguments -Wait -PassThru
  if ($process.ExitCode -ne 0) {
    throw "PostgreSQL installer failed with exit code $($process.ExitCode)."
  }
}

if (-not (Test-Path $Psql)) {
  throw "psql.exe was not found at $Psql after installation."
}

if (-not (Test-Path $Python)) {
  throw "Backend virtual environment was not found at $Python"
}

Write-Host "Installing backend PostgreSQL dependency..." -ForegroundColor Cyan
& $Python -m pip install -r (Join-Path $BackendDir "requirements.txt")

$env:PGPASSWORD = $SuperPassword
$dbUserSql = Escape-SqlLiteral $DbUser
$appPasswordSql = Escape-SqlLiteral $AppPassword
$dbNameSql = Escape-SqlLiteral $DbName

Write-Host "Creating/updating PostgreSQL role $DbUser..." -ForegroundColor Cyan
$roleSql = "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$dbUserSql') THEN CREATE ROLE $DbUser LOGIN PASSWORD '$appPasswordSql'; ELSE ALTER ROLE $DbUser WITH LOGIN PASSWORD '$appPasswordSql'; END IF; END `$`$;"
& $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -c $roleSql

$dbExists = & $Psql -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$dbNameSql'"
if (-not ($dbExists -match "1")) {
  Write-Host "Creating database $DbName..." -ForegroundColor Cyan
  & $Createdb -h 127.0.0.1 -p $Port -U postgres -O $DbUser $DbName
}

$encodedPassword = [System.Uri]::EscapeDataString($AppPassword)
$databaseUrl = "postgresql+psycopg://$DbUser`:$encodedPassword@127.0.0.1:$Port/$DbName"

Write-Host "Migrating SQLite data to PostgreSQL..." -ForegroundColor Cyan
& (Join-Path $Root "scripts\migrate-sqlite-to-postgres.ps1") -PostgresUrl $databaseUrl

if ($UpdateEnv) {
  Set-EnvDatabaseUrl -EnvPath $EnvPath -DatabaseUrl $databaseUrl
} else {
  Write-Host "Migration complete. Update DATABASE_URL manually or rerun with -UpdateEnv." -ForegroundColor Yellow
  Write-Host "DATABASE_URL=$databaseUrl"
}
