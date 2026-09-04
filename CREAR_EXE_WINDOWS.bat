@echo off
setlocal
cd /d "%~dp0"
title Crear VIER-NEX Video Downloader v0.1.0 EXE

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no esta en PATH.
  pause
  exit /b 1
)

echo Instalando dependencias...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo ERROR instalando dependencias.
  pause
  exit /b 1
)

echo.
echo Creando EXE Windows SIN consola...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "VIER-NEX Video Downloader" ^
  --icon "VIERNEX_icon.ico" ^
  --add-data "VIERNEX_icon.ico;." ^
  --add-data "VIERNEX_icon.png;." ^
  --collect-all customtkinter ^
  --collect-all yt_dlp ^
  --collect-all imageio_ffmpeg ^
  --collect-all pystray ^
  --collect-all winotify ^
  --collect-all tkinterdnd2 ^
  --collect-all comtypes ^
  "VIERNEX_Video_Downloader.py"

if errorlevel 1 (
  echo.
  echo ERROR creando el EXE.
  pause
  exit /b 1
)

copy /Y "VIER-NEX_Manual_de_Usuario.pdf" "dist\VIER-NEX_Manual_de_Usuario.pdf" >nul
if errorlevel 1 (
  echo ERROR copiando el Manual de Usuario PDF.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo LISTO
echo %~dp0dist\VIER-NEX Video Downloader.exe
echo ============================================================
start "" "%~dp0dist"
pause
endlocal


