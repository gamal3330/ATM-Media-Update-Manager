param(
  [string]$HostAddress = "0.0.0.0",
  [int]$BackendPort = 8001,
  [int]$FrontendPort = 5175,
  [int]$WhatsappPort = 3020,
  [string]$WhatsappHostName = "127.0.0.1",
  [string]$WhatsappToken = "",
  [switch]$NoWhatsappGateway,
  [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

function Quote-PowerShellPath([string]$Value) {
  return "'" + ($Value -replace "'", "''") + "'"
}

function Require-Command([string]$Name, [string]$InstallHint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name was not found. $InstallHint"
  }
}

function Resolve-PythonCommand {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @("py", "-3")
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @("python")
  }
  throw "Python was not found. Install Python 3.11+ on the server."
}

function Invoke-Python([string[]]$PythonCommand, [string[]]$Arguments) {
  $Executable = $PythonCommand[0]
  $BaseArguments = @()
  if ($PythonCommand.Length -gt 1) {
    $BaseArguments = $PythonCommand[1..($PythonCommand.Length - 1)]
  }
  & $Executable @BaseArguments @Arguments
}

function File-Is-NewerThanMarker([string]$FilePath, [string]$MarkerPath) {
  if (-not (Test-Path $MarkerPath)) {
    return $true
  }
  if (-not (Test-Path $FilePath)) {
    return $false
  }
  return (Get-Item $FilePath).LastWriteTimeUtc -gt (Get-Item $MarkerPath).LastWriteTimeUtc
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$WhatsappGatewayDir = Join-Path $Root "whatsapp-gateway"
$RootEnv = Join-Path $Root ".env"
$ExampleEnv = Join-Path $Root ".env.example"
$FrontendEnv = Join-Path $FrontendDir ".env"

Set-Location -LiteralPath $Root

if (-not (Test-Path $RootEnv)) {
  if (-not (Test-Path $ExampleEnv)) {
    throw ".env was not found and .env.example is missing."
  }
  Copy-Item $ExampleEnv $RootEnv
  Write-Host "Created .env from .env.example. Edit it before production use." -ForegroundColor Yellow
}

Copy-Item $RootEnv $FrontendEnv -Force

if (-not $NoInstall) {
  $PythonCommand = Resolve-PythonCommand
  $VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
  $Requirements = Join-Path $BackendDir "requirements.txt"
  $BackendMarker = Join-Path $BackendDir ".venv\.requirements-installed"

  if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating backend virtual environment..." -ForegroundColor Cyan
    Invoke-Python $PythonCommand @("-m", "venv", (Join-Path $BackendDir ".venv"))
  }

  if (File-Is-NewerThanMarker $Requirements $BackendMarker) {
    Write-Host "Installing backend requirements..." -ForegroundColor Cyan
    & $VenvPython -m pip install -r $Requirements
    New-Item -ItemType File -Force -Path $BackendMarker | Out-Null
  }

  Require-Command "npm" "Install Node.js LTS on the server."
  $NodeModules = Join-Path $FrontendDir "node_modules"
  $NpmMarker = Join-Path $NodeModules ".install-marker"
  $PackageJson = Join-Path $FrontendDir "package.json"
  $PackageLock = Join-Path $FrontendDir "package-lock.json"
  $NeedsNpmInstall = (
    (-not (Test-Path $NodeModules)) -or
    (File-Is-NewerThanMarker $PackageJson $NpmMarker) -or
    (File-Is-NewerThanMarker $PackageLock $NpmMarker)
  )

  if ($NeedsNpmInstall) {
    Write-Host "Installing frontend packages..." -ForegroundColor Cyan
    Push-Location $FrontendDir
    try {
      npm install
      New-Item -ItemType File -Force -Path $NpmMarker | Out-Null
    } finally {
      Pop-Location
    }
  }

  if (-not $NoWhatsappGateway) {
    if (-not (Test-Path $WhatsappGatewayDir)) {
      throw "WhatsApp gateway directory was not found at $WhatsappGatewayDir."
    }
    $WhatsappNodeModules = Join-Path $WhatsappGatewayDir "node_modules"
    $WhatsappNpmMarker = Join-Path $WhatsappNodeModules ".install-marker"
    $WhatsappPackageJson = Join-Path $WhatsappGatewayDir "package.json"
    $WhatsappPackageLock = Join-Path $WhatsappGatewayDir "package-lock.json"
    $NeedsWhatsappInstall = (
      (-not (Test-Path $WhatsappNodeModules)) -or
      (File-Is-NewerThanMarker $WhatsappPackageJson $WhatsappNpmMarker) -or
      (File-Is-NewerThanMarker $WhatsappPackageLock $WhatsappNpmMarker)
    )

    if ($NeedsWhatsappInstall) {
      Write-Host "Installing WhatsApp gateway packages..." -ForegroundColor Cyan
      Push-Location $WhatsappGatewayDir
      try {
        npm install
        New-Item -ItemType File -Force -Path $WhatsappNpmMarker | Out-Null
      } finally {
        Pop-Location
      }
    }
  }
}

$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  throw "Backend virtual environment was not found. Run without -NoInstall first."
}

Require-Command "npm" "Install Node.js LTS on the server."

$BackendDirQ = Quote-PowerShellPath $BackendDir
$FrontendDirQ = Quote-PowerShellPath $FrontendDir
$WhatsappGatewayDirQ = Quote-PowerShellPath $WhatsappGatewayDir
$VenvPythonQ = Quote-PowerShellPath $VenvPython

$BackendCommand = "Set-Location -LiteralPath $BackendDirQ; & $VenvPythonQ -m uvicorn app.main:app --host $HostAddress --port $BackendPort"
$FrontendCommand = "Set-Location -LiteralPath $FrontendDirQ; npm run dev -- --host $HostAddress --port $FrontendPort"
$WhatsappTokenArgument = if ($WhatsappToken) { " -Token " + (Quote-PowerShellPath $WhatsappToken) } else { "" }
$WhatsappCommand = "Set-Location -LiteralPath $WhatsappGatewayDirQ; .\start-whatsapp-gateway.ps1 -HostName $WhatsappHostName -Port $WhatsappPort$WhatsappTokenArgument"

Write-Host "Starting QIB ATM Manager..." -ForegroundColor Green
Write-Host "Backend:  http://localhost:$BackendPort/docs"
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Network frontend example: http://SERVER-IP:$FrontendPort"
if (-not $NoWhatsappGateway) {
  Write-Host "WhatsApp gateway: http://$WhatsappHostName`:$WhatsappPort"
}

Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $BackendCommand) -WindowStyle Normal
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $FrontendCommand) -WindowStyle Normal
if (-not $NoWhatsappGateway) {
  Start-Sleep -Seconds 2
  Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $WhatsappCommand) -WindowStyle Normal
}

if ($NoWhatsappGateway) {
  Write-Host "Backend and frontend were started in separate PowerShell windows." -ForegroundColor Green
} else {
  Write-Host "Backend, frontend, and WhatsApp gateway were started in separate PowerShell windows." -ForegroundColor Green
}
