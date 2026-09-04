@echo off
setlocal
cd /d "%~dp0"
title VIER-NEX Video Downloader v4 - Instalacion

echo ============================================================
echo      VIER-NEX VIDEO DOWNLOADER v4 - PRIMERA INSTALACION
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no esta en PATH.
  echo Instala Python y marca "Add Python to PATH".
  pause
  exit /b 1
)

echo Instalando / verificando componentes...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR instalando componentes.
  pause
  exit /b 1
)

echo.
echo Componentes listos.
echo A partir de ahora puedes abrir la app SIN consola usando:
echo ABRIR_VIER_NEX.vbs
echo.
start "" wscript.exe "%~dp0ABRIR_VIER_NEX.vbs"
pause
endlocal
