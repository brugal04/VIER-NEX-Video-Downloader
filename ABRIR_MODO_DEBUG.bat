@echo off
setlocal
cd /d "%~dp0"
title VIER-NEX Video Downloader v4 - DEBUG
python "VIERNEX_Video_Downloader.py"
if errorlevel 1 (
  echo.
  echo Hubo un error. Revisa:
  echo %LOCALAPPDATA%\VIER-NEX Video Downloader\startup_error.txt
  pause
)
endlocal

