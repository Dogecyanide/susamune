@echo off
setlocal
if "%~1"=="" (
  echo Drag your clean Sunshine ISO onto this file.
  pause
  exit /b 1
)
py -3 -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python
echo 64-bit Python 3.10 or newer is required.
pause
exit /b 1
:launcher
py -3 "%~dp0apply_patch.py" "%~1"
goto stopped
:python
python "%~dp0apply_patch.py" "%~1"
:stopped
set "patch_exit=%errorlevel%"
pause
exit /b %patch_exit%
