@echo off
setlocal
cd /d "%~dp0"

if defined PYTHON_CMD (
  %PYTHON_CMD% --version >nul 2>nul
  if not errorlevel 1 goto build
)

where py >nul 2>nul
if %errorlevel%==0 (
  for %%V in (3.14-32 3.13-32 3.12-32 3.11-32) do (
    py -%%V --version >nul 2>nul
    if not errorlevel 1 (
      set PYTHON_CMD=py -%%V
      goto build
    )
  )
)

if exist "%LocalAppData%\Programs\Python\Python314-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python314-32\python.exe"
  goto build
)

if exist "%LocalAppData%\Programs\Python\Python313-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python313-32\python.exe"
  goto build
)

if exist "%LocalAppData%\Programs\Python\Python312-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python312-32\python.exe"
  goto build
)

if exist "%LocalAppData%\Programs\Python\Python311-32\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python311-32\python.exe"
  goto build
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
