$ErrorActionPreference = "Stop"

Write-Host "QIB ATM Manager Android build check" -ForegroundColor Cyan

$androidStudioJbr = "C:\Program Files\Android\Android Studio\jbr"
if (Test-Path $androidStudioJbr) {
    $env:JAVA_HOME = $androidStudioJbr
    $env:Path = "$env:JAVA_HOME\bin;$env:Path"
    Write-Host "Using Android Studio JBR: $env:JAVA_HOME" -ForegroundColor Green
}

$defaultSdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
if (-not $env:ANDROID_HOME -and (Test-Path $defaultSdk)) {
    $env:ANDROID_HOME = $defaultSdk
    $env:ANDROID_SDK_ROOT = $defaultSdk
    Write-Host "Using Android SDK: $env:ANDROID_HOME" -ForegroundColor Green
}

if (Test-Path ".\gradlew.bat") {
    .\gradlew.bat :app:assembleDebug
    exit $LASTEXITCODE
}

$gradle = Get-Command gradle -ErrorAction SilentlyContinue
if ($gradle) {
    gradle :app:assembleDebug
    exit $LASTEXITCODE
}

$gradleVersion = "8.10.2"
$bootstrapDir = Join-Path $PWD ".gradle\bootstrap"
$gradleHome = Join-Path $bootstrapDir "gradle-$gradleVersion"
$gradleBat = Join-Path $gradleHome "bin\gradle.bat"

if (-not (Test-Path $gradleBat)) {
    New-Item -ItemType Directory -Force -Path $bootstrapDir | Out-Null
    $zipPath = Join-Path $bootstrapDir "gradle-$gradleVersion-bin.zip"
    if (-not (Test-Path $zipPath)) {
        $url = "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip"
        Write-Host "Gradle is not in PATH. Downloading Gradle $gradleVersion..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri $url -OutFile $zipPath
    }
    Write-Host "Extracting Gradle $gradleVersion..." -ForegroundColor Yellow
    Expand-Archive -LiteralPath $zipPath -DestinationPath $bootstrapDir -Force
}

& $gradleBat :app:assembleDebug
exit $LASTEXITCODE
