@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
if not "%~1"=="" goto explicit
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto python
goto missing

:explicit
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto missing
"%~1" "%~dp0server.py" --bind 127.0.0.1 --port 38400
goto stopped

:launcher
py -3 "%~dp0server.py" --bind 127.0.0.1 --port 38400
goto stopped

:python
python "%~dp0server.py" --bind 127.0.0.1 --port 38400
goto stopped

:missing
echo Python 3.10 or newer is required. No software or settings were changed.
echo Ask the developer to use your existing Python, or install it from python.org.
pause
exit /b 1

:stopped
set "relay_exit=%errorlevel%"
echo.
echo Moonshine relay stopped. Close this window, or press a key to finish.
pause
exit /b %relay_exit%
