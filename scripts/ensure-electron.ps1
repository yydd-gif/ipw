# Reinstall the Electron binary (electron.exe) using the China mirror.
# Run from the repo root in PowerShell:
#   .\scripts\ensure-electron.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'

if (Test-Path .\node_modules\electron) {
  Remove-Item -Recurse -Force .\node_modules\electron
}

npm install electron --save-dev --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exe = Get-ChildItem .\node_modules\electron\dist\electron.exe
Write-Host "OK: $($exe.FullName)"
