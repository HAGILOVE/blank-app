@echo off
chcp 65001 >nul
rem WARPZIP Windows build - double-click this file.
cd /d "%~dp0\.."
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python 3.10+ was not found. Install it from https://www.python.org/downloads/ ^(check "Add python.exe to PATH"^) and run this again.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" ( echo. & echo [!] Build failed ^(exit code %RC%^). ) else ( echo. & echo Build finished: see the dist folder. )
pause
exit /b %RC%
