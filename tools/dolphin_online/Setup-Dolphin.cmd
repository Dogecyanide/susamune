@echo off
if "%~1"=="" (
  echo Close Dolphin, then drag its User Folder onto this file.
  echo Find it using Dolphin: File - Open User Folder.
  pause
  exit /b 1
)
py -3 "%~dp0setup_dolphin_data.py" --user "%~1" --data "%~dp0Moonshine data" --dolphin-closed
pause
