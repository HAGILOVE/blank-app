# Build WARPZIP on Windows:  .\packaging\build_windows.ps1 [-Version 1.0.0]
param([string]$Version = "1.0.0")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m pip install -r requirements-dev.txt
python tools/make_assets.py
python -m pytest -q
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path build) { Remove-Item build -Recurse -Force }
pyinstaller packaging/warpzip.spec --noconfirm --clean

# smoke test the frozen CLI
$tmp = Join-Path $env:TEMP "wz-smoke"; New-Item $tmp -ItemType Directory -Force | Out-Null
"hello warpzip" | Set-Content "$tmp\a.txt"
& dist\WarpZip\wz.exe a "$tmp\t.7z" "$tmp\a.txt" -p secret -q; if ($LASTEXITCODE) { throw "wz a failed" }
& dist\WarpZip\wz.exe t "$tmp\t.7z" -p secret -q; if ($LASTEXITCODE) { throw "wz t failed" }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) { $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" } else { $iscc = $iscc.Source }
if (Test-Path $iscc) {
  $env:WARPZIP_VERSION = $Version
  & $iscc packaging\installer.iss
} else { Write-Warning "Inno Setup not found - skipped installer" }

# portable zip
New-Item dist\WarpZip\portable.flag -ItemType File -Force | Out-Null
Compress-Archive -Path dist\WarpZip\* -DestinationPath "dist\WarpZip-$Version-portable.zip" -Force
Remove-Item dist\WarpZip\portable.flag
Write-Host "Done -> dist\"
