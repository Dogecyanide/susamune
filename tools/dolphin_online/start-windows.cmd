@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
if not "%~1"=="" goto explicit
py -3 -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys,struct; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python
goto missing
:explicit
"%~1" "%~dp0bridge.py"
goto stopped
:launcher
py -3 "%~dp0bridge.py"
goto stopped
:python
python "%~dp0bridge.py"
goto stopped
:missing
echo 64-bit Python 3.10 or newer is required. No settings were changed.
pause
exit /b 1
:stopped
set "bridge_exit=%errorlevel%"
echo.
echo Moonshine Dolphin companion stopped.
pause
exit /b %bridge_exit%
