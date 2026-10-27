# Build WARPZIP on Windows:  .\packaging\build_windows.ps1 [-Version 1.0.0] [-SkipTests]
# (or just double-click packaging\build_windows.bat)
param([string]$Version = "1.0.0", [switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$root = (Get-Location).Path

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Magenta }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

# A private virtual environment keeps the build independent of whatever is installed
# globally (e.g. the obsolete 'pathlib' backport breaks PyInstaller).
Step "Python environment (.venv-build)"
if (-not (Test-Path ".venv-build\Scripts\python.exe")) { python -m venv .venv-build; Check "creating venv" }
$py = Join-Path $root ".venv-build\Scripts\python.exe"
& $py -m pip install --disable-pip-version-check -q --upgrade pip; Check "pip upgrade"
& $py -m pip install --disable-pip-version-check -r requirements-dev.txt; Check "installing requirements"

Step "Assets"
& $py tools\make_assets.py; Check "asset generation"

if (-not $SkipTests) {
  Step "Tests"
  $env:QT_QPA_PLATFORM = "offscreen"
  & $py -m pytest -q; Check "tests"
}

Step "PyInstaller"
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path build) { Remove-Item build -Recurse -Force }
& $py -m PyInstaller packaging\warpzip.spec --noconfirm --clean; Check "PyInstaller"

Step "Smoke test of the built CLI"
$wz = Join-Path $root "dist\WarpZip\wz.exe"
if (-not (Test-Path $wz)) { throw "wz.exe was not produced" }
$tmp = Join-Path $env:TEMP "wz-smoke"; New-Item $tmp -ItemType Directory -Force | Out-Null
"hello warpzip" | Set-Content "$tmp\a.txt"
Remove-Item "$tmp\t.7z" -ErrorAction SilentlyContinue
& $wz a "$tmp\t.7z" "$tmp\a.txt" -p secret -q; Check "wz a"
& $wz t "$tmp\t.7z" -p secret -q; Check "wz t"

Step "Installer (Inno Setup)"
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
$isccPath = if ($iscc) { $iscc.Source } else { "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
if (Test-Path $isccPath) {
  $env:WARPZIP_VERSION = $Version
  & $isccPath packaging\installer.iss; Check "Inno Setup"
} else { Write-Warning "Inno Setup 6 not found - installer skipped (https://jrsoftware.org/isinfo.php)" }

Step "Portable zip"
New-Item dist\WarpZip\portable.flag -ItemType File -Force | Out-Null
Compress-Archive -Path dist\WarpZip\* -DestinationPath "dist\WarpZip-$Version-portable.zip" -Force
Remove-Item dist\WarpZip\portable.flag
Write-Host "`nDone -> $root\dist" -ForegroundColor Green
