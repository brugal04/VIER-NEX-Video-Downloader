@echo off
setlocal
cd /d "%~dp0"
title VIER-NEX - Actualizar motor de interfaz

echo ============================================================
echo   VIER-NEX VIDEO DOWNLOADER - MOTOR DE INTERFAZ
echo ============================================================
echo.
echo Actualizando CustomTkinter a la rama 6.x...
python -m pip install --upgrade "customtkinter>=6.0.0,<7"
if errorlevel 1 (
  echo.
  echo ERROR actualizando CustomTkinter.
  pause
  exit /b 1
)

echo.
python -c "import customtkinter as ctk; print('CustomTkinter instalado:', ctk.__version__)"
echo.
echo Listo. Ahora abre ABRIR_VIER_NEX.vbs
pause
