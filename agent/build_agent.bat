@echo off
setlocal
cd /d "%~dp0"

if defined PYTHON_CMD (
  %PYTHON_CMD% --version >nul 2>nul
  if not errorlevel 1 goto python_found
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 (
    set PYTHON_CMD=py -3
    goto python_found
  )
)

where python >nul 2>nul
if %errorlevel%==0 (
  python --version >nul 2>nul
  if not errorlevel 1 (
    set PYTHON_CMD=python
    goto python_found
  )
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python312\python.exe"
  goto python_found
)

if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python311\python.exe"
  goto python_found
)

if exist "C:\Program Files\Python312\python.exe" (
  set PYTHON_CMD="C:\Program Files\Python312\python.exe"
  goto python_found
)

if exist "C:\Program Files\Python311\python.exe" (
  set PYTHON_CMD="C:\Program Files\Python311\python.exe"
  goto python_found
)

echo.
echo ERROR: Python was not found on this build machine.
echo If Python is already installed, close this window and open a new Command Prompt.
echo Also disable Windows App Execution Aliases for python.exe and python3.exe if they point to Microsoft Store.
echo You can force a path like:
echo   set PYTHON_CMD=C:\Users\YOUR_USER\AppData\Local\Programs\Python\Python312\python.exe
echo   build_agent.bat
echo The ATM itself does not need Python after atm-agent.exe is built.
echo.
exit /b 1

:python_found
echo Using Python command: %PYTHON_CMD%

%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 exit /b 1
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
%PYTHON_CMD% -m pip install pyinstaller pywin32
if errorlevel 1 exit /b 1

echo.
echo Source agent version:
%PYTHON_CMD% atm_agent.py version
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist\atm-agent.exe del /f /q dist\atm-agent.exe
if exist atm-agent.spec del /f /q atm-agent.spec

%PYTHON_CMD% -m PyInstaller ^
  --clean ^
  --onefile ^
  --name atm-agent ^
  --paths "%CD%" ^
  --hidden-import api_client ^
  --hidden-import backup_manager ^
  --hidden-import cash_monitoring_module ^
  --hidden-import checksum ^
  --hidden-import config_manager ^
  --hidden-import logger ^
  --hidden-import media_update_module ^
  --hidden-import module_runner ^
  --hidden-import network_probe ^
  --hidden-import path_policy ^
  --hidden-import safe_zip ^
  --hidden-import service ^
  --hidden-import update_manager ^
  --hidden-import win32timezone ^
  --hidden-import xfs_cdm_diagnostics ^
  --hidden-import xfs_cdm_reader ^
  atm_agent.py
if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\atm-agent.exe
