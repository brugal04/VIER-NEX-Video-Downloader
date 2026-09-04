@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title VIER-NEX Video Downloader v0.1.0 - Crear Instalador

echo ============================================================
echo      VIER-NEX VIDEO DOWNLOADER v0.1.0 - BUILD RELEASE
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no esta en PATH.
  pause
  exit /b 1
)

echo [1/5] Instalando / actualizando dependencias...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/5] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release
mkdir release >nul 2>&1

echo.
echo [3/5] Creando EXE de Windows...
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
if errorlevel 1 goto :error

echo.
echo [4/5] Buscando Inno Setup...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup 6 no esta instalado y winget no esta disponible.
    echo Instala Inno Setup 6 y vuelve a ejecutar este BAT.
    pause
    exit /b 1
  )

  echo Inno Setup no esta instalado. Instalando con winget...
  winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 goto :error

  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if not defined ISCC (
  echo ERROR: No pude localizar ISCC.exe.
  pause
  exit /b 1
)

echo.
echo Compilando instalador...
"%ISCC%" "installer\VIERNEX_Video_Downloader.iss"
if errorlevel 1 goto :error

echo.
echo [5/5] Generando SHA-256 para GitHub Release...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$f = Get-ChildItem '.\release\VIER-NEX-Video-Downloader-Setup-v0.1.0.exe';" ^
  "$h = Get-FileHash $f.FullName -Algorithm SHA256;" ^
  "'SHA256  ' + $h.Hash + '  ' + $f.Name | Set-Content '.\release\SHA256SUMS.txt' -Encoding ASCII"

echo.
echo ============================================================
echo BUILD COMPLETADO
echo.
echo Archivos para GitHub Releases:
echo   release\VIER-NEX-Video-Downloader-Setup-v0.1.0.exe
echo   release\SHA256SUMS.txt
echo ============================================================
echo.
start "" "%~dp0release"
pause
exit /b 0

:error
echo.
echo ============================================================
echo ERROR: El build no pudo completarse.
echo ============================================================
pause
exit /b 1
endlocal


