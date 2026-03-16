@echo off
REM =============================================================================
REM build_windows.bat — Build Image Splicer as a Windows .exe
REM
REM Usage:
REM   build_windows.bat
REM
REM Output:
REM   dist\windows\Image Splicer\Image Splicer.exe   (folder with dependencies)
REM   dist\windows\Image Splicer.exe                  (single-file build)
REM
REM Requirements:
REM   pip install pyinstaller
REM =============================================================================

setlocal enabledelayedexpansion

set APP_NAME=Image Splicer
set SCRIPT_DIR=%~dp0
set DIST_DIR=%SCRIPT_DIR%dist\windows
set WORK_DIR=%SCRIPT_DIR%build\windows

echo =^> Building %APP_NAME% for Windows

REM ── Check PyInstaller ────────────────────────────────────────────────────────
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo     Installing PyInstaller...
    pip install pyinstaller -q
)

REM ── Icon arg ────────────────────────────────────────────────────────────────
set ICON_ARG=
if exist "%SCRIPT_DIR%icon.ico" (
    set ICON_ARG=--icon "%SCRIPT_DIR%icon.ico"
) else if exist "%SCRIPT_DIR%icon.png" (
    set ICON_ARG=--icon "%SCRIPT_DIR%icon.png"
)

REM ── Data files ───────────────────────────────────────────────────────────────
set ADD_DATA=--add-data "%SCRIPT_DIR%style.qss;."
if exist "%SCRIPT_DIR%icons" (
    set ADD_DATA=!ADD_DATA! --add-data "%SCRIPT_DIR%icons;icons"
)
if exist "%SCRIPT_DIR%image_splicer\themes" (
    set ADD_DATA=!ADD_DATA! --add-data "%SCRIPT_DIR%image_splicer\themes;themes"
)

REM ── Build — onedir (recommended: faster startup, easier to update) ───────────
echo =^> Building onedir version...
cd /d "%SCRIPT_DIR%"

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name "%APP_NAME%" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    --specpath "%WORK_DIR%" ^
    %ICON_ARG% ^
    %ADD_DATA% ^
    --hidden-import PyQt6.sip ^
    --collect-all PyQt6 ^
    --paths "%SCRIPT_DIR%image_splicer" ^
    "%SCRIPT_DIR%main.py"

if errorlevel 1 (
    echo =^> Build failed!
    exit /b 1
)

echo.
echo =^> Done!  Output folder:
echo     %DIST_DIR%\%APP_NAME%\
echo.
echo     Run:  "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe"
echo     Distribute:  zip the entire "%APP_NAME%" folder
echo.
