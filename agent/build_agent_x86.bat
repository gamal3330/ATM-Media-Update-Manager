@echo off
setlocal
cd /d "%~dp0"

set "REQUIRE_PYTHON_ARCH=32"

if defined PYTHON_CMD (
  call :check_python
  if not errorlevel 1 goto build
)

where py >nul 2>nul
if %errorlevel%==0 (
  for %%V in (3.14-32 3.13-32 3.12-32 3.11-32) do (
    set PYTHON_CMD=py -%%V
    call :check_python
    if not errorlevel 1 goto build
  )
)

if exist "%LocalAppData%\Programs\Python\Python314-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python314-32\python.exe"
  call :check_python
  if not errorlevel 1 goto build
)

if exist "%LocalAppData%\Programs\Python\Python313-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python313-32\python.exe"
  call :check_python
  if not errorlevel 1 goto build
)

if exist "%LocalAppData%\Programs\Python\Python312-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python312-32\python.exe"
  call :check_python
  if not errorlevel 1 goto build
)

if exist "%LocalAppData%\Programs\Python\Python311-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python311-32\python.exe"
  call :check_python
  if not errorlevel 1 goto build
)

echo.
echo ERROR: 32-bit Python was not found on this build machine.
echo Install Python 3.12 32-bit or run:
echo   py install 3.12-32
echo Then run:
echo   build_agent_x86.bat
echo.
exit /b 1

:build
echo Building 32-bit ATM Agent with: %PYTHON_CMD%
call build_agent.bat
exit /b %ERRORLEVEL%

:check_python
set "PY_ARCH="
set "PY_CHECK_FILE=%TEMP%\atm_agent_python_x86_check_%RANDOM%.txt"
if exist "%PY_CHECK_FILE%" del /f /q "%PY_CHECK_FILE%" >nul 2>nul
%PYTHON_CMD% -c "import platform; print(platform.architecture()[0])" > "%PY_CHECK_FILE%" 2>nul
if errorlevel 1 goto check_python_failed
if not exist "%PY_CHECK_FILE%" goto check_python_failed
set /p PY_ARCH=<"%PY_CHECK_FILE%"
del /f /q "%PY_CHECK_FILE%" >nul 2>nul
if "%PY_ARCH%"=="32bit" exit /b 0

:check_python_failed
if exist "%PY_CHECK_FILE%" del /f /q "%PY_CHECK_FILE%" >nul 2>nul
exit /b 1
